"""Conversations, durable Participants, and behavioural composition.

Built entirely on the public spine seam. Nothing in this module touches a store,
a file or a record shape -- it calls `Corpus` methods and defines its vocabulary
as data through `define_kind` / `define_relation`. That is deliberate and
structurally tested: if this layer needed storage internals, the spine would not
have been sufficient and we would need to know.

Three things are machine-local and stay that way: a live execution handle, the
material supplied for one invocation, and a composed payload. None of them is a
durable fact and none of them is written to the corpus.

The archaeology at `c896d3e` found that Mark III's failure was composition, not
storage. So: one composition seam, several distinct sources, and every component
keeps the identity of where it came from.
"""

from __future__ import annotations

import re
import threading
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field, replace

# -- vocabulary, defined as data through the public seam ---------------------
#
# The engine branches on none of these. They are rows.

CONVERSATION = "conversation"
PARTICIPANT = "participant"
PERSONA = "persona"
CONTRIBUTION = "contribution"
TOPIC = "topic"
DELETION = "deletion"
CONVERSATION_INSTRUCTION = "conversation-instruction"
OBSERVATION = "observation"
RUNTIME_DEFAULT = "runtime-default"
DISCIPLINE = "discipline"
WORKFLOW = "workflow"
#: THE ONE PLACEMENT DESTINATION THAT IS NOT A CONVERSATION. Placing material
#: on the whole Brain is the ordinary `scoped-to` link, written to an entry of
#: this Kind -- so it is an explicit act with a target, and never a reading of
#: a missing Conversation id. See `whole_brain`.
WHOLE_BRAIN = "whole-brain"
WHOLE_BRAIN_NAME = "Whole Brain"
#: The scope a composition records for material that reached an execution
#: because it is placed on the whole Brain. Not `brain`, which is the scope
#: the Brain-scope ORIENTATION has always been recorded under.
WHOLE_BRAIN_SCOPE = "whole-brain"

#: A CONVERSATION OPENED UNDER A PROVISIONAL NAME is said so by the act that
#: opened it. The Conversation Kind declares `name` and `about` and nothing
#: else, so whether its name is provisional is recorded BESIDE it, as an act
#: with its own who and when, never as a third field: a name is provisional
#: while this act exists for the Conversation and nobody has renamed it since.
PROVISIONALLY_NAMED = "conversation-named-provisionally"
#: The act a rename records, beside the new version it writes.
CONVERSATION_RENAMED = "conversation-renamed"
#: The same, for a Participant: its new alias is its next version.
PARTICIPANT_RENAMED = "participant-renamed"

#: THE TWO VALUES OF `knowing`, WRITTEN HERE AS DATA AND NOT IMPORTED. The seed
#: declares the property and these same two values, and this layer deliberately
#: does not reach into the spine for them -- it reaches the spine only through
#: the public seam, which is a property a test pins. So they are rows here for
#: exactly the reason every other name above is a row: the engine branches on
#: none of them, and `_KINDS` below already states `knowing` the same way.
KNOWING_THAT = "that"
KNOWING_HOW = "how"


def content_of(entry, fields=None, form=None, said=None) -> str:
    """The material's own words, wherever that Kind keeps them.

    ONE CHOICE, BECAUSE FOUR READERS WERE MAKING IT SEPARATELY AND TWO OF
    THEM GOT IT WRONG. A Persona keeps its words in `behaviour`; everything else
    keeps them in `text`. `compose` knew that and fell back; `governs()` and the
    Conversation view read `text` alone -- so a placed Persona governed a
    Conversation, its behaviour crossed into the prompt, and both surfaces the
    owner would correct it through showed an empty string. The owner could see
    THAT something governed and not WHAT.

    SO DELIVERY AND INSPECTION ASK THE SAME FUNCTION. Not because a Persona is
    special, but because "the words this material carries" is one question and
    was being answered in four places. A Kind that keeps its words somewhere
    else again needs one line here and no reader changes.
    """
    body = entry.get("body") or {}
    primary = body.get("text") or body.get("behaviour") or ""
    if not fields:
        return primary
    # EVERY DECLARED FIELD, LABELLED, IN THE KIND'S OWN ORDER. A Discipline
    # keeps its principles in `text` and its tool use, verification and
    # requirements in fields of their own; delivering `text` alone would hand a
    # run the principles and silently drop how to check the work. So the
    # caller passes the Kind's declared fields and this renders each one that
    # holds something: the principal words first and unlabelled, exactly as
    # before, then the rest under a label -- the Kind's own `form` label where
    # it declares one, the field's name otherwise. `name` and `about` are
    # the material's title and subject, which the delivery already says
    # elsewhere, so they are not repeated here. A list is bullets. A Kind with
    # nothing beyond its principal field renders exactly as it always did.
    #
    # `said` IS A FIELD ALREADY PUT INTO WORDS by a caller that can read the
    # record (`Conversations._said_with_links`): references resolved to names,
    # a row group laid out. It replaces only how that one value is shown,
    # under the same label, so a structured field reads as prose rather than
    # as a dictionary.
    said = said or {}
    labels = {name: (f.get("delivered_label") or f.get("label"))
              for name, f in _form_items(form)}
    out = [primary] if primary else []
    for name in fields:
        if name in _PRINCIPAL or name in _TITLES:
            continue
        value = body.get(name)
        if value is None or value == "" or value == [] or value == {}:
            continue
        label = labels.get(name) or name.replace("_", " ").capitalize()
        if said.get(name):
            out.append(f"{label}:\n{said[name]}")
        elif isinstance(value, (list, tuple)):
            out.append(f"{label}:\n" + "\n".join(f"- {v}" for v in value))
        elif isinstance(value, bool):
            out.append(f"{label}: {'yes' if value else 'no'}")
        elif isinstance(value, str) and "\n" in value.strip():
            out.append(f"{label}:\n{value.strip()}")
        else:
            out.append(f"{label}: {value}")
    return "\n\n".join(out)


#: WHERE A KIND KEEPS ITS PRINCIPAL WORDS, and what a rendering leaves out
#: because the delivery already names it. See `content_of`.
_PRINCIPAL = ("text", "behaviour")
_TITLES = ("name", "about")


def _form_items(form):
    """`(field, declaration)` pairs from a `form`, which is keyed by field
    (`seed.FORM_INPUTS` describes the inputs). Anything else declares
    nothing here."""
    if not isinstance(form, dict):
        return []
    return [(k, v) for k, v in form.items() if isinstance(v, dict)]


def rendering_of(corpus, kind) -> tuple[list, dict]:
    """The fields and `form` the CURRENT definition of this Kind declares,
    for `content_of`. Current, for the reason `knowing_of` reads the current
    definition: how material is said is a fact about the vocabulary now.
    Empty for an undefined Kind, which `content_of` renders as it always
    did."""
    if not kind:
        return [], {}
    body = (corpus.current_definition(kind) or {}).get("body") or {}
    return list(body.get("fields") or ()), (body.get("form") or {})


def capability_fields(corpus, kind) -> list[str]:
    """Which of this Kind's fields its `form` declares to hold names from
    the runtime Capability vocabulary (`input: "capabilities"`). Read from the
    declaration, never from a field's name, so a Kind says this about
    itself."""
    return [name for name, f in _form_items(rendering_of(corpus, kind)[1])
            if f.get("input") == "capabilities"]


def capability_refusal(corpus, kind, body, known) -> dict | None:
    """Why this body names a requirement no runtime can declare, or None.

    THE SAME ANSWER `delegate` GIVES, for the same reason. An unknown name is
    UNKNOWN, unknown satisfies nothing, and so material requiring an invented
    one would deterministically make every runtime ineligible for every piece
    of work it reaches. Refused where it is written, in words, rather than
    becoming a recorded pre-start failure nobody expected.

    `known` IS PASSED IN, the runtime Capability vocabulary
    (`capability_names`), because this layer reaches nothing inward of the
    spine seam.
    """
    known = set(known)
    for name in capability_fields(corpus, kind):
        said = (body or {}).get(name)
        if said in (None, ""):
            continue
        if not isinstance(said, (list, tuple)) or not all(
                isinstance(x, str) for x in said):
            return {"error": f"`{name}` is a list of capability names",
                    "kind": kind, "field": name, "given": said,
                    "known": sorted(known)}
        unknown = [x for x in said if x not in known]
        if unknown:
            return {"error": f"{unknown} name no capability any runtime can "
                             f"declare, so nothing could ever satisfy them. "
                             f"Known: {sorted(known)}",
                    "kind": kind, "field": name, "unknown": unknown,
                    "known": sorted(known)}
    return None


#: THE INPUTS WHOSE VALUES NAME OTHER ENTRIES OR CARRY STRUCTURE, and so are
#: checked against the record where they are written (`reference_refusal`).
#: Declared on a Kind's `form`, never inferred from a field's name.
ROW_GROUP = "activities"
PARTICIPANT_INPUT = "participant"
PERSONA_INPUT = "persona"
#: What one row of an `activities` input may say. `who` is who carries it,
#: as a Persona, a Participant and/or a role in words; `disciplines` are
#: references to procedural material its delegated work is given;
#: `coordinates` is the author's declaration that carrying it out takes the
#: coordinate grant (picking up discovered work, say), shown to the owner as a
#: hint and granting nothing.
ACTIVITY_KEYS = ("key", "what", "who", "disciplines", "done_when",
                 "coordinates")
_WHO_KEYS = ("persona", "participant", "role")
_ACTIVITY_KEY = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,39}")


def fields_with_input(corpus, kind, *inputs) -> list[str]:
    """This Kind's fields whose `form` declares one of these inputs."""
    return [name for name, f in _form_items(rendering_of(corpus, kind)[1])
            if f.get("input") in inputs]


def activities_of(corpus, entry) -> list[dict]:
    """The activity rows this material carries, from every field its Kind's
    `form` declares an `activities` input. Empty for every other Kind and for
    a value that is not a list of rows (a write door refuses those; this read
    does not raise on an old or odd record)."""
    if not entry:
        return []
    kind = (entry.get("definition") or {}).get("name")
    body = entry.get("body") or {}
    out = []
    for name in fields_with_input(corpus, kind, ROW_GROUP):
        rows = body.get(name)
        if isinstance(rows, list):
            out.extend(r for r in rows if isinstance(r, dict) and r.get("key"))
    return out


def current_of(corpus, ref) -> dict:
    """What a pinned reference in a body names NOW.

    A procedure names a Discipline by the id it had when the procedure was
    written; revising that Discipline supersedes the id. So a reader follows
    the supersession line forward (`versions.lineage`), as every other
    current-version read does, and says honestly what it found:

        entry     the version to use now, or None when there is none
        pinned    the reference as written
        stands    whether `entry` stands
        why       None when `entry` stands; else "superseded by …" (only when
                  the pinned id was replaced), "not established", "deleted"
                  or "not in this record"
    """
    from .versions import lineage
    got = corpus.read([ref]) if isinstance(ref, str) and ref else []
    if not got:
        return {"entry": None, "pinned": ref, "stands": False,
                "why": "not in this record"}
    lin = lineage(corpus, ref)
    if lin["deletion"] is not None:
        return {"entry": None, "pinned": ref, "stands": False,
                "why": "deleted"}
    now = (lin["current"] or got[0])["id"]
    stands = corpus.stands(now)["stands"]
    why = None if stands else "not established"
    return {"entry": now, "pinned": ref, "stands": stands, "why": why,
            **({"superseded_by": now} if now != ref else {})}


def _entry_of_kind_refusal(corpus, ref, *, field, wanted, why):
    from .versions import inert_refusal
    if not isinstance(ref, str) or not ref.strip():
        return {"error": f"`{field}` is an entry reference", "field": field,
                "given": ref}
    got = corpus.read([ref])
    if not got:
        return {"error": f"{ref!r} is not something this record holds, so "
                         f"`{field}` cannot name it",
                "field": field, "names": ref}
    kind = (got[0].get("definition") or {}).get("name")
    if got[0].get("family") != "entry" or got[0].get("link") or not wanted(kind):
        return {"error": f"{ref!r} is {kind!r} material; `{field}` names "
                         f"{why}", "field": field, "names": ref, "kind": kind}
    refusal = inert_refusal(corpus, ref)
    if refusal:
        # `names`, NOT `entry`: on a write door `entry` is what was written.
        return {"error": f"{ref!r} cannot be named in `{field}`: "
                         f"{refusal['error']}", "field": field, "names": ref}
    return None


def reference_refusal(corpus, kind, body) -> dict | None:
    """Why this body's references or row groups cannot be recorded, or None.

    ASKED OF THE KIND'S OWN `form`, by input and never by field or Kind name:
    a `participant` input names a Participant, a `persona` input a Persona, a
    `list` input is a list of strings, and an `activities` input is a list of
    rows (`ACTIVITY_KEYS`) whose keys are unique, whose `what` is said, whose
    `who` names a real Persona or Participant and whose `disciplines` are
    procedural material the record holds -- not a Persona, which is chosen as
    who, and not material that itself carries activities, which is carried by
    its own carrier rather than handed to a child. STANDING IS NOT ASKED: a
    proposal may name a proposal, and whether anything stands is asked when
    it is delivered, as everywhere. A field the body does not carry is not
    asked about, so a partial edit is checked for what it says. NO SIZE IS
    ASKED: a procedure is as long as it needs to be.
    """
    body = body or {}
    form = dict(_form_items(rendering_of(corpus, kind)[1]))

    def is_persona(k):
        return k == PERSONA

    def is_participant(k):
        return k == PARTICIPANT

    def procedural(k):
        return (k != PERSONA and knowing_of(corpus, k) == KNOWING_HOW
                and not fields_with_input(corpus, k, ROW_GROUP))

    for name, f in form.items():
        if name not in body:
            continue
        value = body.get(name)
        if value in (None, "", []):
            continue
        how = f.get("input")
        if how == PARTICIPANT_INPUT:
            r = _entry_of_kind_refusal(corpus, value, field=name,
                                       wanted=is_participant,
                                       why="a Participant")
            if r:
                return r
        elif how == PERSONA_INPUT:
            r = _entry_of_kind_refusal(corpus, value, field=name,
                                       wanted=is_persona, why="a Persona")
            if r:
                return r
        elif how == "list":
            if not isinstance(value, list) or not all(
                    isinstance(x, str) for x in value):
                return {"error": f"`{name}` is a list of lines", "field": name,
                        "given": value}
        elif how == ROW_GROUP:
            r = _rows_refusal(corpus, name, value, is_persona, is_participant,
                              procedural)
            if r:
                return r
    return None


def _rows_refusal(corpus, name, value, is_persona, is_participant,
                  procedural):
    """`reference_refusal` for one `activities` value."""
    if not isinstance(value, list):
        return {"error": f"`{name}` is a list of activities", "field": name,
                "given": value}
    seen = set()
    for i, row in enumerate(value):
        at = f"{name}[{i}]"
        if not isinstance(row, dict):
            return {"error": f"`{at}` is an activity: an object holding "
                             f"{list(ACTIVITY_KEYS)}", "field": at}
        extra = sorted(set(row) - set(ACTIVITY_KEYS))
        if extra:
            return {"error": f"`{at}` says {extra}, which an activity does "
                             f"not hold; it holds {list(ACTIVITY_KEYS)}",
                    "field": at}
        key = row.get("key")
        if not isinstance(key, str) or not _ACTIVITY_KEY.fullmatch(key):
            return {"error": f"`{at}.key` names the activity: letters, digits, "
                             f"`_`, `.` or `-`, up to 40, starting with a "
                             f"letter or digit", "field": at, "given": key}
        if key in seen:
            return {"error": f"two activities are keyed {key!r}; a key names "
                             f"one activity", "field": at}
        seen.add(key)
        if not isinstance(row.get("what"), str) or not row["what"].strip():
            return {"error": f"`{at}.what` says what the activity is",
                    "field": at}
        if not isinstance(row.get("done_when") or "", str):
            return {"error": f"`{at}.done_when` is words", "field": at}
        if not isinstance(row.get("coordinates", False), bool):
            return {"error": f"`{at}.coordinates` is true or false",
                    "field": at}
        who = row.get("who") or {}
        if not isinstance(who, dict) or set(who) - set(_WHO_KEYS):
            return {"error": f"`{at}.who` holds {list(_WHO_KEYS)}",
                    "field": at, "given": who}
        for k, wanted, why in (("persona", is_persona, "a Persona"),
                               ("participant", is_participant,
                                "a Participant")):
            if who.get(k):
                r = _entry_of_kind_refusal(corpus, who[k],
                                           field=f"{at}.who.{k}",
                                           wanted=wanted, why=why)
                if r:
                    return r
        if not isinstance(who.get("role") or "", str):
            return {"error": f"`{at}.who.role` is words", "field": at}
        ds = row.get("disciplines") or []
        if not isinstance(ds, list):
            return {"error": f"`{at}.disciplines` is a list of references",
                    "field": at}
        for d in ds:
            r = _entry_of_kind_refusal(
                corpus, d, field=f"{at}.disciplines", wanted=procedural,
                why="procedural material a child is given -- a Kind that "
                    "directs how work is done, not a Persona and not "
                    "material that carries activities of its own")
            if r:
                return r
    return None


def declared_placement_refusal(corpus, eid, where) -> dict | None:
    """Why this material may not be placed there, BY ITS KIND'S DECLARATION,
    or None.

    A Kind that declares `authoring.placeable: false` is not placed in a
    Conversation or on the whole Brain (`where` None or the whole-Brain
    destination); one that declares `persona_placeable: false` is not placed
    on a Persona. Only an explicit `false` refuses: a Kind that declares
    nothing, or leaves a key out, is placed exactly as before. A Workflow
    declares both, because a placement would deliver the whole procedure to
    everyone working there -- including the children it hands work to.
    """
    got = corpus.read([eid])
    if not got:
        return None
    kind = (got[0].get("definition") or {}).get("name")
    declared = ((corpus.current_definition(kind) or {}).get("body") or {}
                ).get("authoring") if kind else None
    if not isinstance(declared, dict):
        return None
    target = corpus.read([where]) if where else []
    target_kind = ((target[0].get("definition") or {}).get("name")
                   if target else None)
    if target_kind == PERSONA:
        if declared.get("persona_placeable") is False:
            return {"error": f"{kind!r} material is not placed on a Persona: "
                             f"its Kind declares persona_placeable false",
                    "entry": eid, "where": where, "kind": kind}
        return None
    if declared.get("placeable") is False:
        return {"error": f"{kind!r} material is not placed: its Kind declares "
                         f"placeable false, so it reaches work only by being "
                         f"named for it",
                "entry": eid, "where": where, "kind": kind}
    return None


def body_refusal(corpus, kind, body, known) -> dict | None:
    """Every check a body is put to where it is written, by its Kind's own
    declarations: Capability names (`capability_refusal`), then references
    and row groups (`reference_refusal`). One call, so no door asks one and
    forgets the other."""
    return (capability_refusal(corpus, kind, body, known)
            or reference_refusal(corpus, kind, body))


def knowing_of(corpus, kind) -> str | None:
    """Which ladder this Kind's CURRENT definition puts its material on.

    ONE SOURCE, NO FALLBACK -- the rule `standing_apt` and `expects_falsifier`
    are read under, and for the same reason: whether a Kind's material states
    something or directs work is a fact about the vocabulary NOW, not about what
    an entry meant when it was written. ABSENT STAYS ABSENT and is returned as
    None, which is not a third value.

    MODULE-LEVEL, AND THE ONLY PLACE THIS LOOKUP LIVES. Delivery asks it
    (`placed_procedural`, `_supplied_as`) and so do the owner-facing reads that
    must not disagree with delivery -- `governance.applies` and the governed
    register. Those used to decide what governs from `standing_apt` and
    placement alone, which disagreed with delivery in BOTH directions: placed
    procedural material of a Kind whose `standing_apt` is absent was delivered
    and appeared on neither surface, and a standing `lesson` that was merely
    placed was reported as governing while delivery correctly declined it. A
    second copy of this one-line lookup is how that happens again, so there
    is one.
    """
    if not kind:
        return None
    current = corpus.current_definition(kind) or {}
    return (current.get("body") or {}).get("knowing")


def placements_now(corpus, eid) -> list[str]:
    """Where this material is placed NOW: the targets of its `scoped-to`
    links that nothing has ended, oldest first.

    ONE READ FOR EVERY PLACE THAT CARRIES OR CHECKS A PLACEMENT. A placement
    is ended the way a filing is (`Conversations.end_placement`), so a reader
    that walked every link ever written would keep delivering, inheriting or
    demanding coverage of a placement somebody removed.
    """
    return list(dict.fromkeys(
        x["link"]["to"] for x in corpus.links(relation=SCOPED_TO, frm=eid)
        if not corpus.stands(x["id"])["superseded_by"]))


def whole_brain_ids(corpus) -> set[str]:
    """Every whole-Brain destination entry. Usually none or one; a link to
    any of them is a whole-Brain placement."""
    return {e["id"] for e in corpus.entries_of_kind(WHOLE_BRAIN)}


def whole_brain_refusal(corpus, eid) -> dict | None:
    """Why this material may not be placed on the whole Brain, or None.

    EVERYWHERE IS HELD TO MORE THAN ONE CONVERSATION IS. What is placed on the
    whole Brain reaches every execution in it, so only material that already
    governs is placed there: it must stand, and its Kind must declare that it
    directs how work is done. A proposal is established first, by its own act;
    placing it here never makes it govern. A successor that inherits the
    placement from what it replaces is not asked this here -- it is
    established by the act that replaces, and that act carries the placement.
    """
    got = corpus.read([eid])
    if not got:
        return {"error": "the record holds no such entry, so nothing can be "
                         "placed at it",
                "entry": eid}
    entry = got[0]
    kind = (entry.get("definition") or {}).get("name")
    if (entry.get("family") != "entry" or entry.get("link")
            or knowing_of(corpus, kind) != KNOWING_HOW):
        return {"error": "only material whose Kind directs how work is done "
                         "can be placed on the whole Brain",
                "entry": eid, "kind": kind}
    standing = corpus.stands(eid)
    if not standing["stands"]:
        return {"error": ("this material has been superseded"
                          if standing["superseded_by"] else
                          "this material is not established")
                         + ", so it cannot be placed on the whole Brain; only "
                           "standing material is",
                "entry": eid, "superseded_by": standing["superseded_by"]}
    return None

IN_CONVERSATION = "in-conversation"
PARTICIPATES_IN = "participates-in"
SCOPED_TO = "scoped-to"
REPLIES_TO = "replies-to"
OBSERVES = "observes"
TOPIC_OF = "topic-of"
ABOUT_TOPIC = "about-topic"
LINKED_INTO = "linked-into"
CARRIES_INTAKE = "carries-intake"
PICTURED_BY = "pictured-by"
PRODUCED = "produced"
PURGED = "purged"       # = mentis.spine.held.PURGED, which snapshots read
ANCHOR = "anchor"
REACTION = "reaction"
ANCHORS_IN = "anchors-in"
REACTS_TO = "reacts-to"
OPENED_FROM = "opened-from"
#: DURABLE FILLABLE BLOCKS. See `mentis.conversation.responses`.
RESPONSE_SET = "response-set"
ANSWER = "answer"
MARKED_READY = "marked-ready"
OWN_WORDS = "own-words"
INTERPRETATION = "interpretation"
INTERPRETATION_REPLY = "interpretation-reply"
#: A TIMER'S STARTS AND STOPS. See `mentis.conversation.timers`.
TIMER_MARK = "timer-mark"
RESPONDS_TO = "responds-to"
IN_RESPONSE_SET = "in-response-set"
SHOWN_IN = "shown-in"
DRAWS_ON = "draws-on"
#: THE ROLES A `draws-on` LINK MAY SAY ITS TARGET PLAYS. Three, and no Kind
#: for any of them: an example, a reference or a check is an ordinary entry or
#: held artifact that some governing material points at.
DRAWS_ON_ROLES = ("example", "reference", "check")
#: The scope a composition records for material that reached an execution
#: because it is placed ON the Persona that execution wore: `persona:<id>`.
PERSONA_CARRIED_PREFIX = "persona:"

#: The act an execution records when it hands bytes back. Named here because
#: what a child returned is part of what its parent reads when it resumes;
#: everything else about artifacts is `mentis.artifacts`.
ARTIFACT_RETURNED = "artifact-returned"

#: THE WAYS A RUN'S END IS RECORDED. The first two are written by the dispatch
#: waiter that watched the run finish. The third is written LATER, by a person,
#: when that waiter was lost -- the server hosting it stopped -- while the
#: runtime went on and finished. It closes the run exactly as the other two do,
#: and says the opposite of them about who saw it: nothing in Mentis observed
#: the end, and the result was read back afterwards from the runtime's own
#: evidence. See `recover_result`.
RESULT_RETURNED = "result-returned"
DELIVERY_FAILED = "delivery-failed"
RESULT_RECOVERED = "result-recovered"
#: The act that opens a run. Named because `open_runs` and the run
#: surfaces read it back; the literal is still spelled out in the
#: readers that predate this name.
RUN_START = "execution-started"
RUN_ENDS = (RESULT_RETURNED, DELIVERY_FAILED, RESULT_RECOVERED)


def closed_starts(acts, key) -> set:
    """Which `execution-started` acts among `acts` are over.

    A run on one instance is over when THAT run, or any LATER run on the same
    instance, has an end. An instance runs one thing at a time, so a later run
    ending there means every earlier run there is behind it -- whatever became
    of it. This is the old by-execution-id reading with its one error removed:
    an end belonging to an EARLIER run no longer closes a later one (a
    recovered earlier run used to make a later run on the same instance look
    ended while it was still running).

    "Later" and "earlier" are write order (`key`). An end is placed by the
    start it hangs off (`caused_by`); one that hangs off no start among `acts`
    -- older records, or a fixture -- is placed by its own position instead.

    ONLY AMONG `acts`. Callers pass one request's own acts, so a later run of
    a DIFFERENT request on the instance does not close this request's run;
    that is how it was before this rule, and recovery is how such a run is
    closed.
    """
    starts = {a["id"]: a for a in acts
              if a["act"] == "execution-started" and a.get("execution")}
    # ONE PASS PER INSTANCE, NOT ENDS x STARTS (the owner's slowdown,
    # 2026-10-25). Asked of every act in the record -- `open_runs`, which
    # `/api/activity` reads every four seconds -- the pairwise reading cost
    # 1.3 s of pure Python for ~2,700 runs. The rule is unchanged: a start
    # is closed by an end on its own instance that names it, or whose mark
    # is later than it; so per instance only the LATEST mark and the set of
    # starts named matter.
    latest: dict = {}
    named: set = set()
    for e in acts:
        if e["act"] not in RUN_ENDS or not e.get("execution"):
            continue
        own = starts.get(e.get("caused_by"))
        mark = key(own) if own is not None else key(e)
        x = e["execution"]
        if x not in latest or latest[x] < mark:
            latest[x] = mark
        if own is not None and own["execution"] == x:
            named.add(own["id"])
    return {i for i, s in starts.items()
            if s["execution"] in latest
            and (i in named or key(s) < latest[s["execution"]])}

#: WHAT CARRIES `knowing` HERE, AND WHAT DELIBERATELY DOES NOT. `knowing`
#: ("that" / "how", see `mentis/spine/seed.py`) says whether material of a Kind
#: states something or directs how work is done. A Conversation, a Participant,
#: a Topic, a Contribution, an Observation and a Deletion are NEITHER: they are
#: the record's own furniture, not knowledge, and they carry no `knowing` key at
#: all rather than a third value meaning "not applicable". Absent stays absent.
#:

#: The act that declares work waits on other work it did not delegate. Named
#: because the resumption check reads it back; see `await_work`.
WORK_AWAITED = "work-awaited"

#: WAITING FOR WHAT SOMEBODY FILLS IN (forms build, package P4). An
#: expectation `expects: "input"` is work saying it cannot go on until the
#: owner has filled in a response set (`mentis.conversation.responses`) and
#: marked it ready: `request_input`, the counterpart of `request_decision`.
#: Its `detail` names the set (`response_set`) and the marked-ready entries
#: the set already held when the wait was declared (`ready_before`), which
#: answer nothing. It is ANSWERED ONLY BY A LATER MARKED-READY by the person
#: it was asked of -- or by their withdrawing it -- never by a reply: a chat
#: message on the post fills in nothing.
INPUT = "input"
#: THE KINDS ASKED OF SOMEBODY UNDER A PIECE OF WORK, as part of it: never a
#: piece of work of their own, never awaited with `await_work`, and what the
#: work waits on. Where a reader branched on `== "decision"` for that reason,
#: it now asks this; where it branched for what is particular to a decision
#: (its options, its card, a wake-check review), it still asks "decision".
ASKED_UNDER_WORK = ("decision", INPUT)
#: The act `send_back` records (`mentis.web.inputs`): which answers were handed
#: to the post's author, by whom, and the request that carried them.
ANSWERS_SENT_BACK = "answers-sent-back"

#: DECISIONS AS A FORM ON THE POST THAT ASKS THEM (forms build, package P7;
#: design revision 3, section 9A). `request_decision` with `questions` or
#: `on` records ONE `decision-form` act, caused by the carried request, and
#: one ordinary `kind="decision"` expectation per question, each naming the
#: form (`detail.form`) and its place in it (`detail.index`), with the
#: question's own words (`detail.question`) -- so governance, owner-only
#: withdrawal and Needs You stay per question, exactly as for any decision.
#:
#: WHERE THE FORM IS. On the Turn `on` named, which is then the form's and
#: each question's own `turn`. With no `on`, on no post at all until the
#: run's answer post is written, and then on that post by a
#: `decision-form-attached` act (caused by the form). Until then it is owed
#: and shown in Needs You only. `Conversations.asked_on` answers it.
#:
#: ANSWERED PER QUESTION. A question of a form is answered only by the reply
#: that NAMES it -- `chose: {expectation, option}` or, in the owner's own
#: words, `chose: {expectation}` -- by the person asked, recorded beside the
#: reply as a `decision-answered` act caused by that question. A reply to
#: the post that names no question answers none of them. A decision asked
#: as its own Turn (every decision before this, and a single `question`
#: with no `on`) keeps the rule it always had: any reply of theirs to it.
DECISION_FORM = "decision-form"
DECISION_FORM_ATTACHED = "decision-form-attached"
DECISION_ANSWERED = "decision-answered"

#: WHERE A KIND'S `standing_apt` IS DECLARED, and where it is deliberately not.
#: `ABSENT` means nobody has established whether standing is meaningful for that
#: Kind -- which is NOT the same answer as False, and is not written into the
#: definition at all. See `mentis/spine/seed.py` for the classification.
ABSENT = object()

_KINDS = [
    (CONVERSATION, ["name", "about"],
     "A durable collaborative context. Not a topic, a project, a Work, a task, "
     "a workflow, a Participant, a runtime or a memory.", ABSENT),
    (PARTICIPANT, ["alias", "about"],
     "Durable continuity for a human or an agent. Not a runtime, not a Persona, "
     "not a Conversation and not a live session.", ABSENT),
    # KNOWING HOW. A Persona says how a Participant behaves, so it is read
    # because it GOVERNS the work, never because it answers a question.
    (PERSONA, ["name", "behaviour", "about"],
     "Re-deliverable behavioural material describing how a Participant should "
     "behave while operating in this mode. Confers nothing.", True,
     {"knowing": "how"}),
    (CONTRIBUTION, ["parts", "addressed_to"],
     "One thing somebody contributed. `parts` is a LIST of content parts, so a "
     "contribution is not structurally text.", False),
    # KNOWING HOW, and the reason the delivery path no longer names this Kind:
    # what makes it deliverable is that it directs work and is placed here, not
    # that it is called an instruction. A `rule` placed here is read the same
    # way, and this Kind's meaning is unchanged by that.
    (CONVERSATION_INSTRUCTION, ["text", "about"],
     "Behavioural material that applies within one Conversation, whoever is "
     "acting and whatever Persona they wear.", True,
     {"knowing": "how"}),
    (OBSERVATION, ["about", "what", "detail"],
     "Something observed about something else. Never rewrites what it observes.", False),
    (TOPIC, ["name", "about"],
     "A lightweight organisational and focus dimension inside ONE Conversation. "
     "Not a Conversation, a thread, a task, a workflow stage, a memory, an "
     "epistemic Kind or any kind of boundary. Its name is a label for people; "
     "its identity is its entry id.", ABSENT),
    # THE RECORD THAT SOMETHING WAS DELETED, AND NOTHING ELSE. See
    # `mentis.conversation.versions`. Not captured material and not a claim
    # about anything, so neither capturable nor truth-apt; and it never
    # stands, because a deletion is an act on the record, not material that
    # could govern anything.
    (DELETION, ["reason"],
     "The record that the entry this SUPERSEDES was deleted. From the moment "
     "it was written that entry has no current standing or effect, and it is "
     "not to be used as new support or provenance for anything. IT ERASES "
     "NOTHING: the deleted entry, what it said, every act and link that ever "
     "touched it, and every earlier use of it stay in the record exactly as "
     "they were, and history may still say truthfully that it contributed. "
     "It does not replace the deleted material's content and says nothing "
     "about whether that material was right. Deleted material is not "
     "restored in place: if its content is wanted again it is written again, "
     "as new material with its own provenance.", False,
     {"capturable": False, "truth_apt": False}),
    # WHICH RUNTIME A PARTICIPANT'S WORK RUNS ON WHEN THE WORK NAMES NONE.
    # Declared by a person, never read from the alias: a name is not a
    # runtime, and no Participant may be named like one (`participant_names`). Not knowledge (no `knowing`), so it cannot be
    # proposed through the worker door, and not a claim. It is resolved into a
    # recorded constraint on each piece of work when that work is recorded or
    # first run, so changing it later moves no work already bound.
    (RUNTIME_DEFAULT, ["participant", "runtime"],
     "A person's declaration of the runtime that runs this Participant's work "
     "when the work names none. `runtime` null declares runtime-auto. Says "
     "nothing about who the Participant is, and is never inferred from its "
     "name.", True,
     {"capturable": False, "truth_apt": False}),
    # ANCHORED INTERACTION. See `mentis.conversation.anchors`. Neither Kind is
    # adjudicated, neither is a claim, neither is captured from outside, and
    # neither directs or informs work -- so `standing_apt` is declared False
    # (they are "standing not meaningful", never "proposed") and `knowing` is
    # absent, as for the rest of the record's own furniture.
    (ANCHOR, ["selector"],
     "A durable, precise target inside ONE immutable version of a Turn: the "
     "whole version, or a range of code points in one of its text parts. It "
     "asserts nothing about what it names. Never edited and never deleted; "
     "once the Turn is deleted it is history and not used anew.", False,
     {"capturable": False, "truth_apt": False}),
    # WHERE MATERIAL IS PLACED WHEN IT APPLIES EVERYWHERE. A destination for
    # the ordinary `scoped-to` link and nothing else: it holds no material,
    # is not the Brain's identity, and is written only when an owner first
    # places something on the whole Brain. Record furniture, like a
    # Conversation, so it declares no `knowing` and standing is not meaningful.
    (WHOLE_BRAIN, ["name", "about"],
     "The placement destination meaning this whole Brain: every Conversation "
     "in it, now and later, and work done at Brain scope outside any "
     "Conversation. Material placed here applies everywhere exactly as "
     "material placed at one Conversation applies there, and stops when that "
     "placement is ended. It holds no material of its own and confers "
     "nothing.", False,
     {"capturable": False, "truth_apt": False}),
    (REACTION, ["about", "token"],
     "An actor's lightweight reaction to an anchor: who, and which token. An "
     "immutable occurrence with no standing and no effect on anything. A "
     "change is a new reaction that supersedes it; withdrawing it is a "
     "deletion. Not an observation, not a comment, not a judgement of the "
     "material.", False,
     {"capturable": False, "truth_apt": False}),
    # DURABLE FILLABLE BLOCKS. See `mentis.conversation.responses`. What a
    # person fills in is an attributed occurrence, like a reaction: not
    # adjudicated, not a claim, not captured from outside, and it neither
    # directs nor informs work -- so `standing_apt` is False and `knowing` is
    # absent, which is what keeps every one of them out of retrieval,
    # delivery, adoption and the register.
    (RESPONSE_SET, ["post", "version", "part", "block", "type", "mode",
                    "holder", "started_from", "conversation"],
     "Where what is filled in one fillable block of one Turn is kept: the "
     "Turn's root, its text part, the block's name and type, and whether it "
     "is one shared set or one person's own (`holder`). A set started from "
     "another names it (`started_from`) and where it was started. Holds no "
     "values itself and asserts nothing. Never edited and never deleted.",
     False,
     {"capturable": False, "truth_apt": False}),
    (ANSWER, ["set", "field", "value", "note", "replaces", "version", "check",
              "conversation"],
     "One person's value for one field of a response set, as they gave it, "
     "checked against the version of the Turn it names, and the "
     "Conversation it was given in. An immutable "
     "occurrence with no standing: a change is a new answer naming the ones "
     "it replaces, and two answers replacing the same one are both kept, as "
     "a conflict. Never edited and never deleted. Not knowledge, not a "
     "claim, and confers nothing.", False,
     {"capturable": False, "truth_apt": False}),
    (MARKED_READY, ["set", "answers"],
     "A person's statement that their input in a response set is finished as "
     "it stood: the exact answers it covers. Later answers do not undo it; "
     "the set then reads as changed since ready. Confers nothing.", False,
     {"capturable": False, "truth_apt": False}),
    (OWN_WORDS, ["set", "text", "replaces", "conversation"],
     "Free text a person adds to a response set in their own words, kept "
     "exactly as written, under their name. A new version names the one it "
     "replaces, and the earlier wording stays. Nothing reads it as an answer "
     "to any field unless the person confirms that. Not knowledge and "
     "confers nothing.", False,
     {"capturable": False, "truth_apt": False}),
    (INTERPRETATION, ["set", "words", "passage", "proposes", "version",
                      "mapped", "check"],
     "Somebody else's reading of a passage of a person's own words in a "
     "response set, under the reader's name: the exact passage it cites, and "
     "one thing it proposes -- a field's value, a row, or a new field -- "
     "with the version of the Turn it was read against. Unconfirmed: it is "
     "no answer and replaces nothing until that person confirms it. Not "
     "knowledge and confers nothing.", False,
     {"capturable": False, "truth_apt": False}),
    (INTERPRETATION_REPLY, ["set", "interpretation", "outcome", "answer",
                            "changed_to", "reason"],
     "What the person whose words were interpreted did with the "
     "interpretation, once: confirmed, changed or declined, and the answer "
     "that confirming or changing a field's value wrote. Confers nothing.",
     False,
     {"capturable": False, "truth_apt": False}),
    (TIMER_MARK, ["set", "action", "at", "run", "replaces", "reason",
                  "problems", "direction"],
     "One mark on a timer in a person's own response set: a start, a stop, "
     "a continue at the check-in, or a box or break ending -- what was done "
     "and when. A correction is a new stop naming the stop it replaces, and "
     "two replacing the same one are both kept, as a conflict. A mark an "
     "agent wrote names the owner's direction it acted on. Totals are read "
     "from the marks every time and never stored. Never edited and never "
     "deleted. Not knowledge, not a claim, and confers nothing.", False,
     {"capturable": False, "truth_apt": False}),
    # KNOWING HOW, AND THE ONE KIND THIS FEATURE ADDS. Practical expertise
    # somebody can reuse: what to hold to, how to go about it, which tools it
    # uses and how, and how to tell the work was done to it. Examples,
    # references and checks are NOT Kinds -- they are existing entries or held
    # artifacts it `draws-on`. It is delivered the way every procedural Kind
    # is (placed, carried by a Persona, or named for the work) and it confers
    # nothing: `tool_use` is prose the runtime may or may not be able to act
    # on, and `requires` narrows which runtimes may carry work it reaches, so
    # it can only ever REFUSE a runtime, never grant one anything.
    #
    # `authoring` AND `form` ARE DECLARATIONS FOR AN AUTHORING SURFACE, carried
    # verbatim like every other property and branched on by nothing in the
    # engine. `form` is also what `content_of` labels the delivered fields by,
    # and what says `requires` names Capabilities (`capability_refusal`).
    (DISCIPLINE, ["name", "about", "text", "tool_use", "verification",
                  "requires"],
     "Governed, reusable practical expertise: the principles and procedure "
     "for a kind of work, the tools it uses and how, how to verify work done "
     "to it, and which runtime capabilities it requires. Its examples, "
     "references and checks are existing entries or held artifacts it draws "
     "on. It guides behaviour using tools the runtime actually has; it grants "
     "no capability and no authority, and its tool use is not verified by "
     "Mentis.", True,
     {"knowing": "how", "capturable": False, "truth_apt": False,
      # THE SHAPE WORKSTREAM A's DECLARATION-DRIVEN BUILDER READS
      # (`seed.KIND_PROPERTIES`, `seed.FORM_INPUTS`): `form` keyed by field,
      # list inputs stored as JSON lists. `delivered_label` is this Kind's own
      # addition, read by `content_of` alone.
      "authoring": {"section": "disciplines", "section_label": "Disciplines",
                    "door": "entry", "placeable": True,
                    "persona_placeable": True, "basis": False},
      "form": {
          "name": {"label": "Name", "input": "line"},
          "about": {"label": "When it applies", "input": "line",
                    "help": "the kind of work this Discipline is for"},
          "text": {"label": "Principles and procedure", "input": "text",
                   "rows": 12,
                   "help": "what to hold to and how to go about the work; "
                           "no length limit"},
          "tool_use": {"label": "Tool use", "input": "text", "rows": 6,
                       "help": "which tools it uses and how. Shown to runs "
                               "as not verified by Mentis",
                       "delivered_label": "Tool use (the tools this "
                                          "Discipline uses; not verified by "
                                          "Mentis)"},
          "verification": {"label": "Verification", "input": "text",
                           "rows": 6,
                           "help": "how to tell work was done to it"},
          "requires": {"label": "Requires", "input": "capabilities",
                       "help": "runtime capabilities work under this "
                               "Discipline needs; a runtime without them is "
                               "not selected"},
      }}),
    # HOW A PIECE OF WORK PROCEEDS, DESCRIBED AND NOTHING MORE. Its activities,
    # who carries each and under which Disciplines, the decisions reserved to
    # the owner, and when it is done. IT IS NOT AN ENGINE: there are no
    # transitions, no stages, no stored position and no act that moves
    # anything on its own. It is NAMED for a request (`governed`), delivered
    # to that request's carrier as procedural material, and carried out with
    # the coordination every run already has -- `delegate` (whose optional
    # `activity` only labels which activity a child is for), `await_work`,
    # `request_decision`, the coordinate grant. Where the work has got to is
    # READ from the record (the work status, `mentis.operational.work`), never kept.
    #
    # NOT PLACEABLE, deliberately: material placed at a Conversation reaches
    # everybody who works there, which would hand the whole procedure to the
    # children it delegates to. They are given their activity's Disciplines
    # by name instead.
    (WORKFLOW, ["name", "about", "text", "activities", "decisions",
                "done_when", "carrier", "persona", "requires"],
     "A governed, reusable description of how a kind of work proceeds: its "
     "activities, who carries each and under which Disciplines, the "
     "decisions reserved to the owner, and when it is done. It is named for "
     "a request and delivered to the request's carrier, who organises the "
     "work with the coordination it already has. It is not an engine: it "
     "holds no position, schedules nothing, moves nothing by itself and "
     "grants no authority; how far the work has got is read from the "
     "record.", True,
     {"knowing": "how", "capturable": False, "truth_apt": False,
      "authoring": {"section": "workflows", "section_label": "Workflows",
                    "door": "entry", "placeable": False,
                    "persona_placeable": False, "basis": False},
      "form": {
          "name": {"label": "Name", "input": "line"},
          "about": {"label": "When it applies", "input": "line",
                    "help": "the kind of work this Workflow is for"},
          "text": {"label": "How the work proceeds", "input": "text",
                   "rows": 8,
                   "help": "the shape of the work in words; no length limit"},
          "activities": {"label": "Activities", "input": "activities",
                         "help": "each activity: what it is, who carries it, "
                                 "the Disciplines its delegated work is "
                                 "given, and when it is done. Not stages: "
                                 "nothing moves from one to the next by "
                                 "itself"},
          "decisions": {"label": "Decisions reserved to the owner",
                        "input": "list",
                        "help": "one per line; the carrier asks these with "
                                "request_decision and never makes them"},
          "done_when": {"label": "Done when", "input": "text", "rows": 3},
          "carrier": {"label": "Usually carried by", "input": "participant",
                      "help": "a default the Composer pre-fills; the owner "
                              "can change it"},
          "persona": {"label": "Carried as", "input": "persona",
                      "help": "the Persona the carrier usually wears; a "
                              "pre-filled default"},
          "requires": {"label": "Requires", "input": "capabilities",
                       "help": "runtime capabilities the carrier needs; "
                               "with its activities' Disciplines' needs, a "
                               "runtime without them is not selected"},
      }}),
]

_RELATIONS = [
    (IN_CONVERSATION, "holds", "This contribution belongs to that Conversation."),
    (PARTICIPATES_IN, "has-participant",
     "This Participant takes part in that Conversation. Says nothing about any "
     "Persona, runtime or execution."),
    # REWORDED FOR A PERSONA DESTINATION. Only a Brain defined from now on
    # gets these words: an existing Brain keeps the meaning it recorded,
    # because rewording a Brain's vocabulary is the owner's act, not a side
    # effect of opening it.
    (SCOPED_TO, "carries",
     "This behavioural material applies THERE: within that Conversation, "
     "everywhere when that is the whole-Brain destination, or -- when that is "
     "a Persona -- wherever a Participant operates as that Persona, which is "
     "how a Persona carries Disciplines and other procedural material. "
     "Placement, as data; it confers nothing."),
    (REPLIES_TO, "answered-by", "This contribution answers that one."),
    (OBSERVES, "observed-by",
     "This observation is about that record. Append-only: the observed record "
     "is never touched."),
    (TOPIC_OF, "has-topic",
     "This Topic organises that Conversation. A Topic belongs to exactly one."),
    (ABOUT_TOPIC, "discussed-in",
     "This contribution is associated with that Topic. It does NOT move the "
     "contribution, does not remove it from the Conversation's chronology, and "
     "grants and withholds nothing. A contribution may carry none, one or "
     "several of these."),
    (LINKED_INTO, "shows-linked",
     "This contribution is SHOWN in that Conversation as well, as a link back "
     "to where it was written. It still belongs to its own Conversation: its "
     "number, its thread and its replies are there, and nothing is moved, "
     "copied or renumbered. Grants and withholds nothing. Ended the way a "
     "filing is ended, by a deletion record that supersedes this link."),
    (CARRIES_INTAKE, "intake-carried-by",
     "This Participant carries requests addressed to nobody in particular in "
     "this Brain, wearing that Persona. FROM a Participant TO a Persona, so "
     "the one link says who and as-what together and neither can be read "
     "without the other. It is ORDINARY DATA: it confers no authority, names "
     "no runtime, and grants nothing. What makes it apply is that something "
     "established it and nothing superseded it -- the same `stands` every "
     "other entry is judged by -- so replacing the designation is an ordinary "
     "supersession and earlier assignments stay true as history. None in "
     "force, or more than one, is UNRESOLVED and not a tie to be broken."),
    (PICTURED_BY, "pictures",
     "This Participant is shown with that held image. FROM a Participant TO "
     "an Admission whose bytes are an image. Presentation only: it confers "
     "nothing, names no runtime, and says nothing about who the Participant "
     "is. Applies while it stands; choosing another image supersedes it and "
     "going back to the default ends it, so every earlier picture stays in "
     "the record as history."),
    # BOOTSTRAPPED, NOT LEFT TO A FIXTURE. `produced` was only ever defined by
    # the demo fixture, so on a fresh Brain reading it returned nothing -- which
    # looks exactly like "nothing was produced" -- and writing it raised. Found
    # by the artifact-ingress execution (ent-091bd6ec6261).
    (PRODUCED, "produced-by",
     "This operational act brought this durable Entry into being as a result "
     "of the act. Production, and only production: `about` on an act means it "
     "concerned something, never that it made it."),
    (ANCHORS_IN, "anchored-by",
     "This anchor names a place in a version of that Turn. FROM the anchor TO "
     "the Turn's root. Confers nothing and says nothing about the Turn."),
    (REACTS_TO, "reacted-by",
     "This reaction is to that anchor. Confers nothing."),
    (RESPONDS_TO, "responded-in",
     "This response set keeps what is filled in a block of that Turn. FROM "
     "the set TO the Turn's root. Confers nothing."),
    (IN_RESPONSE_SET, "holds-response",
     "This answer, marked-ready, own-words, interpretation, reply or timer "
     "mark belongs to that response set. Confers nothing."),
    (SHOWN_IN, "shows-response-set",
     "This response set's answers are shown in that Conversation too, where "
     "its Turn is included: the same answers, each saying where it was "
     "given. Moves and copies nothing, and confers nothing."),
    (OPENED_FROM, "opened",
     "This Conversation was opened to explore that anchor, for the reason on "
     "the link. LINEAGE ONLY: not support, not context, and nothing of the "
     "Conversation the anchor is in is inherited through it."),
    (DRAWS_ON, "drawn-on-by",
     "This governing material draws on that entry or held artifact as an "
     "example, a reference or a check -- the role and a short label are on "
     "the link. Where the material is delivered the link is LISTED, one line "
     "each, and the target is read on demand; its words are never copied in. "
     "INERT: it confers no standing on either end, establishes nothing, and "
     "grants nothing beyond the artifact offer delivery already makes. "
     "Running a check is recorded as an ordinary outcome of the check."),
    (PURGED, "purged-by",
     "This operational act removed the bytes Mentis held for that Admission. "
     "The Admission, what produced it, every Turn that names it and every "
     "earlier delivery stay exactly as they were; only possession ended. Says "
     "nothing about copies outside this corpus, and is not secure erasure."),
]


def text(s: str) -> dict:
    """The one content part this slice actually delivers."""
    return {"type": "text", "text": s}


def standing_state(standing: dict) -> str:
    """Where an entry is, as governed material, from what `stands` returned.

    ONE CLASSIFICATION, READ WHEREVER MATERIAL IS SORTED. `governs()` sorts one
    Conversation's instructions by it and the Brain-wide register
    (`mentis.conversation.register`) sorts every governed entry by it, so the
    two cannot disagree. The UI's `standingOf` gives the same four answers.

      stands     established, and nothing has superseded it
      ended      superseded after it had been established -- it USED to hold
      replaced   REPLACED BEFORE ESTABLISHMENT. Nobody ever established it and
                 somebody then superseded it, so it never held: calling it
                 ended would credit it with a standing it never had. Nor is it
                 still a candidate -- the supersession is the recorded answer
                 to the proposal. It is kept, unchanged, as what was proposed
                 and then replaced. This is how the record is READ; the spine
                 does not refuse a later establishment of it.
      candidate  written, and neither established nor answered by a successor
    """
    if standing["stands"]:
        return "stands"
    if standing["superseded_by"]:
        return "ended" if standing["established_by"] else "replaced"
    return "candidate"


_GOVERNS_BUCKET = {"stands": "governing", "ended": "ended",
                   "replaced": "replaced", "candidate": "candidates"}


# -- composition results, all computed, none durable ------------------------


@dataclass(frozen=True)
class Component:
    """One piece of behavioural material, with where it came from intact.

    `source_id` is None only for material that has no durable identity, which
    in this slice means invocation-scoped material and the request itself.
    """

    source_kind: str
    source_id: str | None
    scope: str
    text: str
    why: str
    about: str = ""
    #: WHICH LADDER THIS CAME UP, and absent where the question does not apply.
    #: Read from the source Kind's CURRENT definition at the moment of
    #: composing -- `knowing == "how"` is governance, `knowing == "that"` is
    #: knowledge -- and left None for material that declares neither: the
    #: orientation, the invocation strings, the request itself. None is NOT a
    #: third ladder and must not read as either, which is why `sources()` omits
    #: the key rather than emitting a null.
    supplied_as: str | None = None
    #: THE OTHER SCOPES THAT WOULD HAVE SUPPLIED THIS SAME MATERIAL, and were
    #: not delivered twice. Material placed at this Conversation AND on the
    #: whole Brain is one component recorded under `scope`, with
    #: `whole-brain` here, so the record keeps both reasons it applied.
    #: Empty, and omitted from `sources()`, wherever there was one reason.
    also: tuple = ()
    #: WHAT THE MATERIAL IS CALLED AND WHAT IT IS FOR, said above its words,
    #: for a Kind whose definition declares a `form` (a Discipline's `name`
    #: and `about`). Empty for every other Kind, which renders as it always
    #: did. Rendering only; `sources()` is unchanged.
    title: str = ""
    #: WHICH TIER OF THE LADDER THIS WAS DELIVERED ON: `governing` (directs
    #: the work), `adopted` (the Brain's working position) or `experience`
    #: (recorded, not adopted: evidence to weigh). None for what is on no
    #: ladder -- the orientation, invocation strings, the request -- exactly
    #: as `supplied_as` is None there. `supplied_as` says which ladder the
    #: KIND is on; this says what standing THIS ITEM was delivered with, which
    #: is a second fact: a recorded lesson and an adopted one are both
    #: `knowledge`, and only one of them is the Brain's position.
    tier: str | None = None
    #: WHAT TRAVELS WITH IT (`ladder.trailer`, or `ladder.why_this_holds` for
    #: governing material): attribution, basis, limits, outcomes, open
    #: challenges, status. Read at composition, rendered compactly under the
    #: words, and kept out of equality and hashing -- it is evidence about the
    #: component, not part of what the component is.
    trailer: dict | None = field(default=None, compare=False, hash=False)


#: THE SCOPES THROUGH WHICH MATERIAL GOVERNS A RUN: selected as its Persona,
#: carried by that Persona, named for the work, placed at its Conversation, or
#: placed on the whole Brain. NOT the orientation (record furniture, recorded
#: under a Conversation scope) and NOT the knowledge channel (`question:...`,
#: material offered because it may be relevant, which governs nothing).
GOVERNING_SCOPES = ("invocation:persona", "invocation:named")
GOVERNING_PREFIXES = ("persona:", "conversation:")


@dataclass(frozen=True)
class Conflict:
    """Two applicable components speak to the same declared subject.

    Surfaced, never resolved. There is no precedence model and inventing one
    without evidence is exactly what the archaeology warned against.
    """

    about: str
    components: tuple[Component, ...]


@dataclass(frozen=True)
class Composition:
    components: tuple[Component, ...]
    conflicts: tuple[Conflict, ...]
    withheld: tuple[dict, ...]

    #: HOW THE SUPPLY REASON IS SPELLED IN THE RENDERING. One short qualifier
    #: in front of the Kind's own name, and deliberately nothing more: no
    #: header, no section, no schema and no metadata protocol. `sources()` is
    #: where the durable answer lives and it is unchanged.
    _QUALIFIER = {"governance": "governs", "knowledge": "knowledge"}
    #: AND THE THIRD WORD, FOR A TIER RATHER THAN A LADDER. Recorded material
    #: comes up the same ladder as adopted knowledge -- its Kind declares
    #: `knowing: "that"` -- and must not arrive under the same word, because
    #: `knowledge` reads as something this Brain holds. `experience` says it
    #: was somebody's record and nothing more; its trailer says the rest.
    _TIER_QUALIFIER = {"experience": "experience"}
    #: How much of an adopted or recorded entry the rendering says: its first
    #: line, cut here (`_rendered`).
    KNOWLEDGE_GIST = 160

    def payload(self) -> str:
        """A rendering. The components remain the truth; this is a view.

        AND IT SAYS WHICH LADDER EACH LINE CAME UP, because the actor is who the
        distinction is FOR. This used to render the Kind's NAME alone -- so a
        Kind called `rule` that declares `knowing: "that"` arrived as `[rule]`
        flush against real governance, a Kind called `observation_note` that
        declares `"how"` arrived looking like a note, and `supplied_as` never
        left the process. The reader was left inferring a ladder from a noun,
        which is the one thing nothing here is allowed to reason from.

        ABSENT STAYS ABSENT. A component whose Kind declares neither -- the
        orientation, the invocation strings, the request itself -- renders
        exactly as it always did, with no qualifier at all. A third word here
        would invent the third ladder the rest of this module refuses to invent.
        """
        return "\n\n".join(self._rendered(c) for c in self.components)

    def _rendered(self, c) -> str:
        """One component as the run reads it. Governing material also says
        its REFERENCE, on a line of its own at the end, because a run may name
        it back -- `propose_revision` takes it as `of` -- and the words alone
        do not say which entry they are. A Kind that declares a `form` has its
        name and subject (`title`) said in the heading."""
        q = (self._TIER_QUALIFIER.get(c.tier)
             or self._QUALIFIER.get(c.supplied_as))
        tag = f"[{q} · {c.source_kind}]" if q else f"[{c.source_kind}]"
        text = c.text
        # KNOWLEDGE AND EXPERIENCE ARRIVE AS A GIST AND A REFERENCE. They
        # were chosen because their words overlap the request, not because
        # they govern it, and one recorded finding can run to thousands of
        # characters; the run reads the whole entry with `resolve` when it
        # bears on the work. Governing material is never cut.
        if c.tier in ("adopted", "experience") and c.source_id:
            gist = first_line(text, self.KNOWLEDGE_GIST)
            if gist != text.strip():
                text = f"{gist} [first line only; resolve its reference for the rest]"
        body = f"{tag} {c.title}\n{text}" if c.title else f"{tag} {text}"
        # THE REFERENCE, so a run can name it back: governing material for a
        # revision, and adopted or recorded material for a citation or an
        # outcome recorded against it -- which is how later work says it used
        # what it was given. Directly under the words, where it always was.
        if c.source_id and (c in self.governing()
                            or c.tier in ("adopted", "experience")):
            body += f"\n(reference: {c.source_id})"
        # WHAT TRAVELS WITH IT, ON ONE LINE UNDER THAT: who recorded it and
        # where, its basis, limits, latest outcomes, open challenges and its
        # status -- or, for governing material, why it holds and what is
        # still challenged. A run that is handed a recorded lesson without
        # these is handed a claim with nothing to check it against. A
        # governing item with no evidence linked and nothing challenged has
        # nothing to add, and adds nothing.
        if c.trailer:
            from .ladder import render_governing_note, render_trailer
            line = (render_governing_note(c.trailer) if c.tier == "governing"
                    else render_trailer(c.trailer, c.tier))
            if line:
                body += "\n" + line
        return body

    def governing(self) -> tuple:
        """The components that GOVERN the run: material whose Kind declares
        that it directs how work is done (`supplied_as == "governance"`),
        delivered through a governing scope (`GOVERNING_SCOPES`). Asked of
        the declaration recorded on each component, never of a Kind's name.
        Only standing material is ever a component, so all of these stand."""
        return tuple(
            c for c in self.components
            if c.source_id and c.supplied_as == "governance"
            and not c.source_kind.endswith("orientation")
            and (c.scope in GOVERNING_SCOPES or c.scope == WHOLE_BRAIN_SCOPE
                 or c.scope.startswith(GOVERNING_PREFIXES)))

    def governing_ids(self) -> list[str]:
        """The ids of `governing()`, in delivery order: what a run was TOLD
        that governs it, and the only material it may propose to revise or
        whose drawn-on artifacts it is offered."""
        return list(dict.fromkeys(c.source_id for c in self.governing()))

    def sources(self) -> list[dict]:
        """What a delivery record should carry about behavioural origin.

        AND WHAT EACH COMPONENT WAS SUPPLIED AS, which the record could not say
        before. A delivery that lists a `finding` and a `rule` side by side,
        with nothing distinguishing them, records two very different claims in
        one shape: one is something this Brain knows and offered because it may
        be relevant, the other is something that GOVERNS the work. Afterwards
        nobody could say which had been which.

        `supplied_as` says it, in the Kind's own declared terms: `knowledge`
        where the Kind declares `knowing == "that"`, `governance` where it
        declares `"how"`. WHERE THE KIND DECLARES NEITHER THE KEY IS ABSENT,
        never null-as-a-value and never a third word -- the record's own
        furniture is in no ladder, and saying so by saying nothing is the only
        answer that does not invent a category.

        THE COLUMN'S NAME PREDATES THIS DISTINCTION. This lands in
        `delivery.behavioural_sources`, which was named when everything
        composition delivered was behavioural. It is not renamed and no second
        column is added: the column holds what the composition sourced, which
        is what it always held, and the rows now say which ladder each came up.
        """
        # AND THE TIER, where there is one, so the record can later say a
        # lesson reached a run as EXPERIENCE rather than as adopted knowledge
        # (`ladder.delivered_to`). Absent where the component is on no tier,
        # for the reason `supplied_as` is absent there.
        return [{"source_kind": c.source_kind, "source_id": c.source_id,
                 "scope": c.scope,
                 **({"supplied_as": c.supplied_as} if c.supplied_as else {}),
                 **({"tier": c.tier} if c.tier else {}),
                 **({"also": list(c.also)} if c.also else {})}
                for c in self.components]


@dataclass
class Execution:
    """A live handle. Machine-local, ephemeral, never durable.

    It holds the invocation-scoped material, which is why that material cannot
    outlive the execution: there is nowhere else it lives.
    """

    reference: str
    participant: str
    conversation: str
    persona: str | None = None
    material: tuple[str, ...] = ()
    #: The request this execution is carrying, where the caller knew it. One
    #: Participant may carry several at once in one Conversation, so this is
    #: what keeps them apart; None means nobody said, not "no request".
    for_expectation: str | None = None
    ended: bool = False
    runtime: str | None = None
    boundary: object = field(default=None, repr=False)


class Conversations:
    """The public Conversation capability, over the public spine seam."""

    def __init__(self, corpus):
        self._c = corpus
        # The open `reading()` scope for THIS thread and THIS Conversations,
        # and nothing wider. See `reading`: a request-scoped memo, never a
        # cache, never shared -- not between threads, and not between two
        # Conversations over two corpora in one process.
        self._scope = threading.local()
        self._executions: dict[str, Execution] = {}   # machine-local
        self._ensure_vocabulary()

    @property
    def corpus(self):
        """The spine seam underneath. Public, because this layer adds no store."""
        return self._c

    # -- vocabulary ---------------------------------------------------------

    def _ensure_vocabulary(self):
        for name, fields, meaning, standing_apt, *extra in _KINDS:
            if self._c.current_definition(name) is None:
                props = {"meaning": meaning, "capturable": True,
                         "truth_apt": False, **(extra[0] if extra else {})}
                # ABSENT IS NOT WRITTEN DOWN. A Kind nobody has judged carries
                # no `standing_apt` key at all, so a reader sees UNKNOWN rather
                # than a False somebody never established.
                if standing_apt is not ABSENT:
                    props["standing_apt"] = standing_apt
                self._c.define_kind(name, fields=fields, properties=props,
                                    attributed_to="human")
        for name, inverse, meaning in _RELATIONS:
            if self._c.current_definition(name) is None:
                self._c.define_relation(name, inverse=inverse,
                                        properties={"meaning": meaning},
                                        attributed_to="human")

    # -- durable objects ----------------------------------------------------

    def open_conversation(self, name, *, about="", attributed_to="human",
                          written_by=None, provisional=False) -> str:
        """A Conversation, under a name.

        `provisional`: the name stands in until somebody names it
        (`rename_conversation`), and the act `PROVISIONALLY_NAMED` says so,
        written in the same step. With no name, the provisional one is
        `provisional_name()`. Without `provisional` this is what it always
        was: one entry, established, and nothing else.
        """
        if not provisional:
            return self._c.create_and_establish(
                kind=CONVERSATION, body={"name": name, "about": about},
                attributed_to=attributed_to, written_by=written_by)
        name = (name or "").strip() or provisional_name()
        with self._c.atomic():
            cid = self._c.create_and_establish(
                kind=CONVERSATION, body={"name": name, "about": about},
                attributed_to=attributed_to, written_by=written_by)
            self.record_act(actor=attributed_to, act=PROVISIONALLY_NAMED,
                            conversation=cid, about=[cid],
                            detail={"name": name})
        return cid

    # -- a Conversation's name ----------------------------------------------
    #
    # A CONVERSATION KEEPS ITS IDENTITY AT THE ROOT, as a Turn and a Topic do
    # (`versions.ROOT_IDENTITY`): every post, link, placement and act names the
    # entry it was opened as, and a rename is its next version, superseding the
    # last. So the one way to read a Conversation's name is as it NOW reads --
    # `conversation_now` -- and its later versions are never Conversations of
    # their own (`all_conversations`, `is_conversation`).

    def conversation_now(self, conversation) -> dict | None:
        """The Conversation as it now reads: its own id, author and time, with
        its current version's body. None when that is not a Conversation."""
        from .versions import presented
        got = self._c.read([conversation]) if conversation else []
        if not got or not self._is(got[0], CONVERSATION):
            return None
        return presented(self._c, got[0])

    def conversation_name(self, conversation) -> str | None:
        """A Conversation's CURRENT name, or None."""
        got = self.conversation_now(conversation)
        return (got.get("body") or {}).get("name") if got else None

    def is_conversation(self, eid) -> bool:
        """A Conversation itself: an entry of the Kind that is not a later
        version of one. A rename's version is the Conversation it renames."""
        got = self._c.read([eid]) if isinstance(eid, str) and eid else []
        return bool(got) and self._is(got[0], CONVERSATION) and not \
            self._c.links(relation=self._c.superseding_relation(), frm=eid)

    def version_refusal(self, eid) -> dict | None:
        """Why this id may not be taken as a Conversation, when it is a later
        version of one -- a rename's version -- or None.

        A VERSION IS NEVER A CONVERSATION OF ITS OWN, AT ANY DOOR. It is
        REFUSED, never resolved to the Conversation it renames: a post homed,
        a post included or a name written under an id the caller did not mean
        would be the split this guards against, done quietly. The refusal
        names the Conversation (`version_of`), so a caller can ask again with
        it. Anything that is not a Conversation entry at all is the door's own
        question, answered as it always was."""
        got = self._c.read([eid]) if isinstance(eid, str) and eid else []
        if not got or not self._is(got[0], CONVERSATION):
            return None
        if not self._c.links(relation=self._c.superseding_relation(),
                             frm=eid):
            return None
        root = self._c.history(eid)[0]
        return {"error": f"{eid} is a later version of conversation {root} "
                         "(its name), not a conversation of its own; name "
                         f"{root} instead",
                "conversation": eid, "version_of": root}

    def provisional(self, conversations) -> dict:
        """conversation -> whether its name is provisional NOW: it was opened
        under a provisional name and nobody has renamed it since. One read of
        the acts and one of the renames, for the whole set."""
        ids = list(dict.fromkeys(c for c in conversations if c))
        if not ids:
            return {}
        named = {a["conversation"] for a in self._c.operational(
            act=PROVISIONALLY_NAMED, conversation=ids)}
        renamed = {x["link"]["to"] for x in self._c.links(
            relation=self._c.superseding_relation(),
            to_any=sorted(named))} if named else set()
        return {c: c in named and c not in renamed for c in ids}

    def rename_conversation(self, conversation, name, *, by, because=None,
                            written_by=None) -> dict:
        """RENAME a Conversation. IDENTITY IS KEPT, as a Topic's is.

        The Conversation stays the entry it always was -- every post, link,
        placement and act still points at it -- and the new name is its next
        version, superseding the last; the old name is still in the record.
        A Conversation's name is a label for people, so renaming one is
        ungated, as a Topic's is: it takes effect when it is written, and the
        new version is established exactly when the one it replaces stood.
        Naming a provisionally named Conversation makes its name its own,
        even when the words are the same.

        Refused (`versions.Refused`) with nothing written: no name, no
        somebody, not a Conversation, or nothing changing.
        """
        from .versions import Refused, lineage
        if not by:
            raise Refused({"error": "a rename needs somebody who did it"})
        name = name.strip() if isinstance(name, str) else ""
        if not name:
            raise Refused({"error": "a conversation needs a name",
                           "conversation": conversation})
        sup = self._c.superseding_relation()
        with self._c.atomic():
            if not self.is_conversation(conversation):
                raise Refused(self.version_refusal(conversation) or {
                    "error": f"{conversation} is not a conversation in this "
                             "record", "conversation": conversation})
            head = lineage(self._c, conversation)["current"]
            was = (head.get("body") or {}).get("name")
            provisional = self.provisional([conversation])[conversation]
            if was == name and not provisional:
                raise Refused({"error": "that is already its name; nothing "
                                        "changed", "conversation": conversation,
                               "name": name})
            new = self._c.write(kind=CONVERSATION,
                                body={**(head.get("body") or {}), "name": name},
                                attributed_to=by, written_by=written_by)
            established = None
            if self._c.stands(head["id"])["stands"]:
                established = self._c.establish(
                    new, attributed_to=by, written_by=written_by,
                    reason="the current name of a Conversation; a name is a "
                           "label for people and approves nothing")
            link = self._c.write(body={"reason": because or "renamed"},
                                 attributed_to=by, written_by=written_by,
                                 link={"from": new, "to": head["id"],
                                       "relation": sup})
            act = self.record_act(
                actor=by, act=CONVERSATION_RENAMED, conversation=conversation,
                about=[conversation, head["id"], new], because=because or None,
                detail={"name": name, "was": was, "version": new,
                        "replaces": head["id"], "link": link,
                        "established": established,
                        "was_provisional": provisional})
        return {"conversation": conversation, "name": name, "was": was,
                "version": new, "replaces": head["id"], "link": link,
                "act": act, "provisional": False}

    def create_participant(self, alias, *, about="", attributed_to="human",
                           written_by=None) -> str:
        """Deliberately another durable Participant, even if the alias repeats.

        Separate from `resolve_participant` on purpose: making a second @Elena
        must be something somebody asked for, never something that happens.

        NEVER UNDER A RESERVED NAME, AND NEVER UNDER A FORMER ONE
        (`participant_alias_refusal`). Refused (`versions.Refused`) with
        nothing written.
        """
        from .versions import Refused
        refusal = self.participant_alias_refusal(alias)
        if refusal:
            raise Refused(refusal)
        return self._c.create_and_establish(
            kind=PARTICIPANT, body={"alias": alias, "about": about},
            attributed_to=attributed_to, written_by=written_by)

    def participant_alias_refusal(self, alias, *, for_participant=None
                                  ) -> dict | None:
        """Why no Participant may newly take this alias, or None.

        THREE REASONS, each said with what to do instead:
          * it is a FORMER alias of a renamed Participant: it still names that
            somebody in history, and anybody using it means them, so they are
            pointed at the current alias rather than handed a stranger;
          * it is NOT MADE OF THE ALLOWED CHARACTERS -- English letters,
            digits, `-` and `_`, starting with a letter
            (`participant_names.alias_problem`, owner's decision
            opr-938e0fa58007); the refusal says which are allowed;
          * it is RESERVED: it reads as a runtime or a model family
            (`participant_names.reserved_as`), so it would be taken for a
            choice of where work runs. Said beside the characters when both
            hold, so a caller always learns both.
        FORMER FIRST (review finding opr-faafddfea8de): the migration renames
        exactly the Participants whose names became reserved -- @Codex to
        @Quill -- so their former aliases are all reserved too, and a reserved
        refusal checked first would hide the one thing the caller needs, who
        @Codex is now. The pointer still says the name is reserved.
        `for_participant` is the one being renamed: taking back its own former
        alias is not taking somebody else's.
        """
        from .participant_names import ALLOWED, alias_problem, reserved_as
        hit = reserved_as(alias)
        problem = alias_problem(alias)
        key = _alias_key(alias)
        for pid, (now, former) in self._participant_aliases().items():
            if pid == for_participant or _alias_key(now) == key:
                continue
            if key in {_alias_key(a) for a in former}:
                return {"error": f"{alias} was renamed {now}; address {now} "
                                 "instead", "alias": alias,
                        "participant": pid, "renamed_to": now,
                        **({"reserved": hit} if hit else {})}
        if problem:
            return {"error": problem, "alias": alias, "allowed": ALLOWED,
                    **({"reserved": hit} if hit else {})}
        if hit:
            return {"error": f"{alias!r} reads as {hit!r}, which is a runtime "
                             "or model name; a Participant may not be called "
                             "by one, because a name is a label for somebody "
                             "and never chooses where work runs. Choose "
                             "another name", "alias": alias, "reserved": hit}
        return None

    def _participant_aliases(self) -> dict:
        """participant -> (current alias, [former aliases]) for every
        Participant that was ever renamed."""
        from .versions import lineage
        out: dict = {}
        for p in self.all_participants():
            if not p.get("revision"):
                continue
            versions = lineage(self._c, p["id"])["versions"]
            names = [(v.get("body") or {}).get("alias") for v in versions]
            out[p["id"]] = (names[-1], [n for n in names[:-1] if n])
        return out

    def participants_named(self, alias) -> list[str]:
        """EVERY durable Participant with this alias. Usually one.

        `find_participant` below answers the different question a
        composer asks -- give me the Bob this name means -- and answers it
        with the first, deliberately, so that asking twice gets the same
        Bob. That is right for summoning and wrong for anything that needs
        to know WHICH Participant it is talking about: an alias is a
        label and two deliberate Participants may share one. This says how
        many there are, so a caller can decline to guess.

        The CURRENT alias: a renamed Participant answers to its new one.
        """
        return [e["id"] for e in self.all_participants()
                if e["body"]["alias"] == alias]

    def find_participant(self, alias) -> str | None:
        found = self.participants_named(alias)
        return found[0] if found else None

    def resolve_participant(self, alias, **kw) -> str:
        """The same durable Participant, or a first one. Never a duplicate.

        REFUSED (`versions.Refused`), never resolved, when the alias is a
        former one (pointing at the current), not of the allowed characters,
        or reserved. An EXISTING Participant whose alias is no longer one a
        Participant may take -- named before the rule, or before the runtime
        it clashes with was registered -- is refused too, with what the owner
        must do (`refuse_reserved`)."""
        found = self.find_participant(alias)
        if found is None:
            return self.create_participant(alias, **kw)
        self.refuse_reserved(found)
        return found

    def refuse_reserved(self, participant) -> None:
        """Refuse (`versions.Refused`) new addressing BY NAME of a Participant
        whose CURRENT alias is reserved or not of the allowed characters,
        telling the owner to rename it. A Participant named before the rule,
        or before the runtime it clashes with was registered, stays in the
        record and in history, and work addressed to it by id still reaches
        it; it is only not addressed again under that name."""
        from .participant_names import ALLOWED, alias_problem, reserved_as
        from .versions import Refused
        alias = self.alias(participant)
        hit = reserved_as(alias)
        if alias_problem(alias):
            raise Refused({
                "error": f"{alias!r} is no longer a name a Participant may be "
                         f"called by: a name may use only {ALLOWED}. The "
                         "owner must rename this Participant before it is "
                         "addressed by name again", "alias": alias,
                "participant": participant, "allowed": ALLOWED,
                **({"reserved": hit} if hit else {}),
                "rename": f"/api/participants/{participant}/rename"})
        if hit:
            raise Refused({
                "error": f"{alias} is named like the runtime or model "
                         f"{hit!r}, which a Participant may no longer be; "
                         "the owner must rename this Participant before it "
                         "is addressed again", "alias": alias,
                "participant": participant, "reserved": hit,
                "rename": f"/api/participants/{participant}/rename"})

    def rename_participant(self, participant, alias, *, by, because=None,
                           written_by=None) -> dict:
        """RENAME a Participant. IDENTITY IS KEPT, as a Conversation's is.

        The Participant stays the entry it always was -- every post, act,
        delegation and declaration still points at it -- and the new alias is
        its next version, superseding the last; the old alias is still in the
        record, and history still shows who it was. From then on the old
        alias is refused for new addressing, with the new one named
        (`participant_alias_refusal`).

        AN OWNER ACT. This layer does not know who the owner is, so every door
        that reaches it asks first (`/api/participants/<id>/rename`,
        `bootstrap.rename_participants`).

        Refused (`versions.Refused`) with nothing written: no somebody, no
        alias, not a Participant, nothing changing, the alias taken by
        another Participant, reserved, or a former alias of another.
        """
        from .versions import Refused, lineage
        if not by:
            raise Refused({"error": "a rename needs somebody who did it"})
        alias = alias.strip() if isinstance(alias, str) else ""
        if not alias.lstrip("@"):
            raise Refused({"error": "a participant needs a name",
                           "participant": participant})
        sup = self._c.superseding_relation()
        with self._c.atomic():
            if not self._is_kind(participant, PARTICIPANT):
                raise Refused({"error": f"{participant} is not a Participant "
                                        "in this record",
                               "participant": participant})
            head = lineage(self._c, participant)["current"]
            was = (head.get("body") or {}).get("alias")
            if isinstance(was, str) and was.startswith("@") \
                    and not alias.startswith("@"):
                alias = "@" + alias
            if was == alias:
                raise Refused({"error": "that is already its name; nothing "
                                        "changed", "participant": participant,
                               "alias": alias})
            taken = [p["id"] for p in self.all_participants()
                     if p["id"] != participant
                     and _alias_key(p["body"]["alias"]) == _alias_key(alias)]
            if taken:
                raise Refused({"error": f"{alias} is already the name of "
                                        "another Participant",
                               "participant": participant, "alias": alias,
                               "taken_by": taken})
            refusal = self.participant_alias_refusal(
                alias, for_participant=participant)
            if refusal:
                raise Refused({**refusal, "participant": participant})
            new = self._c.write(kind=PARTICIPANT,
                                body={**(head.get("body") or {}),
                                      "alias": alias},
                                attributed_to=by, written_by=written_by)
            established = None
            if self._c.stands(head["id"])["stands"]:
                established = self._c.establish(
                    new, attributed_to=by, written_by=written_by,
                    reason="the current alias of a Participant; a name is a "
                           "label for somebody and approves nothing")
            link = self._c.write(body={"reason": because or "renamed"},
                                 attributed_to=by, written_by=written_by,
                                 link={"from": new, "to": head["id"],
                                       "relation": sup})
            act = self.record_act(
                actor=by, act=PARTICIPANT_RENAMED,
                about=[participant, head["id"], new], because=because or None,
                detail={"participant": participant, "alias": alias,
                        "was": was, "version": new, "replaces": head["id"],
                        "link": link, "established": established})
        return {"participant": participant, "alias": alias, "was": was,
                "version": new, "replaces": head["id"], "link": link,
                "act": act}

    def define_persona(self, name, behaviour, *, about="", attributed_to="human",
                       written_by=None) -> str:
        return self._c.create_and_establish(
            kind=PERSONA, body={"name": name, "behaviour": behaviour,
                                "about": about},
            attributed_to=attributed_to, written_by=written_by)

    def propose_persona(self, name, behaviour, *, about="",
                        attributed_to="human", written_by=None) -> str:
        """A Persona WRITTEN and not established. Candidate material.

        `define_persona` is a human creating one directly. This is the other
        half, and it exists because something that may not establish still
        needs to be able to put a Persona forward: the entry is in the record,
        it is addressable and arguable, and `compose` withholds it with the
        reason until a person establishes it. Proposing is not a weaker
        establishment; it is a different act with no standing at all.
        """
        return self._c.write(
            kind=PERSONA, body={"name": name, "behaviour": behaviour,
                                "about": about},
            attributed_to=attributed_to, written_by=written_by)

    def join(self, participant, conversation, *, attributed_to="human",
             written_by=None) -> str:
        return self._c.write(
            body={"reason": "takes part"}, attributed_to=attributed_to,
            written_by=written_by,
            link={"from": participant, "to": conversation,
                  "relation": PARTICIPATES_IN})

    # -- who carries a request addressed to nobody ---------------------------
    #
    # ONE LINK, AND NOTHING ELSE IS NEW. The designation is a Link of an
    # ordinary Relation whose target is an ordinary Persona entry, so it needs
    # no Kind, no table, and -- the reason this shape was chosen over the
    # obvious one -- no placement at all: who carries intake is a fact about a
    # Participant, not material that applies somewhere, so the whole-Brain
    # placement destination (`whole_brain`) is not used for it. Standing and
    # supersession are the spine's, unchanged. Nothing below names an alias
    # or a Persona.

    def designate_intake_carrier(self, participant, persona, *,
                                 attributed_to="human", written_by=None,
                                 reason="carries requests addressed to nobody"
                                 ) -> str:
        """Establish that this Participant carries unaddressed requests, as
        that Persona. A deliberate act of whoever may establish.

        Atomic: a link in the record without the act that established it would
        read as a designation nobody made.
        """
        if not self._is_kind(participant, PARTICIPANT):
            raise ValueError("an intake carrier must be a Participant")
        if not self._is_kind(persona, PERSONA):
            raise ValueError("an intake carrier is designated wearing a Persona")
        with self._c.atomic():
            link = self._c.write(
                body={"reason": reason}, attributed_to=attributed_to,
                written_by=written_by,
                link={"from": participant, "to": persona,
                      "relation": CARRIES_INTAKE})
            self._c.establish(link, attributed_to=attributed_to,
                              written_by=written_by, reason=reason)
        return link

    def intake_designations(self) -> list[dict]:
        """Every designation ever written, with what the record says of it."""
        out = []
        for e in self._c.links(relation=CARRIES_INTAKE):
            standing = self._c.stands(e["id"])
            out.append({
                "designation": e["id"],
                "participant": e["link"]["from"],
                "persona": e["link"]["to"],
                "stands": standing["stands"],
                "established_by": standing["established_by"],
                "superseded_by": standing["superseded_by"],
                "attributed_to": e.get("attributed_to"),
                "written_by": e.get("written_by"),
                "at": e.get("recorded_at"),
            })
        return sorted(out, key=lambda r: r["at"] or 0)

    def carry_intake_forward(self, predecessor, replacement, *, by,
                             written_by=None) -> list[str]:
        """A Persona replaced by another Persona takes its intake designation
        with it. Returns the new designation(s) written; usually none.

        THE BUG THIS CLOSES (2026-10-07): editing Caretaker's behaviour
        superseded the Persona its designation named, `intake_carrier()`
        answered "persona does not stand", and every unaddressed post went to
        nobody until somebody re-designated by hand. Nothing had decided that.

        EXPLICIT, NOT FOLLOWED AT READ TIME. Each standing `carries-intake`
        link to `predecessor` gets a successor link from the same Participant
        to `replacement`, established, superseding the old one -- the shape
        `designate_intake_carrier` and a hand re-designation write. The record
        still names the exact Persona version designated, and `intake_carrier`
        keeps refusing a designation whose Persona does not stand.

        CALLED WHERE A SUPERSESSION TAKES EFFECT, inside its atomic act, by
        whoever made it: the `supersede`, `establish-replacement` and `revise`
        doors, and `versions.edit` when it replaces directly. A PROPOSED
        replacement carries nothing -- the old Persona still stands, so its
        designation still resolves -- until `establish-replacement` approves
        it. A raw spine write of a `supersedes` link carries nothing either;
        the spine knows no Kind.

        NO CARRY-FORWARD unless both ends are Personas: a Persona ended by a
        deletion record, or by material of another Kind, has no Persona to
        designate, so its designation stays where it was and stops resolving,
        which is what `intake_carrier` already says of it.
        """
        if predecessor == replacement or not (
                self._is_kind(predecessor, PERSONA)
                and self._is_kind(replacement, PERSONA)):
            return []
        reason = "the designated Persona was replaced by this version"
        written = []
        with self._c.atomic():
            # AND WHAT THE PERSONA CARRIES GOES WITH IT, at the same moment and
            # by the same doors. See `carry_placements_forward`.
            self.carry_placements_forward(predecessor, replacement, by=by,
                                          written_by=written_by)
            for old in self._c.links(relation=CARRIES_INTAKE, to=predecessor):
                if not self._c.stands(old["id"])["stands"]:
                    continue
                link = self._c.write(
                    body={"reason": reason}, attributed_to=by,
                    written_by=written_by,
                    link={"from": old["link"]["from"], "to": replacement,
                          "relation": CARRIES_INTAKE})
                self._c.establish(link, attributed_to=by,
                                  written_by=written_by, reason=reason)
                self._c.write(
                    body={"reason": "carried forward to the Persona's new "
                                    "version"},
                    attributed_to=by, written_by=written_by,
                    link={"from": link, "to": old["id"],
                          "relation": self._c.superseding_relation()})
                written.append(link)
        return written

    def carry_placements_forward(self, predecessor, replacement, *, by,
                                 written_by=None) -> list[str]:
        """Material placed ON a Persona is placed on its new version too.
        Returns the new placement links written; usually none.

        THE SAME GAP `carry_intake_forward` CLOSED, ONE RELATION OVER. A
        Persona carries Disciplines by their being placed on it -- a
        `scoped-to` link whose destination is the Persona entry -- and editing
        the Persona replaces that entry. Without this, approving a reworded
        Persona would silently drop every Discipline it carried, and nothing
        would have decided that.

        EXPLICIT, AND THE SAME SHAPE: each placement on `predecessor` that
        nothing has ended gets a successor link from the same material to
        `replacement`, superseding the old link, so the record says which
        Persona version carried it when. Called from `carry_intake_forward`,
        which every door that makes a Persona supersession take effect calls
        inside its own atomic act; a PROPOSED replacement carries nothing,
        because the old Persona still stands and still carries it.
        """
        if predecessor == replacement or not (
                self._is_kind(predecessor, PERSONA)
                and self._is_kind(replacement, PERSONA)):
            return []
        reason = "carried by the Persona's new version"
        written = []
        with self._c.atomic():
            for old in self._links_now(SCOPED_TO, to=predecessor):
                link = self._c.write(
                    body={"reason": reason}, attributed_to=by,
                    written_by=written_by,
                    link={"from": old["link"]["from"], "to": replacement,
                          "relation": SCOPED_TO})
                self._c.write(
                    body={"reason": "carried forward to the Persona's new "
                                    "version"},
                    attributed_to=by, written_by=written_by,
                    link={"from": link, "to": old["id"],
                          "relation": self._c.superseding_relation()})
                written.append(link)
        return written

    def persona_carried(self, persona) -> list[dict]:
        """What is placed ON this Persona now and directs work: what an
        execution operating as it is carried. The same question
        `placed_procedural` asks of a Conversation, asked of a Persona."""
        if not persona or not self._is_kind(persona, PERSONA):
            return []
        return self.placed_procedural(persona)

    def governed_named(self, expectation) -> list[str]:
        """Which governed material this request names: references only, the
        newest assigning act that says so, else the request's own record.

        THE ONE READ, HERE so that what dispatch delivers and what the work
        status reads as governing a request cannot disagree; the reasons it
        reads the record this way (newest assignment wins, PRESENT not
        truthy, nothing resolved or filtered) are given where dispatch asks
        it, `mentis.web.dispatch._governed_for`.
        """
        if not expectation:
            return []
        for a in sorted(self.history(caused_by=expectation),
                        key=lambda a: a["at"], reverse=True):
            if a["act"] == "expectation-assigned" and "governed" in (
                    a["detail"] or {}):
                return list(a["detail"]["governed"] or ())
        detail = ((self._act(expectation) or {}).get("detail") or {})
        return list(detail.get("governed") or ()) if "governed" in detail else []

    def governing_now(self, conversation, named=(), persona=None) -> set[str]:
        """Every piece of governing material work here would be delivered and
        that stands now: placed here, placed on the whole Brain, named for the
        work, and carried by the Persona it is done as. See
        `mentis.web.dispatch.governing_ids`, which asks this."""
        if conversation:
            holding = {r["entry"] for r in self.governs(conversation)["governing"]}
        else:
            holding = {e["id"] for e in self.placed_brain_wide()
                       if self._c.stands(e["id"])["stands"]}
        holding |= {e for e in named if self._c.stands(e)["stands"]}
        if persona and self._c.read([persona]) and self._c.stands(persona)["stands"]:
            holding |= {e["id"] for e in self.persona_carried(persona)
                        if self._c.stands(e["id"])["stands"]}
        return holding

    def drawn_on(self, eid) -> list[dict]:
        """What this material draws on now, one row per link: the target, its
        role and label, and whether it is a held artifact or an entry.

        A link somebody ended is not listed, and nor is a target whose line
        was deleted -- it is not new support for anything. Oldest first, which
        is the order the author added them in.
        """
        from .versions import inert_refusal
        out = []
        for x in self._links_now(DRAWS_ON, frm=eid):
            to = x["link"]["to"]
            if inert_refusal(self._c, to):
                continue
            got = self._c.read([to])
            if not got:
                continue
            body = x.get("body") or {}
            out.append({"link": x["id"], "to": to,
                        "role": body.get("role"),
                        "label": body.get("label") or "",
                        "artifact": got[0].get("family") == "admission"})
        return out

    def _title_of(self, entry) -> str:
        """`name — about` for material whose Kind declares a `form`, so a
        Discipline is delivered with what it is called and when it applies;
        empty otherwise, so every other Kind renders exactly as before."""
        fields, form = rendering_of(self._c, self._kind_of(entry))
        if not form:
            return ""
        body = entry.get("body") or {}
        said = [str(body[f]).strip() for f in ("name", "about")
                if f in fields and isinstance(body.get(f), str)
                and body[f].strip()]
        return " — ".join(said)

    def named_ref(self, ref) -> str:
        """`Name (ent-…)` for a reference a body holds: a Participant by its
        alias, a Persona or Discipline by its name, anything else by the
        first words it says. BOTH, always: a name to read and a reference to
        act on. Says when the material does not stand, because it then
        reaches nobody it is handed to."""
        got = self._c.read([ref]) if isinstance(ref, str) else []
        if not got:
            return f"{ref} (not in this record)"
        body = got[0].get("body") or {}
        if self._is(got[0], PARTICIPANT):
            body = {**body, "alias": self.alias(ref)}    # its CURRENT alias
        name = (body.get("alias") or body.get("name")
                or (content_of(got[0]) or "").strip().split("\n")[0][:60]
                or self._kind_of(got[0]))
        standing = self._c.stands(ref)
        held = ("" if self._is(got[0], PARTICIPANT) or standing["stands"]
                else ", superseded" if standing["superseded_by"]
                else ", not established")
        return f"{name} ({ref}{held})"

    def _said_fields(self, entry, form) -> dict:
        """The fields `content_of` cannot put into words alone, because they
        name other entries: a `participant` or `persona` input by name and
        reference, and an `activities` row group laid out one activity at a
        time with its Disciplines named, followed by how a run delegates one.
        Asked of the Kind's `form`, by input, never of its name."""
        body = entry.get("body") or {}
        out = {}
        for name, f in _form_items(form):
            value = body.get(name)
            if not value:
                continue
            how = f.get("input")
            if how in (PARTICIPANT_INPUT, PERSONA_INPUT) and isinstance(value, str):
                out[name] = self.named_ref(value)
            elif how == ROW_GROUP and isinstance(value, list):
                out[name] = self._said_activities(entry["id"], value)
        return out

    def _said_discipline(self, ref) -> str:
        """An activity's Discipline as the carrier reads it: the CURRENT
        version (`current_of`), by name and reference, and plainly what the
        procedure itself pins when that was replaced -- so the carrier hands a
        child the version that will actually reach it, and is told when none
        will."""
        cur = current_of(self._c, ref)
        if cur["entry"] is None:
            return f"{ref} ({cur['why']}; it reaches nobody)"
        got = self._c.read([cur["entry"]])[0]
        body = got.get("body") or {}
        name = body.get("name") or (content_of(got) or "").strip()[:60] or ref
        notes = []
        if cur.get("superseded_by"):
            notes.append(f"this procedure names {ref}, superseded by it")
        if not cur["stands"]:
            notes.append("not established; it reaches nobody until it is")
        return f"{name} ({cur['entry']}" + (
            "; " + "; ".join(notes) if notes else "") + ")"

    def _said_activities(self, ref, rows) -> str:
        """An `activities` value as the carrier reads it. Numbered for
        reading, never as an order anything follows."""
        lines = []
        for i, row in enumerate(r for r in rows if isinstance(r, dict)):
            key = row.get("key") or "?"
            lines.append(f"{i + 1}. {key} — {str(row.get('what') or '').strip()}")
            who = row.get("who") or {}
            said = ([f"as Persona {self.named_ref(who['persona'])}"]
                    if who.get("persona") else []) + (
                [self.named_ref(who["participant"])]
                if who.get("participant") else []) + (
                [f"role: {who['role']}"] if who.get("role") else [])
            if said:
                lines.append("   Carried by: " + "; ".join(said))
            ds = [d for d in row.get("disciplines") or () if isinstance(d, str)]
            if ds:
                lines.append("   Disciplines: "
                             + "; ".join(self._said_discipline(d) for d in ds))
            if row.get("done_when"):
                lines.append(f"   Done when: {str(row['done_when']).strip()}")
            if row.get("coordinates"):
                lines.append("   Coordinates: carrying it out takes work this "
                             "run does not carry (such as picking up "
                             "discovered work), which needs the request to "
                             "have been granted `coordinate`")
            lines.append(f'   Delegate it with activity: "{ref}#{key}"')
        lines.append(
            "How these are carried out: hand an activity on with `delegate`, "
            f'naming `activity: "{ref}#<key>"` and passing THAT activity\'s '
            "Disciplines (the references above) in `governed`; this "
            "procedure itself is not passed on. Naming an activity labels the "
            "delegation and changes nothing about how the work runs. Nothing "
            "moves from one activity to the next by itself: wait for what "
            "you need back (`return_to_me`, `await_work`), ask any decision "
            "reserved to the owner with `request_decision` and never make it "
            "yourself. How far the work has got is read from the record, not "
            "kept anywhere.")
        return "\n".join(lines)

    def _said_with_links(self, entry) -> str:
        """What a piece of governing material says when it is delivered: its
        declared fields, labelled (`content_of`), then what it draws on,
        LISTED and never inlined.

        BY REFERENCE, ONE LINE EACH, because an example or a reference may be
        long and is needed only sometimes. The line says how to read it: an
        entry with `resolve`, a held artifact with `read_artifact`, which the
        artifact offer for this run admits (`artifacts.available`,
        `drawn-on-by-governed`).
        """
        fields, form = rendering_of(self._c, self._kind_of(entry))
        said = content_of(entry, fields, form, self._said_fields(entry, form))
        rows = self.drawn_on(entry["id"])
        if not rows:
            return said
        lines = ["Draws on (listed by reference, not included; read one when "
                 "it is needed):"]
        for r in rows:
            label = f' "{r["label"]}"' if r["label"] else ""
            how = "read_artifact" if r["artifact"] else "resolve"
            lines.append(f"[{r['role'] or 'reference'}] {r['to']}{label} "
                         f"— {how}")
        return (said + "\n\n" if said else "") + "\n".join(lines)

    # -- how a Participant is pictured -----------------------------------------
    #
    # ONE LINK, THE SAME SHAPE AS THE INTAKE DESIGNATION: an ordinary Relation
    # from the Participant to an ordinary Admission, established by whoever
    # chose it. No field is added to the Participant Kind -- a picture is not
    # part of who somebody is, and a Kind's fields are. Replacing it is an
    # ordinary supersession, so what somebody was shown as last month is
    # still answerable.

    def set_avatar(self, participant, admission, *, by, written_by=None,
                   reason="chosen as this Participant's picture") -> str:
        """Picture this Participant with that held image, superseding
        whatever pictured it until now. Atomic: a new picture that did not
        replace the old one would leave two standing and neither chosen."""
        if not self._is_kind(participant, PARTICIPANT):
            raise ValueError("only a Participant is pictured")
        got = self._c.read([admission])
        if not got or got[0]["family"] != "admission":
            raise ValueError(f"{admission} is not a held artifact")
        with self._c.atomic():
            before = self._links_now(PICTURED_BY, frm=participant)
            link = self._c.write(
                body={"reason": reason}, attributed_to=by,
                written_by=written_by,
                link={"from": participant, "to": admission,
                      "relation": PICTURED_BY})
            self._c.establish(link, attributed_to=by, written_by=written_by,
                              reason=reason)
            for old in before:
                self._c.write(
                    body={"reason": "replaced by another picture"},
                    attributed_to=by, written_by=written_by,
                    link={"from": link, "to": old["id"],
                          "relation": self._c.superseding_relation()})
        return link

    def clear_avatar(self, participant, *, by, written_by=None,
                     because="back to the default picture") -> list[dict]:
        """End whatever pictures this Participant. Empty when nothing did."""
        with self._c.atomic():
            return [self._end_link(x["id"], by=by, because=because,
                                   written_by=written_by)
                    for x in self._links_now(PICTURED_BY, frm=participant)]

    def avatar_of(self, participant) -> str | None:
        """The Admission this Participant is pictured with now, or None.

        Only a link that STANDS counts: written and never established is
        somebody's suggestion, not a choice. Several standing cannot come
        from `set_avatar`; if the record holds them anyway the latest is
        shown, because a picture is presentation and nothing depends on it.
        """
        now = [x for x in self._c.links(relation=PICTURED_BY, frm=participant)
               if self._c.stands(x["id"])["stands"]]
        if not now:
            return None
        return max(now, key=lambda x: x.get("recorded_at") or 0)["link"]["to"]

    def declare_runtime_default(self, participant, runtime, *, by,
                                written_by=None,
                                because="declared this Participant's default "
                                        "runtime") -> str:
        """Declare which runtime runs this Participant's work when the work
        names none, superseding what was declared before. `None` declares
        runtime-auto. Atomic, for the same reason a picture is: two standing
        declarations would leave neither chosen.

        IDENTITY AND RUNTIME STAY SEPARATE. This writes a declaration ABOUT
        the Participant; the Participant entry itself is untouched, and nothing
        anywhere derives a runtime from its alias.
        """
        if not self._is_kind(participant, PARTICIPANT):
            raise ValueError("only a Participant has a default runtime")
        runtime = (str(runtime).strip() or None) if runtime else None
        with self._c.atomic():
            before = [d for d in self._runtime_defaults(participant)
                      if d["stands"]]
            eid = self._c.write(kind=RUNTIME_DEFAULT,
                                body={"participant": participant,
                                      "runtime": runtime},
                                attributed_to=by, written_by=written_by)
            self._c.establish(eid, attributed_to=by, written_by=written_by,
                              reason=because)
            for old in before:
                self._c.write(
                    body={"reason": "replaced by a later declaration"},
                    attributed_to=by, written_by=written_by,
                    link={"from": eid, "to": old["declaration"],
                          "relation": self._c.superseding_relation()})
        return eid

    def _runtime_defaults(self, participant=None) -> list[dict]:
        """Every declaration ever written -- for one Participant, or for all
        when none is named -- with whether it stands."""
        out = []
        for e in self._c.entries_of_kind(RUNTIME_DEFAULT):
            if participant and e["body"].get("participant") != participant:
                continue
            standing = self._c.stands(e["id"])
            out.append({"declaration": e["id"],
                        "participant": e["body"].get("participant"),
                        "runtime": e["body"].get("runtime"),
                        "stands": standing["stands"],
                        "by": e.get("attributed_to"),
                        "at": e.get("recorded_at")})
        return out

    def runtime_default_of(self, participant) -> dict | None:
        """The declaration in force for this Participant, or None when nobody
        declared one. A declaration whose `runtime` is None is runtime-auto,
        said deliberately -- which is a different answer from nobody saying.
        Only a declaration that STANDS counts."""
        now = [d for d in self._runtime_defaults(participant) if d["stands"]]
        return max(now, key=lambda d: d["at"] or 0) if now else None

    def runtime_defaults_now(self) -> dict:
        """The declaration in force for every Participant that has one, read
        once. For a surface listing many names, which would otherwise ask
        `runtime_default_of` once per name."""
        now: dict = {}
        for d in self._runtime_defaults():
            if d["stands"] and (d["participant"] not in now or (d["at"] or 0)
                                > (now[d["participant"]]["at"] or 0)):
                now[d["participant"]] = d
        return now

    def intake_carrier(self) -> dict:
        """Who carries an unaddressed request here, or why nobody does.

        THREE ANSWERS, NEVER COLLAPSED. Exactly one designation in force is
        resolved. None in force is unresolved-because-none. More than one is
        unresolved-because-several, and is NOT a tie broken by recency: two
        standing designations mean a person has said two things and only a
        person can say which.

        A designation whose Persona no longer stands does not resolve either.
        The designation says "as that Persona", so a Persona that has been
        superseded or never established makes the whole designation unusable
        rather than half-usable -- dispatching the Participant without the
        behaviour it was designated to wear is not the thing that was
        established. Replacing the Persona with a new version through any door
        that ends material carries the designation forward explicitly
        (`carry_intake_forward`); nothing here follows the chain.
        """
        standing = [r for r in self.intake_designations() if r["stands"]]
        if not standing:
            wrote = len(self.intake_designations())
            return {"resolved": False, "reason": "none in force",
                    "detail": (f"{wrote} designation(s) written, none standing"
                               if wrote else
                               "no Participant is designated to carry requests "
                               "addressed to nobody in this Brain"),
                    "candidates": []}
        if len(standing) > 1:
            return {"resolved": False, "reason": "more than one in force",
                    "detail": ("several designations stand at once; which one "
                               "applies is a decision only a person can make"),
                    "candidates": [r["designation"] for r in standing]}
        row = standing[0]
        if not self._c.stands(row["persona"])["stands"]:
            return {"resolved": False, "reason": "persona does not stand",
                    "detail": ("the designated Persona is not established, or "
                               "has been superseded, so the designation cannot "
                               "be honoured as it was made"),
                    "candidates": [row["designation"]]}
        return {"resolved": True, "designation": row["designation"],
                "participant": row["participant"], "persona": row["persona"],
                "alias": self.alias(row["participant"])}

    def instruct_conversation(self, conversation, instruction, *, about="",
                              attributed_to="human", written_by=None) -> str:
        """Durable behavioural material placed at one Conversation.

        Placement is the `scoped-to` Link. There is no instructions store.
        """
        with self._c.atomic():
            eid = self._c.create_and_establish(
                kind=CONVERSATION_INSTRUCTION,
                body={"text": instruction, "about": about},
                attributed_to=attributed_to, written_by=written_by)
            self._c.write(body={"reason": "applies in this conversation"},
                          attributed_to=attributed_to, written_by=written_by,
                          link={"from": eid, "to": conversation,
                                "relation": SCOPED_TO})
        return eid

    # -- the whole Brain as a placement destination ---------------------------
    #
    # NOTHING HERE IS A SECOND GOVERNANCE SYSTEM. Placing on the whole Brain is
    # the `scoped-to` link every placement is, written to one deliberate
    # destination entry. Standing, supersession, successors inheriting their
    # predecessor's placements, and ending a placement are all the machinery a
    # Conversation placement already uses. What the destination adds is reach:
    # `compose` carries what is placed there into every Conversation and into
    # Brain-scope work. A Conversation id that is merely absent means nothing.

    def whole_brain(self, *, create=False, by=None, written_by=None
                    ) -> str | None:
        """The whole-Brain destination, or None when nobody has placed
        anything on the whole Brain yet. `create` writes it the first time an
        owner places something there, and never otherwise."""
        found = sorted(self._c.entries_of_kind(WHOLE_BRAIN),
                       key=lambda e: (e.get("recorded_at") or 0, e["id"]))
        if found:
            return found[0]["id"]
        if not create:
            return None
        if not by:
            raise ValueError("the whole-Brain destination is written by "
                             "whoever first places material on it")
        return self._c.create_and_establish(
            kind=WHOLE_BRAIN,
            body={"name": WHOLE_BRAIN_NAME,
                  "about": "every Conversation in this Brain, now and later, "
                           "and work at Brain scope"},
            attributed_to=by, written_by=written_by)

    def is_whole_brain(self, eid) -> bool:
        return bool(eid) and eid in whole_brain_ids(self._c)

    def placement_links_now(self, entry, where=None) -> list[dict]:
        """The placement links from this material that nothing has ended,
        optionally only those to `where`."""
        return self._links_now(SCOPED_TO, frm=entry, to=where)

    def end_placement(self, entry, where, *, by, because,
                      written_by=None) -> dict | None:
        """REMOVE a placement: end every standing `scoped-to` link from this
        material to `where`, append-only, exactly as un-filing ends a filing.

        None when it is not placed there now, and nothing is written. The
        material itself, its standing and its other placements are untouched;
        the ended links stay in the record and read as history. CHANGING a
        placement is this followed by placing it somewhere else -- two acts,
        each with its reason.
        """
        if not by:
            raise ValueError("ending a placement needs somebody who did it")
        if not because:
            raise ValueError("ending a placement needs a reason")
        with self._c.atomic():
            now = self.placement_links_now(entry, where)
            if not now:
                return None
            ended = [self._end_link(x["id"], by=by, because=because,
                                    written_by=written_by) for x in now]
            act = self._c.record_operational(
                actor=by, act="placement-ended",
                conversation=(where if self._is_kind(where, CONVERSATION)
                              else None),
                because=because, about=[entry, where],
                detail={"entry": entry, "where": where,
                        "whole_brain": self.is_whole_brain(where),
                        "ended": ended})
        return {"entry": entry, "where": where, "ended": ended, "act": act}

    def whole_brain_refusal(self, eid) -> dict | None:
        return whole_brain_refusal(self._c, eid)

    def placements_now(self, entry) -> list[str]:
        return placements_now(self._c, entry)

    def place(self, entry, where=None, *, whole_brain=False, by, because,
              written_by=None) -> dict:
        """Place material at a Conversation or on the whole Brain.

        Placement is the `scoped-to` link, written to one deliberate destination
        entry, with attribution, reason and a `material-placed` act.
        """
        if not by:
            raise ValueError("placing material needs somebody who did it")
        if not because:
            raise ValueError("placing material needs a reason")
        if whole_brain and where:
            raise ValueError("a placement names one destination: a where, or whole_brain, not both")
        if not whole_brain and (not isinstance(where, str) or not where.strip()):
            raise ValueError("a placement names where it applies, in where, or whole_brain=True")

        with self._c.atomic():
            if not whole_brain:
                where = where.strip()
                if not self._c.read([where]):
                    raise ValueError("the record holds no such entry, so nothing can be placed at it")
            refusal = declared_placement_refusal(
                self._c, entry, None if whole_brain else where)
            if refusal:
                raise ValueError(refusal["error"])
            brain_wide = whole_brain or self.is_whole_brain(where)
            if brain_wide:
                refusal = self.whole_brain_refusal(entry)
                if refusal:
                    raise ValueError(refusal["error"])
                where = self.whole_brain(create=True, by=by,
                                         written_by=written_by)
                already = self.placement_links_now(entry, where)
            else:
                already = None
            if already:
                # Placed on the whole Brain now: saying it twice writes nothing.
                return {"entry": entry, "where": where,
                        "whole_brain": brain_wide,
                        "placement": already[-1]["id"],
                        "already": True, "act": None,
                        "standing": self._c.stands(entry)}

            link = self._c.write(
                body={"reason": because}, attributed_to=by,
                written_by=written_by,
                link={"from": entry, "to": where, "relation": SCOPED_TO})
            oid = self.record_act(
                actor=by, act="material-placed", about=[entry, where],
                because=because, detail={"link": link, "where": where,
                                         **({"whole_brain": True}
                                            if brain_wide else {})})
            return {"entry": entry, "where": where, "placement": link,
                    "whole_brain": brain_wide,
                    "act": oid, "already": False,
                    "standing": self._c.stands(entry)}

    # -- topics -------------------------------------------------------------

    def open_topic(self, conversation, name, *, about="",
                   attributed_to="human", written_by=None) -> str:
        """A Topic inside one Conversation. Its NAME is a label, not identity.

        Two Conversations may each have a Topic called "Planning" and they are
        two different Topics, because identity is the entry id.
        """
        with self._c.atomic():
            tid = self._c.create_and_establish(
                kind=TOPIC, body={"name": name, "about": about},
                attributed_to=attributed_to, written_by=written_by)
            self._c.write(body={"reason": "organises this conversation"},
                          attributed_to=attributed_to, written_by=written_by,
                          link={"from": tid, "to": conversation,
                                "relation": TOPIC_OF})
        return tid

    def topics(self, conversation) -> list[dict]:
        """Each Topic under its CURRENT name: identity stays the entry every
        filing points at, and a renamed Topic reads as its latest version."""
        from .versions import presented
        return [presented(self._c, t)
                for t in self._c.read(self._linked(TOPIC_OF, to=conversation))]

    def edit_topic(self, topic, *, by, name=None, about=None, because=None,
                   written_by=None) -> dict:
        """Rename a Topic, or change what it is about. IDENTITY IS KEPT.

        The Topic stays the entry it always was -- every filing, every inline
        reference and every Turn count still points at it -- and the new
        name is its next version, superseding the last one. Not delete and
        recreate: nothing is re-filed, and the old name is still in the
        record. A Topic's name is "a label for people", so renaming one is
        ungated: it takes effect when it is written.
        """
        from .versions import edit
        if self.conversation_of_topic(topic) is None:
            raise ValueError("no such topic")
        fields = {k: v for k, v in (("name", name), ("about", about))
                  if v is not None}
        if "name" in fields:
            fields["name"] = (fields["name"] or "").strip()
            if not fields["name"]:
                raise ValueError("a topic needs a name")
        return edit(self, topic, by=by, fields=fields, because=because,
                    written_by=written_by)

    def conversation_of_topic(self, topic) -> str | None:
        found = self._linked(TOPIC_OF, frm=topic)
        return found[0] if found else None

    def conversation_of(self, contribution) -> str | None:
        # Once per reading: every Turn number shown is found through it.
        if not isinstance(contribution, str):
            found = self._linked(IN_CONVERSATION, frm=contribution)
            return found[0] if found else None
        return self._recall(("conversation_of", contribution), lambda: next(
            iter(self._linked(IN_CONVERSATION, frm=contribution)), None))

    def assign_topic(self, contribution, topic, *, attributed_to="human",
                     written_by=None) -> str:
        """Associate a contribution with a Topic. Nothing is moved or copied.

        Refused across Conversations -- a Topic organises one Conversation, and
        a contribution from another one is not a focus question but a mistake.
        THE ONE EXCEPTION IS A LINK: a contribution currently linked into that
        Conversation (`link_into`) is shown there, so it may be filed under
        that Conversation's Topics. Ending the link ends those filings.

        FILED ONCE AT A TIME. While a filing under this Topic is in force, a
        second one writes nothing and returns the link that already says so:
        it would say the same thing twice with two different who-and-whens.
        Once it has been UN-FILED (`end_filing`), filing again writes a new
        link with its own who and when -- the ended one is not restored in
        place, exactly as deleted material never is.
        """
        theirs = self.conversation_of_topic(topic)
        mine = self.conversation_of(contribution)
        if theirs is None:
            raise ValueError("no such topic")
        if mine != theirs and theirs not in self.linked_into(contribution):
            raise ValueError(
                "that contribution is in a different conversation from that topic")
        with self._c.atomic():
            already = self.filing(contribution, topic)
            if already is not None:
                return already
            return self._c.write(body={"reason": "about this topic"},
                                 attributed_to=attributed_to,
                                 written_by=written_by,
                                 link={"from": contribution, "to": topic,
                                       "relation": ABOUT_TOPIC})

    def filing(self, contribution, topic) -> str | None:
        """The filing IN FORCE under this Topic, or None. An un-filed one is
        history, not a filing."""
        found = self._links_now(ABOUT_TOPIC, frm=contribution, to=topic)
        return found[-1]["id"] if found else None

    def topic_contributions(self, topic) -> list[dict]:
        """Everything filed under this Topic now. A view, never a second store."""
        return self._c.read([x["link"]["from"]
                             for x in self._links_now(ABOUT_TOPIC, to=topic)])

    def topics_of(self, contribution, conversation=None) -> list[str]:
        """None, one, or several. Absence is meaningful and is not a default.

        `conversation` narrows to the Topics OF that Conversation. A linked
        contribution can be filed in two Conversations at once, and a reader
        of one of them must not be handed the other's Topics as its own.
        """
        out = [x["link"]["to"]
               for x in self._links_now(ABOUT_TOPIC, frm=contribution)]
        if conversation is None:
            return out
        return [t for t in out if self.conversation_of_topic(t) == conversation]

    # -- ending a filing or a link, append-only ------------------------------
    #
    # NOTHING HERE IS A NEW MECHANISM. A filing and a link are entries, and
    # the spine has one way for an entry to stop having current effect: a
    # later entry supersedes it. So ending one writes exactly what Delete
    # writes -- a `deletion` record carrying the reason and a `supersedes`
    # link from it to the link that is ended -- and an operational act saying
    # who did it. The ended link, who wrote it and when, stay in the record
    # byte for byte; `filings_of` reads both back as History.

    def _links_now(self, relation, *, to=None, frm=None) -> list[dict]:
        """Links of this relation that nothing has ended, oldest first."""
        return [x for x in self._c.links(relation=relation, to=to, frm=frm)
                if not self._c.stands(x["id"])["superseded_by"]]

    def _end_link(self, link_id, *, by, because, written_by=None) -> dict:
        record = self._c.write(kind=DELETION, body={"reason": because},
                               attributed_to=by, written_by=written_by)
        sup = self._c.write(body={"reason": because}, attributed_to=by,
                            written_by=written_by,
                            link={"from": record, "to": link_id,
                                  "relation": self._c.superseding_relation()})
        return {"ends": link_id, "deletion": record, "link": sup}

    def end_filing(self, contribution, topic, *, by, because=None,
                   written_by=None) -> dict | None:
        """UN-FILE: end the filing of this contribution under this Topic.

        None when it is not filed there now -- there is nothing to end, and
        nothing is written. The Turn leaves the Topic's view and count; the
        filing it had is still in the record, and so is this.
        """
        if not by:
            raise ValueError("an un-filing needs somebody who did it")
        conversation = self.conversation_of_topic(topic)
        if conversation is None:
            raise ValueError("no such topic")
        with self._c.atomic():
            fid = self.filing(contribution, topic)
            if fid is None:
                return None
            ended = self._end_link(fid, by=by, because=because or "un-filed",
                                   written_by=written_by)
            ended["act"] = self._c.record_operational(
                actor=by, act="turn-unfiled", conversation=conversation,
                turn=contribution, because=because, about=[topic, fid],
                detail={"filing": fid, **ended})
        return ended

    def move_to_topic(self, contribution, topic, *, by,
                      written_by=None) -> dict:
        """MOVE: un-file from the other Topics of that Topic's Conversation and
        file under this one -- ONE step, all or nothing.

        It writes exactly what the separate steps wrote, and nothing else:
        each un-filing its `deletion` record, `supersedes` link and
        `turn-unfiled` act (reason "moved"), then the filing's link and its
        `turn-filed` act -- so History still reads "filed X · un-filed X
        (moved) · filed Y". What it adds is that they stand or fall together:
        a move that fails part-way (a refused Topic, a lost connection, an
        error while filing) leaves the post filed where it was, with nothing
        written. Filings in OTHER Conversations it is linked into are theirs
        and are left alone.
        """
        if not by:
            raise ValueError("a move needs somebody who did it")
        conversation = self.conversation_of_topic(topic)
        if conversation is None:
            raise ValueError("no such topic")
        with self._c.atomic():
            unfiled = [self.end_filing(contribution, t, by=by, because="moved",
                                       written_by=written_by)
                       for t in self.topics_of(contribution, conversation)
                       if t != topic]
            existing = self.filing(contribution, topic)
            filing = self.assign_topic(contribution, topic, attributed_to=by,
                                       written_by=written_by)
            if existing is None:
                self.record_act(actor=by, act="turn-filed",
                                conversation=conversation, turn=contribution,
                                about=[topic, filing],
                                detail={"filing": filing})
        return {"filing": filing, "already_filed": existing is not None,
                "unfiled": [u for u in unfiled if u]}

    def link_into(self, contribution, conversation, *, by,
                  written_by=None) -> tuple[str, bool]:
        """Show this contribution in ANOTHER Conversation, as a link.

        It stays where it was written: `in-conversation` is untouched, so its
        number, thread and replies do not change and nothing is renumbered.
        Linked once at a time, as filing is. Returns (link, wrote).
        """
        if not by:
            raise ValueError("a link needs somebody who made it")
        home = self.conversation_of(contribution)
        if home is None:
            raise ValueError("that is not a Turn in any conversation")
        target = self._c.read([conversation])
        if not target or not self._is(target[0], CONVERSATION):
            raise ValueError("no such conversation")
        refusal = self.version_refusal(conversation)
        if refusal:
            raise ValueError(refusal["error"])
        if conversation == home:
            raise ValueError("that is the conversation it was written in")
        with self._c.atomic():
            now = self._links_now(LINKED_INTO, frm=contribution,
                                  to=conversation)
            if now:
                return now[-1]["id"], False
            lid = self._c.write(body={"reason": "linked here"},
                                attributed_to=by, written_by=written_by,
                                link={"from": contribution, "to": conversation,
                                      "relation": LINKED_INTO})
            self._c.record_operational(
                actor=by, act="turn-linked", conversation=conversation,
                turn=contribution, about=[conversation, lid],
                detail={"link": lid, "home": home})
        return lid, True

    def unlink(self, contribution, conversation, *, by, because=None,
               written_by=None) -> dict | None:
        """End the link that shows this contribution in that Conversation.

        ITS FILINGS THERE END WITH IT, each recorded on its own: a post that
        is no longer shown in a Conversation is not counted under its Topics.
        None when it is not linked there now.
        """
        if not by:
            raise ValueError("removing a link needs somebody who did it")
        with self._c.atomic():
            now = self._links_now(LINKED_INTO, frm=contribution,
                                  to=conversation)
            if not now:
                return None
            unfiled = [self.end_filing(contribution, t, by=by,
                                       because="its link was removed",
                                       written_by=written_by)
                       for t in self.topics_of(contribution, conversation)]
            ended = self._end_link(now[-1]["id"], by=by,
                                   because=because or "link removed",
                                   written_by=written_by)
            ended["act"] = self._c.record_operational(
                actor=by, act="turn-unlinked", conversation=conversation,
                turn=contribution, because=because,
                about=[conversation, now[-1]["id"]], detail=dict(ended))
            ended["unfiled"] = [u for u in unfiled if u]
        return ended

    # -- including posts, several at once ------------------------------------
    #
    # NOTHING HERE IS A NEW MECHANISM: each inclusion is `link_into` and each
    # ending is `unlink`, writing exactly what they write. What is added is
    # only that several are asked for in one step, and why one may not be.

    def inclusion_refusal(self, post, conversation=None) -> dict | None:
        """Why this may not be included in that Conversation (or in a new
        one, with no `conversation`), or None. Only a post -- a contribution
        written in a Conversation, as it is, not one of its later versions --
        is included anywhere; deleted material is not given new use; and a
        post is never included in the Conversation it was written in."""
        from .versions import inert_refusal
        got = self._c.read([post]) if isinstance(post, str) and post else []
        if not got:
            return {"post": post, "error": "the record holds no such entry"}
        if not self._is(got[0], CONTRIBUTION):
            return {"post": post, "error": "that is not a post; only a "
                                           "contribution is included in a "
                                           "conversation"}
        home = self.conversation_of(post)
        if home is None:
            return {"post": post, "error": "that is not a post in any "
                                           "conversation"}
        refusal = inert_refusal(self._c, post)
        if refusal:
            return {"post": post, **refusal}
        if conversation is not None and home == conversation:
            return {"post": post, "error": "that is the conversation it was "
                                           "written in", "home": home}
        return None

    def group(self, posts, *, by, name=None, about="",
              written_by=None) -> dict:
        """GROUP: open a Conversation and include these posts in it -- ONE
        step, all or nothing.

        With no name the Conversation is opened under a provisional one
        (`open_conversation(provisional=True)`). Whoever groups takes part in
        what they opened, as whoever opens one does. Each post is included by
        `link_into`, so it stays where it was written, keeps its number and
        its thread, and is shown here as a link. ANY POST THAT MAY NOT BE
        INCLUDED REFUSES THE WHOLE GROUP (`versions.Refused`, every refusal
        named in `items`), and nothing is written.
        """
        from .versions import Refused
        if not by:
            raise Refused({"error": "a group needs somebody who made it"})
        if not isinstance(posts, (list, tuple)) or not posts:
            raise Refused({"error": "a group names the posts it includes: "
                                    "\"posts\": [<id>, ...]"})
        posts = list(dict.fromkeys(posts))
        name = name.strip() if isinstance(name, str) else ""
        with self._c.atomic():
            refused = [r for r in (self.inclusion_refusal(p) for p in posts)
                       if r]
            if refused:
                raise Refused({"error": "these posts cannot be included, so "
                                        "nothing was grouped",
                               "items": refused})
            cid = self.open_conversation(name or None, about=about or "",
                                         attributed_to=by,
                                         written_by=written_by,
                                         provisional=not name)
            self.join(by, cid, attributed_to=by, written_by=written_by)
            included = []
            for p in posts:
                lid, _ = self.link_into(p, cid, by=by, written_by=written_by)
                included.append({"post": p, "link": lid,
                                 "home": self.conversation_of(p)})
        return {"conversation": cid, "name": self.conversation_name(cid),
                "provisional": not name, "included": included}

    def include(self, conversation, *, by, add=(), end=(),
                written_by=None) -> dict:
        """Include posts in this Conversation and end inclusions in it, in one
        step: each item through `link_into` or `unlink`.

        REFUSED PER ITEM: a post that may not be included here
        (`inclusion_refusal`), or an inclusion to end that is not in force,
        is named in `refused` and the rest go ahead. Only when nothing at all
        could be done is the whole of it refused (`versions.Refused`, with
        `items`), and then nothing is written. Including a post that is
        included already writes nothing and says so (`already`).
        """
        from .versions import Refused
        if not by:
            raise Refused({"error": "including a post needs somebody who did "
                                    "it"})
        add, end = list(dict.fromkeys(add or ())), list(dict.fromkeys(end or ()))
        with self._c.atomic():
            if not self.is_conversation(conversation):
                raise Refused(self.version_refusal(conversation) or {
                    "error": f"{conversation} is not a conversation in this "
                             "record", "conversation": conversation})
            added, ended, refused = [], [], []
            for p in add:
                why = self.inclusion_refusal(p, conversation)
                if why:
                    refused.append({**why, "asked": "add"})
                    continue
                lid, wrote = self.link_into(p, conversation, by=by,
                                            written_by=written_by)
                added.append({"post": p, "link": lid, "already": not wrote})
            for p in end:
                got = self.unlink(p, conversation, by=by,
                                  written_by=written_by)
                if got is None:
                    refused.append({"post": p, "asked": "end",
                                    "error": "that post is not included in "
                                             "this conversation now"})
                    continue
                ended.append({"post": p, "link": got["ends"],
                              "deletion": got["deletion"],
                              "unfiled": len(got["unfiled"])})
            if refused and not added and not ended:
                raise Refused({"error": "nothing named could be included or "
                                        "ended here; nothing was written",
                               "conversation": conversation,
                               "items": refused})
        return {"conversation": conversation, "added": added, "ended": ended,
                "refused": refused}

    def linked_into(self, contribution) -> list[str]:
        """The Conversations this contribution is linked into now."""
        return [x["link"]["to"]
                for x in self._links_now(LINKED_INTO, frm=contribution)]

    def links_here(self, conversation) -> list[dict]:
        """The links in force that show other Conversations' Turns here."""
        return self._links_now(LINKED_INTO, to=conversation)

    def filings_of(self, contribution) -> list[dict]:
        """EVERY filing and link this contribution ever had, and how each
        ended if it did: who, when, and why, read from the record. Oldest
        first, in the record's own write order -- a link and a filing made
        in one step share a timestamp. History; `topics_of` and
        `linked_into` are now."""
        out = []
        for x in self._c.links(frm=contribution):
            relation = x["link"]["relation"]
            if relation in (ABOUT_TOPIC, LINKED_INTO):
                ended = None
                for sb in self._c.stands(x["id"])["superseded_by"]:
                    rec = self._c.read([sb])
                    if rec and self._is(rec[0], DELETION):
                        ended = {"record": sb, "at": rec[0]["recorded_at"],
                                 "by": rec[0]["attributed_to"],
                                 "because": (rec[0]["body"] or {}).get("reason")}
                        break
                out.append({"link": x["id"], "relation": relation,
                            "to": x["link"]["to"],
                            "at": x["recorded_at"], "by": x["attributed_to"],
                            "ended": ended})
        return out

    # -- contributions ------------------------------------------------------

    def say(self, conversation, author, parts, *, addressed_to=(),
            replies_to=None, written_by=None) -> str:
        """Add a contribution. Never established, so it never stands as knowledge.

        `parts` is a list. Nothing here requires any of them to be text.
        """
        if isinstance(parts, str):
            raise ValueError("parts is a list of content parts, not a string")
        from .versions import Refused
        # EVERY PART NAMES ITS TYPE, checked here where every Turn is
        # written. A part without one was accepted once (Setup room, #737,
        # 2026-10-27): `orientation` lists the types of each recent Turn's
        # parts, rendering joined them, and every dispatch into that room
        # failed with a TypeError until the Turn was deleted. Refused in
        # words at the door, like an anchor the rule refuses.
        for i, part in enumerate(parts):
            if not isinstance(part, dict) or not isinstance(part.get("type"),
                                                             str) \
                    or not part.get("type"):
                raise Refused({"error": "every content part names its type "
                                        "(\"text\", \"anchor\", ...); part "
                                        f"{i} does not", "field": "parts",
                               "part": i})
        with self._c.atomic():
            # NO POST IS HOMED ON A CONVERSATION'S LATER VERSION, whichever
            # door brings it (`version_refusal`); doors that answer in words
            # ask it first, as they do the anchor rule below.
            refusal = self.version_refusal(conversation)
            if refusal:
                raise Refused(refusal)
            # AN ANCHOR PART IS CHECKED HERE, where every Turn is written, so
            # no door -- the owner's route, a worker's `respond`, a deep dive's
            # opening -- can carry one the rule refuses. Raises
            # `versions.Refused`; doors that answer in words ask it first.
            from .anchors import check_parts
            check_parts(self, conversation, parts, replies_to)
            cid = self._c.write(
                kind=CONTRIBUTION,
                body={"parts": list(parts), "addressed_to": list(addressed_to)},
                attributed_to=author, written_by=written_by)
            self._c.write(body={"reason": "said here"}, attributed_to=author,
                          written_by=written_by,
                          link={"from": cid, "to": conversation,
                                "relation": IN_CONVERSATION})
            if replies_to:
                self._c.write(body={"reason": "answers"}, attributed_to=author,
                              written_by=written_by,
                              link={"from": cid, "to": replies_to,
                                    "relation": REPLIES_TO})
        return cid

    # -- Turns ---------------------------------------------------------------
    #
    # A Turn IS a Contribution. `Turn #N` is a human-facing coordinate computed
    # from position in the Conversation, and it is stable because contributions
    # are only ever appended. The durable identity is the entry id; the number
    # is for people.

    def turns(self, conversation) -> list[dict]:
        rows = sorted(self.contributions(conversation),
                      key=lambda e: e["recorded_at"])
        return [{"number": i, "turn": e["id"], "entry": e}
                for i, e in enumerate(rows, start=1)]

    def turn_number(self, contribution) -> int | None:
        conversation = self.conversation_of(contribution)
        if conversation is None:
            return None
        # ONE NUMBERING PER CONVERSATION PER READING. Every Turn number a work
        # view shows re-sorted the whole Conversation to find one Turn in it
        # -- 250 sorts for one large Conversation's work (R3). The first row
        # for a Turn is its number, as the scan below it took.
        def numbering():
            out = {}
            for row in self.turns(conversation):
                out.setdefault(row["turn"], row["number"])
            return out
        return self._recall(("turn_numbers", conversation),
                            numbering).get(contribution)

    def turn_at(self, conversation, number: int) -> str | None:
        rows = self.turns(conversation)
        return rows[number - 1]["turn"] if 1 <= number <= len(rows) else None

    def address_turn(self, turn, participant, *, by, because=None) -> str:
        """Address an EXISTING Turn to somebody, later.

        This creates no Turn and mutates nothing. "Address Turn #322 to @Nadia"
        is something a person DID, so it is operational history that concerns
        Turn #322 -- not Turn #323, and not a rewrite of #322.
        """
        conversation = self.conversation_of(turn)
        if conversation is None:
            raise ValueError("that is not a contribution in any conversation")
        return self._c.record_operational(
            actor=by, act="turn-addressed", conversation=conversation,
            turn=turn, because=because, about=[participant])

    def addressees_of(self, turn) -> dict:
        """Who this Turn is aimed at: originally, and by later acts.

        Two different facts, kept apart. The original list is immutable body
        data; the later ones are operational acts with their own who and when.
        """
        original = self._c.read([turn])[0]["body"]["addressed_to"]
        later = [{"participant": a["about"][0] if a["about"] else None,
                  "by": a["actor"], "at": a["at"], "operational": a["id"],
                  "because": a["because"]}
                 for a in self._c.operational(turn=turn)
                 if a["act"] == "turn-addressed"]
        return {"original": original,
                "later": later,
                "all": list(dict.fromkeys(
                    list(original) + [x["participant"] for x in later
                                      if x["participant"]]))}

    # -- expectation: recorded, never inferred --------------------------------

    def expect(self, turn, *, of, kind, by, because=None, caused_by=None,
               requires=(), material=(), detail=None,
               conversation=None) -> str:
        """Record that this Turn expects something back from somebody.

        `a6cca1f` found that Mentis could not tell "@Ada, what do you think?"
        from "@Ada, investigate X and report back". This is that fact, and it
        is RECORDED BY AN ACTOR, never inferred from prose -- which is why it
        lives in operational history rather than in the Contribution.

        `kind` is vocabulary (result, clarification, decision, input, ...).
        Two kinds are read: "decision" and "input" are asked of somebody
        under a piece of work (`ASKED_UNDER_WORK`), and an input is answered
        by its set being marked ready rather than by a reply (`INPUT`).
        Every other kind is only recorded.

        `of=None` IS A REAL ANSWER AND NOT A MISSING ARGUMENT. Something can be
        owed before anybody is assigned to it, and that is the honest state of a
        request nobody has been chosen for: `about` stays EMPTY rather than
        carrying a null, because `about=[None]` would be a reference to nothing
        and every reader of `about[0]` would have to know that. Who is assigned
        is answered by `assigned_carrier`, from the assignment acts.

        `requires` is what the work actually needs, as declared capability
        names. It is on the expectation because it is a fact about the request,
        and selection must be able to read it without re-reading prose.

        `material` NAMES WHAT IS BEING ASKED ABOUT, where the request is about
        a durable item. It is on the expectation for the same reason `requires`
        is -- it is a fact about the request -- and it is what lets an act on
        that item know it answered this ask instead of leaving the person to
        answer twice. Absent it stays absent: an ask that names no material is
        an ask about nothing in particular, which is an ordinary thing to be.

        IT IS NOT AN OBLIGATION ON THE MATERIAL and it confers nothing. Naming
        an item here does not establish it, dispute it, place it, or make it
        stand; the only thing it changes is that answering can be noticed.

        `turn=None` with a `conversation` is a question of a decision form
        that is on no post yet (`DECISION_FORM`); nothing else asks for it.
        """
        conversation = (self.conversation_of(turn) if turn is not None
                        else conversation)
        body = dict(detail or {})
        body["expects"] = kind
        if requires:
            body["requires"] = list(requires)
        if material:
            body["material"] = list(material)
        return self._c.record_operational(
            actor=by, act="expectation-recorded", conversation=conversation,
            turn=turn, because=because, caused_by=caused_by,
            about=[of] if of else [], detail=body)

    def assign(self, expectation, carrier, *, by, because=None,
               detail=None) -> str:
        """Append who is to carry an expectation. The expectation is untouched.

        APPEND-ONLY, BECAUSE AN ASSIGNMENT IS SOMETHING SOMEBODY DID. Editing
        the expectation's own `about` would erase that it was once unassigned
        and lose who chose the carrier and why. Current assignment is therefore
        COMPUTED from these acts -- see `assigned_carrier` -- and reassignment
        is another act rather than a rewrite.
        """
        exp = self._act(expectation)
        if exp is None or exp["act"] != "expectation-recorded":
            raise ValueError("no such expectation")
        return self._c.record_operational(
            actor=by, act="expectation-assigned",
            conversation=exp["conversation"], turn=exp["turn"],
            because=because, caused_by=expectation, about=[carrier],
            detail=dict(detail or {}))

    def _act(self, oid) -> dict | None:
        # By its id, which the store indexes. This used to read and decode
        # every act in the record to find one, and every expectation read calls
        # it several times -- measured at 5s for one owner's obligations on a
        # 935-act Brain, all of it here.
        if not oid:
            return None
        if not isinstance(oid, str):
            rows = self._c.operational(id=oid)
            return rows[0] if rows else None
        return self._recall(("act", oid), lambda: next(
            iter(self._c.operational(id=oid)), None))

    # -- the reads every expectation answer is built from ----------------------
    #
    # ONE QUESTION EACH, ASKED THE SAME WAY EVERYWHERE, AND ANSWERED ONCE PER
    # READING. An expectation's state is assembled from four reads -- the act by
    # its id, the acts it caused, the replies to its Turn, and the write order
    # of its runs -- and the work and owed views ask them again for every node
    # of every causal tree they walk: ~20,000 statements for `/api/owed` and for
    # one large Conversation's work on the live Brain, most of them the same
    # few questions asked over and over (R3). Each is answered here through
    # `_recall`, so inside a `reading()` scope it is asked once and outside one
    # it is exactly the read it always was. Nothing is kept past the scope and
    # nothing survives a write: `_recall`'s rules, not new ones.
    #
    # THE LISTS ARE HANDED OUT AS COPIES, the acts in them are not: a caller
    # that sorts or extends what it was given must not reorder the next
    # caller's answer, and no reader of an act writes into it.

    def _children(self, parent) -> list[dict]:
        """`operational(caused_by=parent)`, in write order: the acts this one
        caused, directly. The one place every causal walk reads a level."""
        if not isinstance(parent, str):
            return self._c.operational(caused_by=parent)
        return list(self._recall(("caused_by", parent), lambda:
                                 self._c.operational(caused_by=parent)))

    def _replies_to(self, turn) -> list[dict]:
        """The reply links to this Turn, in append order. `turn=None` asks for
        every reply link in the record, exactly as the link read does -- that
        is what an expectation with no Turn has always been compared with."""
        if turn is not None and not isinstance(turn, str):
            return self._c.links(relation=REPLIES_TO, to=turn)
        return list(self._recall(("replies_to", turn), lambda:
                                 self._c.links(relation=REPLIES_TO, to=turn)))

    def _entry(self, eid) -> list[dict]:
        """`read([eid])`: the entry, or nothing. Once per reading."""
        if not isinstance(eid, str):
            return self._c.read([eid])
        return list(self._recall(("entry", eid), lambda: self._c.read([eid])))

    def _prefetch_lineage(self, roots, *, through_expectations=True, acts=()):
        """Read these causal forests a LEVEL at a time and settle, for this
        reading, every per-node answer the walk above them would ask for.

        WHAT IT SETTLES, and nothing it was not asked: for every node whose
        children it read, `_children(node)` -- including the leaves, whose
        answer is "none", which is most of them and is the read that cost
        most; for every act it read, `_act(id)` and its write order; and for
        every expectation it met, `_replies_to(its Turn)`. Each is the answer
        the one-node read would give: `operational_under` keeps each parent's
        acts in write order, and the reply links are grouped from one read in
        append order. `acts` are rows the caller already holds, settled as
        `_act` answers alongside.

        `through_expectations=False` stops below each expectation met under a
        root, as `_own_acts` does; that expectation's own children are then
        not read, and so not settled -- it is left to be asked.

        ONLY INSIDE A `reading()` SCOPE, and through `_recall`, so under its
        rule: every level is read inside one computation, and the answers are
        kept only if no commit finished or was under way across all of it.
        Otherwise they are dropped and every node is asked one at a time, as
        it always was. Outside a scope this does nothing at all."""
        if getattr(self._scope, "frame", None) is None:
            return
        roots = list(dict.fromkeys(r for r in roots if isinstance(r, str)))
        if not roots:
            return

        def compute():
            settled, seen = {}, set(roots)
            expectations = [a for a in acts
                            if a["act"] == "expectation-recorded"]
            for a in acts:
                settled[("act", a["id"])] = a
            frontier = roots
            while frontier:
                kids = {p: [] for p in frontier}
                nxt = []
                for seq, a in self._c.operational_under(frontier):
                    kids[a["caused_by"]].append(a)
                    settled[("act", a["id"])] = a
                    settled[("seq", a["id"])] = seq
                    if a["act"] == "expectation-recorded":
                        expectations.append(a)
                    if a["id"] in seen:
                        continue
                    seen.add(a["id"])
                    if (through_expectations
                            or a["act"] != "expectation-recorded"):
                        nxt.append(a["id"])
                for p, got in kids.items():
                    settled[("caused_by", p)] = got
                frontier = nxt
            turns = list(dict.fromkeys(a["turn"] for a in expectations
                                       if a.get("turn")))
            replies = {t: [] for t in turns}
            for e in self._c.links(relation=REPLIES_TO, to_any=turns):
                replies[e["link"]["to"]].append(e)
            for t, got in replies.items():
                settled[("replies_to", t)] = got
            # ...and which Conversation each of those Turns is in, which is
            # what numbering it asks first (`turn_number`): the first
            # placement link in append order, as `conversation_of` takes it.
            placed = {}
            for e in self._c.links(relation=IN_CONVERSATION, frm_any=turns):
                placed.setdefault(e["link"]["from"], e["link"]["to"])
            for t in turns:
                settled[("conversation_of", t)] = placed.get(t)
            # the write order of the rows the caller handed in, which were
            # read without it
            if acts:
                for i, seq in self._c.operational_order(
                        [a["id"] for a in acts]).items():
                    settled[("seq", i)] = seq
            return settled

        self._recall(("lineage", tuple(roots), bool(through_expectations)),
                     compute, also=lambda settled: settled)

    def assigned_carrier(self, expectation) -> dict:
        """Who carries this now, and how that came to be.

        The latest assignment act wins, and every one of them stays readable.
        An expectation recorded OF somebody was assigned at birth, which is the
        ordinary Ask @Participant case and needs no separate act.
        """
        exp = self._act(expectation)
        if exp is None:
            raise ValueError("no such expectation")
        acts = [a for a in self._children(expectation)
                if a["act"] == "expectation-assigned" and a["about"]]
        acts.sort(key=lambda a: a["at"])
        if acts:
            return {"carrier": acts[-1]["about"][0], "by": acts[-1]["actor"],
                    "at": acts[-1]["at"], "assignment": acts[-1]["id"],
                    "history": [a["id"] for a in acts]}
        if exp["about"]:
            return {"carrier": exp["about"][0], "by": exp["actor"],
                    "at": exp["at"], "assignment": None, "history": []}
        return {"carrier": None, "by": None, "at": None,
                "assignment": None, "history": []}

    def expectation_state(self, expectation) -> dict:
        """The mechanical facts about one expectation. It reaches no verdict.

        Mentis says whether a response exists, whether an execution is live and
        what was last recorded. Whether that means waiting, stalled, blocked,
        retry or escalate is the reading of whoever asked -- deliberately not a
        status machine.
        """
        exp = self._act(expectation)
        if exp is None or exp["act"] != "expectation-recorded":
            raise ValueError("no such expectation")
        assigned = self.assigned_carrier(expectation)
        responder = assigned["carrier"]

        # EVERYTHING BELOW IS ABOUT THIS EXPECTATION, NOT ABOUT ITS CARRIER.
        # It used to ask what that Participant was doing anywhere -- the newest
        # act by them, and any live execution of theirs -- so one agent working
        # in another Conversation made every expectation of them look live, and
        # an unassigned expectation (no carrier at all) looked like activity by
        # whoever `about[0]` happened to be. The causal chain already says which
        # acts belong to this request; these read it instead of guessing.
        mine = self._own_acts(expectation)
        satisfied_by = [a["id"] for a in mine if a["act"] == "expectation-met"]
        # A QUESTION OF A DECISION FORM IS ANSWERED BY THE REPLY THAT NAMES
        # IT (`DECISION_ANSWERED`), never by any reply to the post: several
        # questions share that post. Every other expectation: as it was.
        form = (exp["detail"] or {}).get("form")
        if form:
            answers = [a for a in mine if a["act"] == DECISION_ANSWERED
                       and responder and a["actor"] == responder]
            replies = [(a["detail"] or {}).get("reply") for a in answers]
        else:
            replies = [e["link"]["from"]
                       for e in self._replies_to(exp["turn"])
                       if responder
                       and e.get("attributed_to") == responder]
        # WHAT IS RUNNING FOR **THIS** REQUEST. Three sources, narrowest first,
        # and none of them is "any execution belonging to this carrier" -- which
        # is what this used to be, and why one agent busy in another
        # Conversation made every expectation of them look live.
        #
        #   1. a live handle that NAMES this expectation. Exact, and the only
        #      one that stays exact when a carrier holds several at once.
        #   2. executions the lineage's own start acts named and no result or
        #      failure has closed. Durable, so it survives a restart.
        #   3. a live handle of this carrier IN THIS CONVERSATION that names no
        #      expectation at all. The pre-existing meaning, kept because a
        #      caller who did not say which request is not thereby saying
        #      "none" -- but now bounded by the Conversation, so unrelated
        #      concurrent work in another one can no longer be read as this.
        runs = [a for a in mine
                if a["act"] in ("execution-started", *RUN_ENDS)]
        order = self._write_order(a["id"] for a in runs)
        done = closed_starts(runs, lambda a: order.get(a["id"], -1))
        live = {a["execution"] for a in runs
                if a["act"] == "execution-started" and a["execution"]
                and a["id"] not in done}
        for e in self.active_executions():
            if e.for_expectation == expectation:
                live.add(e.reference)
            elif (e.for_expectation is None and responder
                    and e.participant == responder
                    and e.conversation == exp["conversation"]):
                live.add(e.reference)
        live = sorted(live)
        failures = [{"act": a["id"], "because": a["because"], "at": a["at"]}
                    for a in mine if a["act"] == "delivery-failed"]
        delegations = [{"act": a["id"], "expectation": a["about"][0]
                        if a["about"] else None,
                        "by": a["actor"], "at": a["at"]}
                       for a in mine if a["act"] == "work-delegated"]
        latest = max(mine, key=lambda a: a["at"]) if mine else None
        # A DECISION ABOUT FINDINGS IS ANSWERED BY THE CHOICE, NOT BY WORDS.
        # Its answer is the owner's recorded selections; a reply to it -- a
        # question, or prose that selects nothing -- is kept as their words
        # and leaves it owed, shown and waited on until they choose.
        #
        # A DECISION THE OWNER WITHDREW IS CLOSED BY THAT ACT, and says so.
        # The withdrawal is the decision's own `expectation-met`, by the
        # person it was asked of, marked `withdrawn` and carrying their reason
        # -- written beside their reply, never inferred from its words. It
        # selects nothing, so a reconsideration it closes leaves every finding
        # as it was.
        withdrawal = next((a for a in mine
                           if a["act"] == "expectation-met"
                           and responder and a["actor"] == responder
                           and (a["detail"] or {}).get("withdrawn")), None)
        withdrawn = ({"act": withdrawal["id"], "by": withdrawal["actor"],
                      "at": withdrawal["at"],
                      "because": withdrawal.get("because"),
                      "reply": (withdrawal["detail"] or {}).get("reply")}
                     if withdrawal else None)
        present = bool(satisfied_by or replies)
        if (exp["detail"] or {}).get("reconsideration"):
            present = withdrawn is not None or any(
                a["act"] == "expectation-met"
                and a["actor"] == responder
                and "selections" in (a["detail"] or {})
                for a in mine)
        # AN INPUT IS ANSWERED BY ITS SET BEING MARKED READY, NOT BY WORDS.
        # Only a marked-ready written after the wait was declared, by the
        # person it was asked of, answers it -- or their withdrawing it. A
        # reply to the post is kept as what it is and answers nothing.
        given = None
        if (exp["detail"] or {}).get("expects") == INPUT:
            given = self._input_given(exp, responder)
            present = withdrawn is not None or bool(given["ready"])

        return {
            "expectation": expectation,
            # WHERE IT WAS ASKED: for a question of a decision form, the
            # form's post (None while it is on none yet).
            "turn": self.asked_on(exp) if form else exp["turn"],
            "conversation": exp["conversation"],
            "expects": exp["detail"].get("expects"),
            "requires": list(exp["detail"].get("requires") or ()),
            # THE ALTERNATIVES THE ASKER STATED, as recorded. None when it
            # stated none -- which is not an empty list of alternatives.
            "options": exp["detail"].get("options"),
            # WHAT THIS ASK IS ABOUT, where it names durable material. Empty
            # when it named none, which is not a claim that it concerns
            # nothing -- only that nobody wrote down what.
            "material": list(exp["detail"].get("material") or ()),
            # Durable since `expect()` was written, and never surfaced. It is
            # the requester's own reason for needing this, which is the most
            # the record currently says about WHY somebody is being asked.
            "because": exp.get("because"),
            "recorded_by": exp["actor"],
            "requested_by": exp["actor"],
            "expected_of": responder,
            "assigned": assigned,
            "unassigned": responder is None,
            "response_present": present,
            "satisfied_by": satisfied_by,
            # None, or who withdrew it, when, why and with which reply. A
            # withdrawn decision is closed and was NOT answered.
            "withdrawn": withdrawn,
            "replies_from_expected": replies,
            "live_execution": live,
            "failures": failures,
            "delegations": delegations,
            "latest_activity": latest,
            # ONLY FOR AN INPUT: its set, and each marked-ready that answers
            # it with the exact answers it covered.
            **({"input": given} if given is not None else {}),
            # ONLY FOR A QUESTION OF A DECISION FORM: the form, its place in
            # it, its own words, and the reply that answered it as the owner
            # set it (option, label, or their own words).
            **({"form": form,
                "index": exp["detail"].get("index"),
                "question": exp["detail"].get("question"),
                "answer": ({"reply": (answers[0]["detail"] or {}).get("reply"),
                            "act": answers[0]["id"], "at": answers[0]["at"],
                            **{k: (answers[0]["detail"] or {})[k]
                               for k in ("option", "label", "words")
                               if k in (answers[0]["detail"] or {})}}
                           if answers else None)}
               if form else {}),
        }

    # -- decision forms (P7) ---------------------------------------------------

    def asked_on(self, exp) -> str | None:
        """The post a decision was asked on: its own Turn, or for a question
        of a decision form the form's post -- the Turn `on` named, else the
        answer post it was attached to, else None while it is on none yet.
        `exp` is the expectation act or its id."""
        if isinstance(exp, str):
            exp = self._act(exp)
        if not exp:
            return None
        form = (exp.get("detail") or {}).get("form")
        if not form:
            return exp.get("turn")
        return self._form_post(form)

    def _form_post(self, form) -> str | None:
        act = self._act(form)
        if act is None:
            return None
        if act.get("turn"):
            return act["turn"]
        attached = [a for a in self._children(form)
                    if a["act"] == DECISION_FORM_ATTACHED and a.get("turn")]
        return attached[0]["turn"] if attached else None

    def decision_form(self, form) -> dict | None:
        """One decision form as the record holds it: where it is, who asked,
        and each question with its options and what became of it. What a
        view needs to draw it (P9); nothing here is stored as a status --
        `open` and `closed` are read from each question's own state."""
        act = self._act(form)
        if act is None or act["act"] != DECISION_FORM:
            return None
        exps = sorted((a for a in self._children(act.get("caused_by"))
                       if a["act"] == "expectation-recorded"
                       and (a.get("detail") or {}).get("form") == form),
                      key=lambda a: a["detail"].get("index", 0))
        questions = []
        for a in exps:
            s = self.expectation_state(a["id"])
            w = s["withdrawn"]
            questions.append({
                "expectation": a["id"], "index": s["index"],
                "question": s["question"], "options": s["options"],
                "because": s["because"], "of": s["expected_of"],
                "answered": s["answer"] is not None,
                "answer": s["answer"], "withdrawn": w,
                "open": not s["response_present"],
                "closed_at": (s["answer"]["at"] if s["answer"]
                              else w["at"] if w else None)})
        post = self._form_post(form)
        closed = bool(questions) and not any(q["open"] for q in questions)
        return {"form": form, "post": post, "pending": post is None,
                "on": act.get("turn"),
                "conversation": act["conversation"],
                "asked_by": act["actor"], "execution": act.get("execution"),
                "request": act.get("caused_by"), "at": act["at"],
                "because": act.get("because"),
                "questions": questions,
                "open": sum(1 for q in questions if q["open"]),
                "closed": closed,
                "closed_at": (max(q["closed_at"] for q in questions)
                              if closed else None)}

    def decision_forms_on(self, turn) -> list[str]:
        """The decision forms on this post, oldest first: asked `on` it, or
        attached to it as a run's answer post."""
        out = []
        for a in self._c.operational(turn=turn):
            if a["act"] == DECISION_FORM:
                out.append(a["id"])
            elif a["act"] == DECISION_FORM_ATTACHED and a.get("caused_by"):
                out.append(a["caused_by"])
        return list(dict.fromkeys(out))

    def attach_pending_forms(self, execution, turn, *, by) -> list[str]:
        """Put every decision form this execution asked with no `on`, and
        that is on no post yet, on `turn` -- the run's answer post. Once:
        a form already on a post is never moved. Returns the forms put."""
        if not execution or not turn:
            return []
        made = []
        with self._c.atomic():
            for a in self._c.operational(execution=execution):
                if (a["act"] != DECISION_FORM or a.get("turn")
                        or self._form_post(a["id"])):
                    continue
                self._c.record_operational(
                    actor=by, act=DECISION_FORM_ATTACHED,
                    conversation=self.conversation_of(turn), turn=turn,
                    caused_by=a["id"], execution=execution,
                    because="the run that asked it wrote its answer post",
                    detail={"form": a["id"], "post": turn})
                made.append(a["id"])
        return made

    def _permission_form(self, form) -> bool:
        """Whether a decision form is a run's permission question."""
        if not form:
            return False
        act = self._act(form)
        return bool(act and act["act"] == DECISION_FORM
                    and (act.get("detail") or {}).get("permission"))

    def _forms_waited(self, parent) -> list[dict]:
        """The decision forms this work asked, each as `decision_form`."""
        return [f for f in (self.decision_form(a["id"])
                            for a in self._children(parent)
                            if a["act"] == DECISION_FORM) if f]

    def _input_given(self, exp, responder) -> dict:
        """What has answered this 'input' expectation: its response set and
        each marked-ready since the wait was declared, by the person it was
        asked of, oldest first, with the answers each covered."""
        from . import responses
        d = exp["detail"] or {}
        sid = d.get("response_set")
        before = set(d.get("ready_before") or ())
        rows = []
        if sid and responder:
            # P2a's own reader of a set's members, as `responses.state` reads
            # its marked-ready entries.
            rows = [m for m in responses._members(self._c, sid,
                                                  responses.MARKED_READY)
                    if m["id"] not in before
                    and m.get("attributed_to") == responder]
        return {"set": sid,
                "ready": [{"marked_ready": m["id"],
                           "answers": list(m["body"].get("answers") or ()),
                           "at": m["recorded_at"]} for m in rows]}

    def _input_handover(self, sid) -> dict:
        """The own words and interpretations of an input's set, as a
        `work-resumed` act keeps them (`responses.handed`)."""
        from . import responses
        if not sid:
            return {"words": [], "proposals": []}
        try:
            return responses.handed(responses.handover(self, sid))
        except Exception as exc:                          # noqa: BLE001
            # Resuming is not held up by a set that cannot be read; the act
            # says what was not handed, and why.
            return {"words": [], "proposals": [],
                    "handover_not_read": f"{type(exc).__name__}: {exc}"}

    def _descendants(self, root, *, through_expectations=True) -> list[dict]:
        """Every act caused by this one, transitively, plus nothing else.

        This is the lineage delegation depends on: a specialist's start, result
        and failure hang off the child expectation, which hangs off the
        delegation, which hangs off the parent. Crossing into another Topic or
        Conversation changes nothing here, because causality is not scoped by
        where it happened.

        With `through_expectations=False` the walk STOPS at each child
        expectation -- see `_own_acts`, which is the caller that needs that and
        the reason this parameter exists.
        """
        out, seen, frontier = [], {root}, [root]
        while frontier:
            nxt = []
            for parent in frontier:
                for a in self._children(parent):
                    if a["id"] in seen:
                        continue
                    seen.add(a["id"])
                    out.append(a)
                    if through_expectations or a["act"] != "expectation-recorded":
                        nxt.append(a["id"])
            frontier = nxt
        return sorted(out, key=lambda a: a["at"])

    def _own_acts(self, expectation) -> list[dict]:
        """This expectation's OWN acts: its runs, its failures, its fulfilment.

        WHY THIS IS NOT SIMPLY THE DESCENDANTS, found by a test rather than by
        reading. A dispatch's result and failure hang off its START act, not off
        the expectation, so they are two levels down and a direct-children rule
        would miss them entirely. But the full transitive walk reaches THROUGH a
        delegated child expectation -- and a specialist recording
        `expectation-met` on ITS OWN work then made the PARENT read as
        fulfilled. A request was satisfied by having handed half of itself to
        somebody, which is the worst possible thing this could get wrong.

        So the walk includes everything under this expectation and descends no
        further once it reaches another expectation: that subtree belongs to that
        expectation and is reported as a delegation, not as this one's answer. A
        child is reached by asking about the child.
        """
        return self._descendants(expectation, through_expectations=False)

    def expectations(self, *, conversation=None, of=None,
                     unassigned=None, open_only=False) -> list[dict]:
        """What is owed here. `of` is the CURRENT carrier, not `about[0]`.

        Filtering on the expectation's own `about` would have missed everything
        assigned by a later act and everything reassigned, which is most of what
        Ask Mentis produces. `unassigned=True` asks the opposite question --
        what is owed and nobody is carrying -- which no filter could express
        while an unassigned expectation was written as `about=[None]`.

        `open_only` skips evaluating expectation_state on expectations where
        the assigned carrier has already replied to the turn, returning only
        expectations where response_present is False.

        ONLY THE ONES WHOSE CARRIER IS ASKED ABOUT ARE READ IN FULL. `of` and
        `unassigned` filter on the current carrier, which is one rule over the
        assignment acts (`assigned_carrier`); it used to be applied AFTER the
        whole state of every expectation in the Brain had been read -- ~1,700
        of them, ~11 statements each, to answer one Participant's `/api/owed`
        (R3). The carriers are now read first, all at once and by the
        identical rule (`_carriers`), and only the expectations that pass are
        evaluated. The answer, and its order, are what filtering afterwards
        gave: the same filter is still applied to what comes back.

        AS ONE MOMENT OF THE RECORD. Reading every carrier before any state
        puts some reads earlier than the old order did, so an assignment
        written in between could be missed. The scoped reading is therefore
        taken only if nothing was written while it ran (`Corpus.settled`);
        otherwise the unscoped one answers, as it always did.
        """
        if of is None and unassigned is None:
            return self._expectation_states(
                self._expectation_acts(conversation), open_only)

        def scoped():
            rows = self._expectation_acts(conversation)
            carriers = self._carriers(rows)
            return self._expectation_states(
                [a for a in rows
                 if (of is None or carriers[a["id"]] == of)
                 and (unassigned is None
                      or (carriers[a["id"]] is None) is bool(unassigned))],
                open_only)

        out = self._c.settled(scoped, lambda: self._expectation_states(
            self._expectation_acts(conversation), open_only))
        if of is not None:
            out = [r for r in out if r["expected_of"] == of]
        if unassigned is not None:
            out = [r for r in out if r["unassigned"] is bool(unassigned)]
        return out

    def _expectation_acts(self, conversation=None) -> list[dict]:
        """Every `expectation-recorded` act, in write order -- in one
        Conversation, or anywhere. Selected by SQLite rather than by reading
        and decoding every act in the record to keep these."""
        return self._c.operational(conversation=conversation,
                                   act="expectation-recorded")

    def _carriers(self, rows) -> dict:
        """expectation id -> its CURRENT carrier, or None, for these
        `expectation-recorded` acts -- `assigned_carrier(id)["carrier"]` for
        each, read in one statement instead of one per expectation.

        THE SAME RULE, NOT A SIMILAR ONE: of the `expectation-assigned` acts
        it caused that name somebody, in write order, the latest by `at` under
        a stable sort -- so equal timestamps resolve exactly as there -- else
        the expectation's own `about[0]`, else nobody."""
        assigned = {}
        for _seq, a in self._c.operational_under(
                [a["id"] for a in rows], act="expectation-assigned"):
            if a["about"]:
                assigned.setdefault(a["caused_by"], []).append(a)
        out = {}
        for a in rows:
            acts = sorted(assigned.get(a["id"], ()), key=lambda x: x["at"])
            out[a["id"]] = (acts[-1]["about"][0] if acts
                            else a["about"][0] if a["about"] else None)
        return out

    def _expectation_states(self, rows, open_only) -> list[dict]:
        """`expectation_state` of each of these acts, in their order; with
        `open_only`, of those nobody has answered. Inside a `reading()` scope
        their causal trees and reply links are read a level at a time first
        (`_prefetch_lineage`), so each state is assembled from answers this
        reading already holds."""
        self._prefetch_lineage([a["id"] for a in rows],
                               through_expectations=False, acts=rows)
        if not open_only:
            out = [self.expectation_state(a["id"]) for a in rows]
        else:
            out = []
            # Who replied to the Turns THESE expectations hang on -- the only
            # keys looked up below -- rather than to every Turn in the corpus.
            replies_map = {}
            for e in self._c.links(relation=REPLIES_TO, to_any=[
                    a["turn"] for a in rows if a.get("turn")]):
                replies_map.setdefault(e["link"]["to"], set()).add(
                    e.get("attributed_to"))

            for a in rows:
                exp_id = a["id"]
                # Neither a reconsideration nor an input is answered by a
                # reply, so a reply cannot be taken as a shortcut for them;
                # nor is a question of a decision form, which only the reply
                # naming it answers (P7).
                is_reconsideration = bool(
                    (a.get("detail") or {}).get("reconsideration")
                    or (a.get("detail") or {}).get("expects") == INPUT
                    or (a.get("detail") or {}).get("form"))
                assigned = self.assigned_carrier(exp_id)
                responder = assigned["carrier"]
                if not is_reconsideration and responder and a.get("turn"):
                    if responder in replies_map.get(a["turn"], ()):
                        continue
                st = self.expectation_state(exp_id)
                if not st["response_present"]:
                    out.append(st)
        return out

    def asks_about(self, entry, *, open_only=True) -> list[dict]:
        """Which recorded requests name this durable item.

        THE SAME EXPECTATION MACHINERY, ASKED A DIFFERENT WAY. There is no
        second register of "things asked about material": an ask is an
        expectation, and one that names material says so in its own detail.
        This finds them, so that an act on the item can know whether it
        answered anything.

        `open_only` leaves out the ones a response already exists for, because
        an ask that is already answered is not answered again by a later act.
        """
        out = []
        for a in self._c.operational():
            if a["act"] != "expectation-recorded":
                continue
            if entry not in (a["detail"] or {}).get("material", ()):
                continue
            state = self.expectation_state(a["id"])
            if open_only and state["response_present"]:
                continue
            out.append(state)
        return out

    # -- what a piece of work may organise ------------------------------------
    #
    # AUTHORITY BELONGS TO THE WORK. It is an operational act caused by one
    # expectation, written by whoever made that request, and it names the
    # organising operations that request may use. It is not a property of the
    # Participant carrying it, of any Persona, runtime, model or session, so none
    # of those changing can change it -- and superseding the designation or
    # Persona that first carried the work does not reach back into it either.
    # Narrowing or revoking is another explicit act, not a side effect.
    #
    # The operation NAMES are data here. Which names exist is the worker
    # surface's business; this layer only records what somebody granted --
    # with ONE exception, LEGACY_AUTHORITY below, which is about how an old
    # record reads and not about what any name means now.
    #
    # THE ONE COMPATIBILITY READ (owner ruling ent-94edb8bc6342). Authority to
    # coordinate a piece of work is recorded as `coordinate`. Before that name
    # existed it was recorded as `delegate` -- the same word as the capability
    # every run holds to hand work on, which is why it was replaced. A grant
    # that lists `delegate` was written then and meant coordination, so
    # `authority_of` reads it as `coordinate`; the record itself is never
    # rewritten, and `grant_authority` refuses to write `delegate` again.
    # Nothing else anywhere maps `delegate` to anything: every reader of
    # recorded authority -- dispatch, continuation, resumption -- comes
    # through `authority_of`.
    LEGACY_AUTHORITY = {"delegate": "coordinate"}

    def grant_authority(self, expectation, operations, *, by, source,
                        because, origin=None) -> str:
        """Record what this request may organise. Only its requester may.

        `source` says how it came to be -- carried an unaddressed request,
        continued authorised work, or granted explicitly -- and `origin` is what
        it came from: a designation, or the expectation it continues.
        """
        exp = self._act(expectation)
        if exp is None or exp["act"] != "expectation-recorded":
            raise ValueError("no such expectation")
        if by != exp["actor"]:
            raise ValueError(
                "only the Participant who made a request can say what it may "
                "organise")
        legacy = sorted(set(operations) & set(self.LEGACY_AUTHORITY))
        if legacy:
            raise ValueError(
                f"{legacy} is not authority any more; it is read that way only "
                f"in grants recorded before "
                f"{sorted(self.LEGACY_AUTHORITY.values())} existed. Record "
                f"{[self.LEGACY_AUTHORITY[o] for o in legacy]} instead")
        return self._c.record_operational(
            actor=by, act="authority-granted",
            conversation=exp["conversation"], turn=exp["turn"],
            because=because, caused_by=expectation,
            about=[origin] if origin else [],
            detail={"operations": sorted(set(operations)), "source": source,
                    "origin": origin})

    def authority_of(self, expectation) -> dict:
        """What this request may organise, and where that came from.

        THREE ANSWERS. None recorded is ordinary work, and says so. Exactly one,
        by the requester, is the answer. More than one is UNRESOLVED -- not a
        recency contest -- and organises nothing until a person says which.
        """
        exp = self._act(expectation) if expectation else None
        if exp is None:
            return {"operations": [], "source": None, "origin": None,
                    "act": None, "because": "this run carries no request"}
        acts = [a for a in self._c.operational(caused_by=expectation)
                if a["act"] == "authority-granted" and a["actor"] == exp["actor"]]
        if not acts:
            return {"operations": [], "source": None, "origin": None,
                    "act": None,
                    "because": "no organising authority was recorded for this "
                               "request, so it is ordinary work"}
        if len(acts) > 1:
            return {"operations": [], "source": None, "origin": None,
                    "act": None, "unresolved": [a["id"] for a in acts],
                    "because": "several authority records for one request; "
                               "which applies is a person's decision"}
        a = acts[0]
        recorded = list(a["detail"].get("operations") or ())
        legacy = sorted(set(recorded) & set(self.LEGACY_AUTHORITY))
        return {"operations": sorted({self.LEGACY_AUTHORITY.get(o, o)
                                      for o in recorded}),
                "source": a["detail"].get("source"),
                "origin": a["detail"].get("origin"),
                "act": a["id"], "because": a["because"],
                # said, when the record was read through LEGACY_AUTHORITY,
                # so what was recorded is never mistaken for what is answered
                **({"read_as": {o: self.LEGACY_AUTHORITY[o] for o in legacy}}
                   if legacy else {})}

    def continuation_candidates(self, replying_to, *, requester,
                                carrier) -> list[dict]:
        """The authorised work a reply to this Turn would be continuing.

        READ FROM LINEAGE, NEVER FROM PROSE. The Turn replied to, and the one
        IT answers -- so replying to a carrier's result reaches the request that
        result answered. Only requests that are still open, that this requester
        made, that this carrier carries now, and that carry recorded organising
        authority. The same Participant, the same Conversation, a mention, a
        content reference and a shared session are none of them lineage.

        AND ONE STEP UP `caused_by`. An expectation on those Turns that was
        raised UNDER some work -- a decision that work asked the owner, a child
        it delegated -- leads to that work. So answering the decision, or
        replying to the child's result, resumes the parent. Every guard above
        still applies to the parent, which is why this can only ever reach work
        the replier made and the dispatched Participant carries: the decision
        asker's, the child's and discovered work's own expectations are never
        candidates by being on the Turn.

        THE PARENT NEEDS NO ORGANISING AUTHORITY. Raising a decision or a
        child under it is the lineage, and every run can do that (`delegate`
        is a capability, owner ruling ent-94edb8bc6342). Requiring authority
        here made the owner's answer to ordinary work's decision start an
        unrelated request, and the work it answered sat waiting for a resume
        that nothing would ever ask for (#797, opr-bc5125a362ed). It is
        continued with what it may organise, which may be nothing.

        ONLY FROM A DECISION, AN INPUT OR A DELEGATED CHILD, AND NEVER
        THROUGH WORK CLAIMED MET. Those are the only expectations raised
        under work as part of it. Discovered work's `caused_by` is where it was found; a
        continuation's is the work it continued, which is already this line
        of work and is a candidate itself while open. And a child claimed
        met is finished: a reply to it is new work, not a way back into work
        that already went on past it -- which, counted as that work running,
        would also have kept it from resuming.
        """
        turns = [replying_to] + self._linked(REPLIES_TO, frm=replying_to)
        seen, out = set(), []

        def consider(expectation, turn, via=None):
            if expectation in seen:
                return
            seen.add(expectation)
            a = self._act(expectation)
            if (a is None or a["act"] != "expectation-recorded"
                    or a["actor"] != requester):
                return
            state = self.expectation_state(expectation)
            if state["satisfied_by"] or state["expected_of"] != carrier:
                return
            authority = self.authority_of(expectation)
            if not authority["operations"] and via is None:
                return
            out.append({"expectation": expectation, "turn": a["turn"],
                        "number": self.turn_number(a["turn"]),
                        "operations": authority["operations"],
                        **({"via": via} if via else {})})

        def steps_up(a) -> bool:
            detail = a["detail"] or {}
            # an input it waits for, as a decision it asked: replying on
            # that post (Send back) continues the work that asked
            if detail.get("expects") in ASKED_UNDER_WORK:
                return True
            return bool(detail.get("returns_to")
                        and not self.is_finding(a["id"])
                        and not self.expectation_state(a["id"])["satisfied_by"])

        for turn in dict.fromkeys(turns):
            for a in self._c.operational(turn=turn):
                if a["act"] != "expectation-recorded":
                    continue
                consider(a["id"], turn)
                if a.get("caused_by") and steps_up(a):
                    consider(a["caused_by"], turn, via=a["id"])
        # ONE LINE OF WORK IS NOT TWO CANDIDATES. A continuation's request is
        # caused by the request it continued, and the two Turns read here can
        # hold one each, so both are found; the record already says the
        # nearer one IS the continuation of the other, so the ancestor is
        # dropped. Two requests with no such link between
        # them stay two, and are refused as ambiguous by the caller.
        continued = {self._act(c["expectation"]).get("caused_by") for c in out}
        return [c for c in out if c["expectation"] not in continued]

    # -- what a piece of work is waiting on ------------------------------------
    #
    # COMPUTED, NEVER STORED. There is no ready flag, no status field and no
    # stage: whether work is still waiting is read from the expectations raised
    # under it and what has happened to each. What it waits on is exactly what
    # it DECLARED -- a child delegated with `returns_to`, a decision it asked
    # the owner, or input it said it waits for (`request_input`). Side work it did not say it needed is not waited on, so it
    # cannot hold the work up and cannot wake it either.
    #
    # AND "NO LONGER WAITING" IS NOT "SATISFIED". A child that returned has
    # returned something; one that failed has failed. Neither is a verdict on
    # whether the work needed is done -- that is the judgement of whoever
    # carries the parent, when it resumes. Nothing here claims otherwise.

    def _child_state(self, expectation) -> dict:
        """What one child's own record shows, in the record's own words."""
        s = self.expectation_state(expectation)
        mine = self._own_acts(expectation)
        ends = [a for a in mine if a["act"] in RUN_ENDS]
        last = max(ends, key=lambda a: a["at"]) if ends else None
        # SENT TO ANOTHER RUNTIME SINCE IT LAST ENDED (`dispatch.recover_
        # child`): the run that will answer it has not ended, so nothing
        # waiting on it reads it as ended.
        moved = [a["at"] for a in mine if a["act"] == "work-reassigned"]
        if s["live_execution"]:
            state = "running"
        elif last is None or (moved and max(moved) > last["at"]):
            state = "not-ended"
        elif last["act"] == RESULT_RETURNED:
            state = "returned"
        elif last["act"] == RESULT_RECOVERED:
            state = "recovered"
        else:
            state = (last["detail"].get("terminal")
                     or ("failed-before-start"
                         if last["detail"].get("before_execution_started")
                         else "failed"))
        # WHAT IT HANDED BACK, as well as what it said. Read from the returns
        # recorded under this child's own request, whichever of its runs made
        # them and however it ended: bytes Mentis holds are held whether or
        # not the run that returned them went on to succeed.
        returned = [a["about"][0] for a in self._children(expectation)
                    if a["act"] == ARTIFACT_RETURNED and a["about"]]
        return {"expectation": expectation, "carrier": s["expected_of"],
                "state": state, "ended_by": last["id"] if last else None,
                "ended_at": last["at"] if last else None,
                "because": last.get("because") if last else None,
                "replies": s["replies_from_expected"],
                "returned_artifacts": returned,
                "claimed_met_by": s["satisfied_by"]}

    def waiting_on(self, parent) -> dict:
        """What this work declared it needs, and whether any is outstanding."""
        required, decisions, inputs = [], [], []
        for a in self._children(parent):
            if a["act"] != "expectation-recorded":
                continue
            if a["detail"].get("expects") == INPUT:
                s = self.expectation_state(a["id"])
                given = s["input"]["ready"]
                inputs.append({"expectation": a["id"],
                               "owed_by": s["expected_of"],
                               "set": s["input"]["set"],
                               "answered": s["response_present"],
                               "withdrawn": s["withdrawn"],
                               # the latest Done since the wait, and the
                               # exact answers it covered
                               "marked_ready": (given[-1]["marked_ready"]
                                                if given else None),
                               "answers": (given[-1]["answers"]
                                           if given else []),
                               "ready_at": given[0]["at"] if given else None})
            elif a["detail"].get("expects") == "decision":
                # A RUN'S PERMISSION QUESTION IS THE RUN'S, NOT THE WORK'S
                # (`mentis/web/permissions.py`): the run that asked it waited
                # for the answer and took it. The work never waits on it, so
                # answering it -- or it standing open after the run ended --
                # neither holds the work nor resumes it.
                if self._permission_form(a["detail"].get("form")):
                    continue
                s = self.expectation_state(a["id"])
                if a["detail"].get("form"):
                    # the reply that named this question, and no other
                    answers = list(s["replies_from_expected"])
                else:
                    answers = [e["link"]["from"] for e in
                               self._replies_to(a["turn"])
                               if s["expected_of"] and self._entry(
                                   e["link"]["from"])[0]["attributed_to"]
                               == s["expected_of"]]
                decisions.append({"expectation": a["id"],
                                  "owed_by": s["expected_of"],
                                  "answered": s["response_present"],
                                  "withdrawn": s["withdrawn"],
                                  "answers": answers,
                                  **({"form": a["detail"]["form"]}
                                     if a["detail"].get("form") else {})})
            elif a["detail"].get("returns_to"):
                required.append(self._child_state(a["id"]))
        awaited = [self.awaited_state(w) for w in self.awaits(parent)]
        # THE DECISION FORMS IT ASKED (P7): closed when every question is
        # answered or withdrawn. Their questions are among `decisions`, so
        # an open one is outstanding as any decision is.
        forms = [{"form": f["form"], "post": f["post"],
                  "closed": f["closed"], "closed_at": f["closed_at"],
                  "questions": [q["expectation"] for q in f["questions"]]}
                 for f in self._forms_waited(parent)
                 if not self._permission_form(f["form"])]
        outstanding = ([c["expectation"] for c in required
                        if c["state"] in ("running", "not-ended")]
                       + [d["expectation"] for d in decisions
                          if not d["answered"]]
                       + [i["expectation"] for i in inputs
                          if not i["answered"]]
                       + [w["expectation"] for w in awaited if not w["ended"]])
        return {"parent": parent, "required": required,
                "decisions": decisions, "inputs": inputs, "awaited": awaited,
                "forms": forms, "outstanding": outstanding}

    def recovery_hold(self, parent, *, waiting=None, own=None) -> list[dict]:
        """The required children whose RECOVERED result holds this work.

        A RECOVERED RESULT CONTINUES NOTHING BY ITSELF -- the owner's rule.
        While a child this work needs came back by recovery after this work
        last started or was resumed, whatever else ends here resumes nothing:
        continuing on a recovered result is a person's act. Once somebody
        continues it -- a new run or a resumption -- the recovery is behind it
        and ordinary resumption applies again.

        ONE RULE, READ BY BOTH SIDES: `claim_resumption` refuses on it and work
        status shows it, so what is shown and what happens cannot disagree.

        AWAITED DELEGATED WORK HOLDS IT THE SAME WAY. Its run ending ends the
        wait on it (`awaited_state`), so a recovered end would otherwise
        resume the waiting work by itself -- unless it was claimed met after.
        And a continuation running is this work running (`continuations_of`),
        so it puts the recovery behind it as this work's own run would.
        """
        waiting = waiting if waiting is not None else self.waiting_on(parent)
        line = self._line_acts(parent, own)
        since = max([a["at"] for a in line
                     if a["act"] in ("execution-started", "work-resumed")],
                    default=0)
        return ([c for c in waiting["required"]
                 if c["state"] == "recovered" and c["ended_at"]
                 and c["ended_at"] > since]
                + [w for w in waiting["awaited"]
                   if w["returned"] == "recovered" and not w["met_after"]
                   and w["returned_at"] > since])

    def interruption_hold(self, parent, *, waiting=None, own=None
                          ) -> list[dict]:
        """The interruptions that hold this work from resuming by itself.

        INTERRUPTED WORK CONTINUES BY A PERSON'S ACT, as work on a recovered
        result does (`recovery_hold`). A run the wake check found interrupted
        is ended with `delivery-failed`, `terminal: "interrupted"`
        (`mentis.wakecheck`) -- which stops the request reading as live, and
        would otherwise let the next child that ends resume it automatically.

        HELD while the interrupted run is still this work's latest start or
        resumption, or a required child's interrupted run started after this
        work last ran. In WRITE ORDER, not by clock, and judged from the
        interrupted START: an interruption is often found -- and its end
        written -- after somebody had already continued the work, and that
        continuation must count.

        A CONTINUATION'S RUNS ARE THIS WORK'S RUNS (`continuations_of`): one
        started after the interruption is somebody having continued it, and
        one interrupted while it was the latest is this work interrupted.

        AWAITED DELEGATED WORK whose run was interrupted holds it unless it
        was claimed met after -- judged from the interrupted END, as
        `recovery_hold` judges a recovered one. A required child is delegated
        during this work's run, so its interrupted run always started after
        that run did; awaited work is often ALREADY RUNNING when `await_work`
        is called (#854: a deploy waiting on a recheck in flight), so its
        interrupted run can start before this work's latest run, and by its
        start it would never hold. What the waiting work's carrier ran on was
        that run still going; it never saw the interruption until its end
        was written.
        """
        waiting = waiting if waiting is not None else self.waiting_on(parent)
        line = self._line_acts(parent, own)
        runs = [a for a in line
                if a["act"] in ("execution-started", "work-resumed")]
        interrupted = [a for a in line if a["act"] == DELIVERY_FAILED
                       and (a.get("detail") or {}).get("terminal")
                       == "interrupted"]
        kids = [(c, c["ended_by"]) for c in waiting["required"]
                if c["state"] == "interrupted" and c["ended_by"]]
        awaited = [(w, w["returned_by"]) for w in waiting["awaited"]
                   if w["returned"] == "interrupted" and w["returned_by"]
                   and not w["met_after"]]
        kid_starts = {end: (self._act(end) or {}).get("caused_by")
                      for _, end in kids}
        order = self._write_order([a["id"] for a in runs + interrupted]
                                  + [s for s in kid_starts.values() if s]
                                  + [end for _, end in awaited])
        latest = max(runs, key=lambda a: order.get(a["id"], -1),
                     default=None)
        last = order.get(latest["id"], -1) if latest else -1
        held = [{"expectation": parent, "ended_by": a["id"],
                 "ended_at": a["at"]} for a in interrupted
                if latest is not None and a.get("caused_by") == latest["id"]]
        return (held + [c for c, end in kids
                        if order.get(kid_starts.get(end), -1) > last]
                + [w for w, end in awaited if order.get(end, -1) > last])

    def continuations_of(self, parent) -> list[str]:
        """The requests that continue this one: raised under it by its own
        requester, with authority whose recorded origin is this work."""
        exp = self._act(parent)
        if exp is None:
            return []
        return [a["id"] for a in self._children(parent)
                if a["act"] == "expectation-recorded"
                and a["actor"] == exp["actor"]
                and self.authority_of(a["id"])["origin"] == parent]

    def _line_acts(self, parent, own=None) -> list[dict]:
        """This work's own acts and its continuations': one line of work."""
        own = own if own is not None else self._own_acts(parent)
        return own + [a for c in self.continuations_of(parent)
                      for a in self._own_acts(c)]

    def continuation_pending(self, continuation) -> bool:
        """Is this continuation about to run: recorded or resumed, not yet
        started, not ended since, and not closed?

        It has been dispatched -- runtime selection, summoning and worktree
        setup are between that and its run starting -- so it reads as
        neither live nor having run. A child of the work it continues ending
        in that gap must not resume that work as well: the carrier would get
        two runs of the same work (`claim_resumption`).

        BOUNDED BY THE SERVER THAT DISPATCHED IT. The dispatch is a thread of
        that server, and every way it fails while that server lives is
        recorded (`dispatch._failed_before_start`). One lost with the server
        itself leaves nothing, so a server starting closes every continuation
        still pending from before it (`wakecheck.close_lost_dispatches`), with
        a `delivery-failed` that says so -- and this reads it as ended.
        """
        s = self.expectation_state(continuation)
        if s["satisfied_by"] or s["withdrawn"]:
            return False
        acts = self._own_acts(continuation)
        moved = [a for a in acts if a["act"] in ("execution-started",
                                                 *RUN_ENDS)]
        if not moved:
            return True
        resumed = [a for a in acts if a["act"] == "work-resumed"]
        order = self._write_order([a["id"] for a in moved + resumed])
        last_moved = max(order.get(a["id"], -1) for a in moved)
        return any(order.get(a["id"], -1) > last_moved for a in resumed)

    def claim_resumption(self, parent, *, event) -> str | None:
        """Record, at most once per completion, that this work resumes.

        THE ACT IS THE GUARD. Checked and written inside one transaction, so of
        two children finishing at the same moment exactly one writes it and the
        other finds it already written. Returns the act, or None with nothing
        written when the work is still waiting, already answered, already
        running, or has nothing new to resume for.

        "NOTHING NEW" is what stops a loop: the work resumes only for a required
        child that ENDED after the work last ran or was last resumed -- so a run
        of the parent ending never resumes it on results it has already had.
        """
        with self._c.atomic():
            exp = self._act(parent)
            if exp is None or exp["act"] != "expectation-recorded":
                return None
            state = self.expectation_state(parent)
            if state["satisfied_by"] or state["live_execution"]:
                return None
            waiting = self.waiting_on(parent)
            if ((not waiting["required"] and not waiting["awaited"]
                 and not waiting["inputs"] and not waiting["forms"])
                    or waiting["outstanding"]):
                return None
            own = self._own_acts(parent)
            # A CONTINUATION IS THIS WORK RUNNING. The owner's reply that
            # continues it (`continuation_candidates`) is its own request,
            # so its runs are not among this work's own acts -- but what it
            # ran on was this work's results. Live, it is this work live;
            # started, it is this work having run. Without this, the
            # continuation ending resumed the work a second time on results
            # the continuation had already had. And dispatched but not yet
            # started is live too (`continuation_pending`): a child ending in
            # that gap would otherwise resume this work beside it, and the
            # carrier would get two runs of the same work. Its run starts
            # after that child ended, so it has the child's result.
            continuing = self.continuations_of(parent)
            if any(self.expectation_state(c)["live_execution"]
                   or self.continuation_pending(c) for c in continuing):
                return None
            cont = [a for c in continuing for a in self._own_acts(c)]
            since = max([a["at"] for a in own + cont
                         if a["act"] in ("execution-started", "work-resumed")],
                        default=0)
            # SOMETHING NEW: a child that ended, or awaited work that ended,
            # since this work last ran or was last resumed -- or an input it
            # waited for, first marked ready since then and never handed to
            # it. Once per wait: a later Done on the same set is not new to
            # a run that started after the first, and resumes nothing.
            handed = {i["expectation"] for a in own + cont
                      if a["act"] == "work-resumed"
                      for i in (a["detail"] or {}).get("inputs") or ()}
            fresh = [i for i in waiting["inputs"]
                     if i["answered"] and i["marked_ready"]
                     and i["expectation"] not in handed
                     and i["ready_at"] and i["ready_at"] > since]
            # ...or a decision form it asked, whose LAST question was
            # answered or withdrawn since then and that was never handed to
            # it: once per form. A decision asked as its own Turn resumes
            # nothing by itself, as before.
            given = {f for a in own + cont if a["act"] == "work-resumed"
                     for f in (a["detail"] or {}).get("forms") or ()}
            closed = [f for f in waiting["forms"]
                      if f["closed"] and f["form"] not in given
                      and f["closed_at"] and f["closed_at"] > since]
            if not (any(c["ended_at"] and c["ended_at"] > since
                        for c in waiting["required"])
                    or any(w["ended_at"] and w["ended_at"] > since
                           for w in waiting["awaited"])
                    or fresh or closed):
                return None
            if self.recovery_hold(parent, waiting=waiting, own=own):
                return None
            if self.interruption_hold(parent, waiting=waiting, own=own):
                return None
            carrier = self.assigned_carrier(parent)["carrier"]
            if carrier is None:
                return None
            authority = self.authority_of(parent)
            return self._c.record_operational(
                actor="mentis", act="work-resumed",
                conversation=exp["conversation"], turn=exp["turn"],
                caused_by=parent, about=[carrier],
                because="nothing this work declared it was waiting on is "
                        "outstanding; whether what came back is adequate is "
                        "for its carrier to judge",
                detail={"parent": parent, "event": dict(event),
                        "required": waiting["required"],
                        "decisions": waiting["decisions"],
                        "awaited": waiting["awaited"],
                        # WHICH REVISION OF EACH INPUT IT IS GIVEN: the
                        # latest Done and the exact answers that covered,
                        # and the own words and interpretations as they
                        # stood (their entries, and each one's state).
                        **({"inputs": [
                            {**{k: i[k] for k in ("expectation", "set",
                                                  "marked_ready", "answers",
                                                  "withdrawn")},
                             **self._input_handover(i["set"])}
                            for i in waiting["inputs"]]}
                           if waiting["inputs"] else {}),
                        # THE DECISION FORMS NOW CLOSED, handed over once.
                        **({"forms": [f["form"] for f in waiting["forms"]
                                      if f["closed"]]}
                           if waiting["forms"] else {}),
                        "carrier": carrier,
                        "authority": {k: authority.get(k) for k in
                                      ("source", "origin", "act",
                                       "operations")},
                        # Said, rather than left to be inferred: this act
                        # establishes no child as having done its work.
                        "satisfied": None})

    # -- waiting on work it did not delegate -----------------------------------
    #
    # THE THIRD THING WORK MAY DECLARE IT WAITS ON. A child it delegated, a
    # decision it asked -- and here, other work already in the record that it
    # did not create: a request somebody else carries that has to be finished
    # before this one can go on. Declared by an act (`work-awaited`, caused by
    # the waiting work, about the awaited one), never inferred from prose or
    # from two pieces of work sharing a Conversation, a branch or a carrier.
    #
    # WHAT ENDS THIS WAIT IS A CLAIM OF FULFILMENT, NOT A RUN ENDING. A child
    # ends its parent's wait however its run ends, because a child is one run
    # of one piece of work. Work somebody else carries has as many runs as it
    # needs -- a coordinator returns every time it pauses for its own children
    # -- so one of its runs ending says nothing about whether it is finished.
    # `expectation-met` does, as its carrier's claim -- unless the awaited
    # work IS a delegated child, which ends any wait on it as it ends its
    # parent's (`awaited_state`). Neither is a check: whether it is adequate
    # is for the waiting work's carrier to judge when it resumes.
    #
    # NOTHING POLLS. Awaited work is claimed met inside one of its runs, and a
    # run ending is already when Mentis asks what was waiting on it.

    def is_finding(self, expectation) -> bool:
        """Was this request kept as discovered work (`record_discovered_work`)?

        Its `caused_by` is then where it was found -- provenance -- and not
        work it is part of.
        """
        exp = self._act(expectation)
        return bool(exp and exp["act"] == "expectation-recorded"
                    and exp.get("turn") and any(
            a["act"] == "work-discovered" and expectation in (a["about"] or ())
            for a in self._c.operational(turn=exp["turn"])))

    def awaits(self, expectation) -> list[str]:
        """The work this expectation declared it waits on, in declared order."""
        return list(dict.fromkeys(
            a["about"][0] for a in self._children(expectation)
            if a["act"] == WORK_AWAITED and a["about"]))

    def awaited_by(self, awaited) -> list[str]:
        """Every expectation that declared it waits on this one."""
        return list(dict.fromkeys(
            a["caused_by"] for a in self._c.operational(act=WORK_AWAITED)
            if a["about"] and a["about"][0] == awaited and a["caused_by"]))

    def awaited_state(self, awaited) -> dict:
        """What the record says of awaited work, in its own words."""
        s = self.expectation_state(awaited)
        met = [a for a in self._own_acts(awaited)
               if a["act"] == "expectation-met"]
        met_at = max((a["at"] for a in met), default=None)
        # A DELEGATED CHILD ENDS THE WAIT AS IT ENDS ITS PARENT'S: when its
        # run ends. It is one run of one piece of work, handed back to whoever
        # delegated it without claiming it met -- that judgement is theirs --
        # so a wait that ended only on `expectation-met` never ended on it
        # (#854: a deploy waiting on a recheck, opr-313329a5b482). Other work
        # still ends the wait only when claimed met. Ended is not satisfied.
        child = (self._child_state(awaited)
                 if (self._act(awaited)["detail"] or {}).get("returns_to")
                 else None)
        #
        # ENDED IS NOT FREE TO RESUME. A run that was recovered or interrupted
        # ends the wait too, but continuing on it is a person's act: the
        # waiting work's `recovery_hold` and `interruption_hold` hold it, as
        # they hold it for its own children -- unless the awaited work was
        # claimed met after that end (`met_after`).
        #
        # AND A RUN ENDING MAY BE A PAUSE. A child that itself delegated, or
        # asked, ends a run every time it waits on that, and each such end
        # ends this wait until it resumes -- as it resumes its own parent.
        # `paused` names what it is still waiting on, so the resumed carrier
        # is told it paused rather than finished.
        returned = bool(child and child["state"] not in ("running",
                                                         "not-ended"))
        returned_at = child["ended_at"] if returned else None
        return {"expectation": awaited, "carrier": s["expected_of"],
                "conversation": s["conversation"], "turn": s["turn"],
                "met": bool(met), "met_by": [a["id"] for a in met],
                "met_at": met_at,
                "claimed_by": sorted({a["actor"] for a in met}),
                "returned": child["state"] if returned else None,
                "returned_by": child["ended_by"] if returned else None,
                "returned_at": returned_at,
                "met_after": bool(met_at and returned_at
                                  and met_at > returned_at),
                "paused": (self._pausing_on(awaited)
                           if returned and not met else []),
                "ended": bool(met) or returned,
                "ended_at": max([t for t in (met_at, returned_at) if t],
                                default=None)}

    def _pausing_on(self, expectation) -> list[str]:
        """What this work, between runs, still declared it waits on: its
        children not ended, its decisions unanswered, its inputs not marked
        ready, and other work it awaits not claimed met. Not `waiting_on`,
        which reads awaited work through `awaited_state` and so would read
        this again."""
        out = []
        for a in self._children(expectation):
            if a["act"] == "expectation-recorded":
                if a["detail"].get("expects") in ASKED_UNDER_WORK:
                    if not self.expectation_state(a["id"])["response_present"]:
                        out.append(a["id"])
                elif (a["detail"].get("returns_to")
                      and self._child_state(a["id"])["state"]
                      in ("running", "not-ended")):
                    out.append(a["id"])
        out += [w for w in self.awaits(expectation)
                if not any(a["act"] == "expectation-met"
                           for a in self._own_acts(w))]
        return out

    def await_work(self, expectation, awaited, *, by, because=None,
                   execution=None, runtime=None) -> str:
        """Record that this work waits until `awaited` is claimed met.

        Refused, in words, where the wait could never end or would mean
        nothing: waiting on itself, on a decision (that is `request_decision`),
        on something that is not a request, on work already claimed met, on
        the work this was raised under, or on work that is itself -- however
        indirectly -- waiting on this. Declaring the same wait twice returns
        the first declaration and records nothing.
        """
        # ONE TRANSACTION, because the docstring promises a wait that could
        # never end is refused BEFORE anything is recorded -- and a check
        # outside the write does not promise that. Two workers declaring
        # A-waits-on-B and B-waits-on-A at the same moment both passed the
        # cycle walk and both wrote, leaving a mutual wait nothing can end.
        # The same guard `claim_resumption` states: checked and written
        # inside one transaction, so exactly one of a racing pair wins.
        with self._c.atomic():
            exp = self._act(expectation)
            if exp is None or exp["act"] != "expectation-recorded":
                raise ValueError(f"{expectation!r} is not a request in this record")
            if awaited == expectation:
                raise ValueError("work cannot wait on itself")
            target = self._act(awaited)
            if target is None or target["act"] != "expectation-recorded":
                raise ValueError(
                    f"{awaited!r} is not a request in this record, so nothing "
                    f"could ever claim it met. Only work Mentis holds can be "
                    f"waited on")
            if (target.get("detail") or {}).get("expects") == "decision":
                raise ValueError(
                    f"{awaited!r} is a decision somebody was asked. A decision "
                    f"this work needs is asked with request_decision")
            if (target.get("detail") or {}).get("expects") == INPUT:
                raise ValueError(
                    f"{awaited!r} is input somebody was asked for. Input this "
                    f"work needs is waited for with request_input")
            for a in self._c.operational(caused_by=expectation):
                if (a["act"] == WORK_AWAITED and a["about"]
                        and a["about"][0] == awaited):
                    return a["id"]
            already = self.awaited_state(awaited)
            if already["met"]:
                raise ValueError(
                    f"{awaited!r} is already claimed met, so there is nothing to "
                    f"wait for; read what answered it and go on")
            if already["ended"]:
                raise ValueError(
                    f"{awaited!r} was delegated work and has already "
                    f"{already['returned']}, so there is nothing to wait for; "
                    f"read what it handed back and go on")
            # WHAT THIS WAS RAISED UNDER IS THE WORK IT IS PART OF, NOT WHERE
            # IT WAS FOUND. A finding is caused by the work that discovered it,
            # as its provenance; it is its own work, so the walk stops at it
            # and a finding may wait on the work it was found under like any
            # other.
            up = set()
            cause = None if self.is_finding(expectation) else exp.get("caused_by")
            while cause and cause not in up:
                up.add(cause)
                if self.is_finding(cause):
                    break
                got = self._act(cause)
                cause = got.get("caused_by") if got else None
            if awaited in up:
                raise ValueError(
                    f"{awaited!r} is the work this was raised under. It is not "
                    f"finished until this is, so waiting on it would never end")
            # WHAT HOLDS WORK IS EVERY OBLIGATION IT RECORDED: what it declared
            # it awaits, and the children it delegated and needs back that have
            # not ended. Where it was found holds nothing.
            seen, frontier = set(), [awaited]
            while frontier:
                nxt = []
                for w in frontier:
                    if w in seen:
                        continue
                    seen.add(w)
                    ahead = self.awaits(w) + [
                        a["id"] for a in self._c.operational(caused_by=w)
                        if a["act"] == "expectation-recorded"
                        and a["detail"].get("returns_to")
                        and self._child_state(a["id"])["state"]
                        in ("running", "not-ended")]
                    if expectation in ahead:
                        raise ValueError(
                            f"{awaited!r} is already waiting"
                            + ("" if w == awaited else ", through other work,")
                            + " on this. Each would wait for the other forever")
                    nxt += ahead
                frontier = nxt
            return self._c.record_operational(
                actor=by, act=WORK_AWAITED, conversation=exp["conversation"],
                turn=exp["turn"], execution=execution, runtime=runtime,
                because=because, caused_by=expectation, about=[awaited],
                detail={"until": "expectation-met",
                        "awaited_conversation": target["conversation"],
                        "awaited_turn": target["turn"]})

    # -- ordinary operational recording ---------------------------------------

    def record_act(self, *, actor, act, conversation=None, turn=None,
                   execution=None, runtime=None, because=None, caused_by=None,
                   about=(), detail=None) -> str:
        """Record something an actor did. No Turn is created."""
        return self._c.record_operational(
            actor=actor, act=act, conversation=conversation, turn=turn,
            execution=execution, runtime=runtime, because=because,
            caused_by=caused_by, about=about, detail=detail)

    # -- a run's end that nothing in Mentis saw ----------------------------------

    def _write_order(self, ids) -> dict:
        """The record's own write order for these acts: id -> seq.

        FROM THE READING'S OWN ANSWERS WHEN IT HOLDS ALL OF THEM. A walk
        `_prefetch_lineage` made read each act's `seq` beside it, from the
        same record, so where every id asked about was read there, that is
        the answer this read would give -- nothing it does not hold is
        guessed, and one id it lacks sends the whole question to the store."""
        ids = [i for i in ids if i]
        if not ids:
            return {}
        got = {}
        for i in ids:
            seq = self._settled_already(("seq", i))
            if seq is None:
                return self._c.operational_order(ids)
            got[i] = seq
        return got

    def run_end(self, started) -> dict | None:
        """The act that ended the run this `execution-started` began, or None.

        BY THE START ACT, NEVER BY THE EXECUTION ID. Instances are reused, so
        one execution id carries many runs, and an earlier run's result does
        not end a later run. Every end act hangs off its own start by
        `caused_by`, which is what is asked here. The first in write order.
        """
        ends = [a for a in self._c.operational(caused_by=started)
                if a["act"] in RUN_ENDS]
        if not ends:
            return None
        seq = self._write_order(a["id"] for a in ends)
        return min(ends, key=lambda a: seq.get(a["id"], -1))

    def run_window(self, started) -> dict:
        """This run's start, and the next start on the same execution, if any.

        The run is everything between the two. In write order, because two
        starts in one clock tick are still one before the other.
        """
        start = self._act(started)
        if start is None or start["act"] != "execution-started":
            raise ValueError(f"{started!r} is not an execution-started act")
        if not start.get("execution"):
            raise ValueError(f"{started!r} names no execution")
        starts = [a for a in self._c.operational(execution=start["execution"])
                  if a["act"] == "execution-started"]
        seq = self._write_order(a["id"] for a in starts)
        later = sorted((a for a in starts
                        if seq.get(a["id"], -1) > seq.get(started, -1)),
                       key=lambda a: seq[a["id"]])
        nxt = later[0] if later else None
        return {"start": start, "next_start": nxt,
                "since": start["at"], "until": nxt["at"] if nxt else None}

    def recovery_refusal(self, started, recovered_by) -> dict:
        """Raise why the record refuses to recover this run; else its window.

        Asked by the route BEFORE any evidence is read, so a run that ended or
        was superseded is refused for that reason, and asked again inside the
        write by `recover_result`, so nothing can change in between.
        """
        window = self.run_window(started)
        start = window["start"]
        if not recovered_by or not self._is_kind(recovered_by, PARTICIPANT):
            raise ValueError(f"{recovered_by!r} is not a Participant")
        ended = self.run_end(started)
        if ended is not None:
            raise ValueError(f"this run already has an end: {ended['act']} "
                             f"{ended['id']}; nothing was lost to recover")
        siblings = ([a for a in self._c.operational(caused_by=start["caused_by"])
                     if a["act"] == "execution-started"]
                    if start.get("caused_by") else [])
        seq = self._write_order([started] + [a["id"] for a in siblings])
        newer = [a for a in siblings if seq.get(a["id"], -1) > seq[started]]
        if newer:
            raise ValueError(
                "a later run of the same request has started ("
                + ", ".join(a["id"] for a in newer) + "); recovering this "
                "one would put an older result in front of it")
        return window

    def recover_result(self, *, started, said, recovered_by, evidence,
                       because, written_by, next_start, recorded_through=None
                       ) -> dict:
        """End a run whose end Mentis lost, with the result its runtime wrote.

        WHAT HAPPENED, AND WHAT THIS RECORDS. A run's end is normally recorded
        by the dispatch waiter that watched it. That waiter lives in the server
        process, so when that server stops -- including when the run itself
        restarts it -- the waiter dies with it, the runtime can carry on and
        finish, and the record is left with a start and nothing else.

        This records the result WITHOUT PRETENDING OTHERWISE. It posts the
        runtime's own words as the reply, attributed as dispatch would have
        attributed them -- to the Participant, written by the runtime session
        the evidence names -- and records `result-recovered`, never
        `result-returned`. Its `actor` is the Participant who recovered it, and
        its detail says that nothing in Mentis observed the end
        (`observed_end: False`), what the server checked (`evidence.checked`),
        what it could not establish (`evidence.not_established`), and why the
        recoverer says the end was lost (`because`, theirs, not checked).

        `said` and `evidence` come from `mentis.recovery.final_message`, read by
        the server for exactly the window `run_window` gave; `next_start` is the
        bound that window used, re-checked here so a run started in between
        cannot be hidden inside it.

        EVERYTHING THAT DECIDES WHETHER TO WRITE IS CHECKED INSIDE THE WRITE.
        Two recoveries of one run at once cannot both pass: the transaction
        holds the store's write lock from the first check to the last write.
        Refuses when:
          * the start is not a start, or `recovered_by` is not a Participant;
          * the run already has an end (nothing was lost to recover);
          * a later run of the same request has started -- recovering this
            one would put an older result in front of a newer run's;
          * the next start on this execution is not the one the evidence was
            bounded by.

        AFTER THIS THE RUN COUNTS AS ENDED, everywhere a run's end is read.
        Recording it resumes nothing at that moment: dispatch is not asked, and
        no parent is woken from here. But a parent waiting on this run no longer
        counts it as outstanding, so the next time the parent's wait is
        re-checked -- when another child it waits on ends, or its own run ends
        -- it may resume, exactly as it would for any other ended child.
        """
        said = (said or "").strip()
        if not said:
            raise ValueError("a recovered result needs the text the run wrote")
        if not isinstance(because, str) or not because.strip():
            raise ValueError("say why this is being recovered, in words")
        with self._c.atomic():
            window = self.recovery_refusal(started, recovered_by)
            start = window["start"]
            bound = (window["next_start"] or {}).get("id")
            if bound != next_start:
                raise ValueError("the next start on this execution changed "
                                 "since the evidence was read; read it again")
            # WHAT THIS RUN HANDED BACK: returns under its request, on its
            # execution, written after its start and before the next start on
            # that execution -- so neither an earlier nor a later run's bytes.
            # A start that names no request claims none: matching `None` would
            # take every uncaused return on the execution.
            mine = [a for a in self._c.operational(execution=start["execution"])
                    if a["act"] == ARTIFACT_RETURNED and a["about"]
                    and start.get("caused_by")
                    and a.get("caused_by") == start["caused_by"]]
            # ONE RUN, ONE ANSWER -- HERE TOO, AND BOUNDED THE SAME WAY. A lost
            # run may have answered through `respond` before its waiter died:
            # the answer is in the record and only its ENDING was lost, so
            # recovering the ending must not post the runtime's final words
            # beside an answer that already stands.
            #
            # THE BOUND IS NOT OPTIONAL, FOR THE REASON THE DISPATCH BOUNDARY
            # LEARNED. `execution` is an INSTANCE and not a run: `_resume`
            # re-dispatches the same expectation and the same Turn to the same
            # carrier, so a second run shares both halves of the key. Unbounded,
            # recovering run two reads run one's answer -- typically an interim
            # `I have delegated this` -- and run two's real result never becomes
            # a Turn at all. This window is the one the artifacts below already
            # use: after this run started, and before the next start on this
            # instance.
            answers = [a for a in self._c.operational(execution=start["execution"])
                       if a.get("turn")
                       and (a.get("detail") or {}).get("answers_turn")
                       == start["turn"]]
            order = self._write_order([started, bound]
                                      + [a["id"] for a in mine]
                                      + [a["id"] for a in answers])
            hi = order.get(bound) if bound else None
            returned = [a["about"][0] for a in
                        sorted(mine, key=lambda a: order[a["id"]])
                        if order[a["id"]] > order[started]
                        and (hi is None or order[a["id"]] < hi)]
            # BOUNDED BELOW ONLY, WHICH IS THE DISPATCH RULE AND NOT THE
            # ARTIFACT ONE. The artifacts above stop at the next start because a
            # later run's files are that run's. An answer is bounded below only,
            # and the reason is narrower than "no later run exists": this
            # function is reached only through `recovery_refusal`, which scopes
            # its siblings by `caused_by` -- the EXPECTATION -- and refuses when
            # a later run of that expectation has started. So what is guaranteed
            # here is that no later run OF THIS EXPECTATION exists, which is one
            # notch narrower than "of this request": a Turn may carry several
            # expectations, and `answers` is matched on `answers_turn`. That gap
            # is not this window's to close and is shared exactly with
            # `dispatch._already_answered`, which matches the same way; see the
            # follow-up recorded in `docs/evidence/provenance-join-defects.md`.
            #
            # WHAT THE UPPER BOUND WOULD COST. Recovery's whole premise is that
            # the waiter died and THE RUNTIME CARRIED ON, so a zombie run can
            # answer after its instance was adopted for other work. Bounding
            # above at the next start would read that answer as "never
            # answered" and post the run's final words a second time -- the
            # duplicate this branch exists to remove.
            already = next((a["turn"] for a in
                            sorted(answers, key=lambda a: order.get(a["id"], -1))
                            if order.get(a["id"], -1) > order[started]), None)
            if already is None:
                reply = self.say(start["conversation"], start["actor"],
                                 [text(said)], replies_to=start["turn"],
                                 written_by=written_by)
            else:
                reply = already
            # THE ACT STAYS ON THE TURN, AND THE BADGE IS MADE HONEST INSTEAD.
            # Naming no Turn removed the false "recovered" badge from an answer
            # `respond` had written -- and took a true fact with it: the view
            # builds a Turn's `returned_with` from this act's
            # `returned_artifacts`, so an orphaned act made a recovered run's
            # returned files invisible everywhere, and the act itself vanished
            # from the History pane and causal graph under a Topic scope. What
            # was wrong was never the act's placement but the claim read off it,
            # so `response_owner` below is what the view reads to decide whether
            # this Turn was recovered or merely belongs to a run whose ENDING
            # was.
            act = self.record_act(
                actor=recovered_by, act=RESULT_RECOVERED,
                conversation=start["conversation"], turn=reply,
                execution=start["execution"], runtime=start.get("runtime"),
                caused_by=started, because=because,
                detail={"observed_end": False,
                        # WHOSE ANSWER THIS ENDING BELONGS TO, and the final
                        # text when it was not itself the answer -- kept as
                        # evidence rather than delivered a second time.
                        "response_owner": ("respond" if already
                                           else "recovery"),
                        **({"final_text": said,
                            "final_text_why": (
                                "recovered from the runtime's own output after "
                                "this run had already answered; kept as "
                                "evidence of the lost ending, not as a second "
                                "answer")}
                           if already and said else {}),
                        "recovered_for": start["actor"],
                        "started_at": start["at"],
                        "next_start": bound,
                        "evidence": dict(evidence or {}),
                        "returned_artifacts": returned,
                        "recorded_through": recorded_through,
                        "resumed_anything": False})
        return {"act": act, "reply": reply, "started": started,
                "execution": start["execution"],
                "returned_artifacts": returned}

    def open_runs(self, *, execution=None) -> list[dict]:
        """Every run the record says was started and nothing has ended.

        Durable, so it survives a restart -- and it says nothing about whether
        a process is still inside one. That is a separate question, asked of
        whatever process might hold it (see `mentis.operational.runs`).

        ON `closed_starts`, DELIBERATELY. This was first written against a
        by-execution-id reading, which had one error: an instance handle is
        REUSABLE, so an end belonging to an earlier run closed a later run on
        the same handle. main fixed that separately and better, placing an end
        by the start it hangs off (`caused_by`) and treating a later run's end
        as superseding earlier starts on that handle. Reading it that way here
        means a run attempt is never confused with the persistent instance it
        borrowed, and `result-recovered` -- which main added and the older
        reading never knew about -- closes a run exactly as the other two ends
        do. There is one rule for when a run is over, and this is not a second
        copy of it.
        """
        # ONE PASS. Asking for every act and filtering in Python decoded the
        # `about` and `detail` JSON of every row in the record to keep about
        # two percent of them -- measured at 429ms against 28ms on a 50k-act
        # store, with the store lock held, on a path every dispatch and every
        # UI poll takes.
        #
        # AND MARKS FIRST, BODIES ONLY FOR WHAT IS OPEN. Which starts are
        # closed is decided by id, instance, causal parent and write order --
        # nothing in `detail` -- yet every start's whole detail was read and
        # decoded to decide it: 71 MB over 3,075 starts on the live Brain
        # (2026-10-27), 400 ms of every `/api/working` and `/api/activity`
        # poll, growing with every run ever dispatched. The marks carry their
        # own `seq`, which is the write order `_write_order` would read; the
        # open starts -- a handful -- are then read whole, exactly as before.
        marks = self._c.operational_marks(act=(RUN_START, *RUN_ENDS),
                                          execution=execution)
        done = closed_starts(marks, lambda a: a["seq"])
        wanted = [m["id"] for m in marks
                  if m["act"] == RUN_START and m["id"] not in done]
        out = []
        for k in range(0, len(wanted), 500):
            out.extend(self._c.operational(id=tuple(wanted[k:k + 500])))
        if len(wanted) > 500:
            seq = {m["id"]: m["seq"] for m in marks}
            out.sort(key=lambda a: seq[a["id"]])
        return out

    def history(self, **kw) -> list[dict]:
        """Operational history, filtered. Never Conversation chronology.

        Asked for exactly the acts one act caused, it is `_children`'s read
        -- the same answer, settled once per reading -- because that is the
        question the work views ask of every node they show."""
        if set(kw) == {"caused_by"}:
            return self._children(kw["caused_by"])
        return self._c.operational(**kw)

    def observe(self, about_entry, what, *, detail="", attributed_to="mentis",
                written_by=None) -> str:
        """Record something observed. The observed record is not touched."""
        with self._c.atomic():
            oid = self._c.write(kind=OBSERVATION, attributed_to=attributed_to,
                                written_by=written_by,
                                body={"about": about_entry, "what": what,
                                      "detail": detail})
            self._c.write(body={"reason": what}, attributed_to=attributed_to,
                          written_by=written_by,
                          link={"from": oid, "to": about_entry,
                                "relation": OBSERVES})
        return oid

    # -- reading ------------------------------------------------------------

    def _kind_of(self, entry) -> str:
        return (entry.get("definition") or {}).get("name") or "entry"

    def _is_kind(self, entry_id, kind) -> bool:
        """Is this durable reference a node of that Kind? Checked, not assumed.

        A RENAMED PARTICIPANT'S LATER VERSION IS NOT A PARTICIPANT OF ITS OWN:
        it is that Participant's alias, and acting for it would split one
        somebody in two. Every door that asks this before acting for somebody
        refuses it, as a Conversation's version is refused."""
        got = self._c.read([entry_id])
        if not got or not self._is(got[0], kind):
            return False
        if kind == PARTICIPANT and self._c.links(
                relation=self._c.superseding_relation(), frm=entry_id):
            return False
        return True

    def _is(self, entry, kind) -> bool:
        d = entry.get("definition") or {}
        return entry["family"] == "entry" and d.get("name") == kind

    def _linked(self, relation, *, to=None, frm=None) -> list[str]:
        links = self._c.links(relation=relation, to=to, frm=frm)
        return [e["link"]["from"] if to is not None else e["link"]["to"]
                for e in links]

    def all_conversations(self) -> list[dict]:
        """Every Conversation, ONCE, AS IT NOW READS. A renamed one's later
        versions are entries of the Kind too, but they are it and never
        Conversations of their own; it reads under its current name."""
        from .versions import presented
        rows = self._c.entries_of_kind(CONVERSATION)
        if not rows:
            return rows
        sup = self._c.superseding_relation()
        ids = [e["id"] for e in rows]
        later = {x["link"]["from"] for x in self._c.links(relation=sup,
                                                          frm_any=ids)}
        if not later:
            return rows
        renamed = {x["link"]["to"] for x in self._c.links(relation=sup,
                                                          to_any=ids)}
        return [presented(self._c, e) if e["id"] in renamed else e
                for e in rows if e["id"] not in later]

    def all_participants(self) -> list[dict]:
        """Every Participant, ONCE, AS IT NOW READS. A renamed one's later
        versions are entries of the Kind too, but they are it and never
        Participants of their own; it reads under its current alias."""
        from .versions import presented
        rows = self._c.entries_of_kind(PARTICIPANT)
        if not rows:
            return rows
        sup = self._c.superseding_relation()
        ids = [e["id"] for e in rows]
        later = {x["link"]["from"] for x in self._c.links(relation=sup,
                                                          frm_any=ids)}
        if not later:
            return rows
        renamed = {x["link"]["to"] for x in self._c.links(relation=sup,
                                                          to_any=ids)}
        return [presented(self._c, e) if e["id"] in renamed else e
                for e in rows if e["id"] not in later]

    def _addressee_status(self, conversation):
        """Every (contribution, addressee) of a Conversation with its status,
        walked ONCE.

        `awaiting_response` and `failures_in` are two readings of the same
        evidence -- somebody was addressed, and what is known about it -- and
        were two identical loops over it, so asking for both did everything
        twice. Both walk this now. `_turn_view` asks `status_of` about the same
        pairs a third time and reaches the same answers through `reading()`.

        THE EVIDENCE IS READ FOR THIS CONVERSATION'S TURNS, ONCE. Who replied
        and what was observed used to be read for the whole corpus -- every
        `replies-to` and every `observes` link, by a scan of every entry --
        once per (Turn, addressee) outside a `reading()` block, and once per
        read inside one. Either way its cost grew with everything else in the
        Brain, Source Admissions included (R2). See `_answers`.

        AND IT IS NEVER OLDER THAN THE RECORD IT IS USED ON. The walk is a
        generator, so a write can commit between two of its Turns -- another
        request's reply, on the threaded server. Holding one reading of the
        evidence for the whole walk judged every later Turn as if that write
        had not happened, and the stale answer was then kept in the new read
        scope (R2 review, adm-6889d84c0989). So `answers` is asked for at the
        moment each status is judged, and it reads again whenever the corpus's
        write count has moved since it last read: no more reads than before
        while nothing is written, and exactly as fresh as base when something
        is.
        """
        contribs = self.contributions(conversation)
        ids = [c["id"] for c in contribs]
        held = {}

        def answers():
            # `steady`, not `writes`: beside the writer (R1) an answer read
            # while a commit was under way may be the record before it, and
            # must not be held past it. None never matches, so it is re-read.
            now = self._c.steady
            if now is None or held.get("writes") != now:
                # Each Turn's share is kept with it, under the same guard, so
                # `status_of` asked later about an addressee this walk does not
                # cover -- one addressed after the Turn was posted -- reads
                # nothing again.
                held["answers"] = self._recall(
                    ("answers", conversation), lambda: self._answers(ids),
                    also=lambda got: {("answers-of", c): {c: got[c]}
                                      for c in ids})
                held["writes"] = now
            return held["answers"]

        for c in contribs:
            for who in c["body"]["addressed_to"]:
                yield c, who, self._recall(
                    ("status", c["id"], who),
                    lambda: self._status_of(c["id"], who, answers))

    def awaiting_response(self, conversation) -> list[dict]:
        """Contributions addressed to somebody with no reply from them.

        Computed only from evidence that already exists: who was addressed,
        whether a delivery record names them, and whether they replied. It
        never asserts read, seen or understood, and it says plainly when
        something was addressed but never delivered.
        """
        out = []
        for c, who, st in self._addressee_status(conversation):
            if st["responded"] or st["failed"]:
                continue
            out.append({
                "what": "awaiting response",
                "conversation": conversation,
                "contribution": c["id"],
                "participant": who,
                "detail": (f"{self.alias(who)} was addressed and has not "
                           f"replied; delivered={st['delivered']}"),
                # The same fact as a field, so a reader can tally it without
                # parsing the sentence.
                "delivered": st["delivered"],
            })
        return out

    def failures_in(self, conversation) -> list[dict]:
        out = []
        for c, who, st in self._addressee_status(conversation):
            if st["failed"]:
                out.append({
                    "what": "delivery failed",
                    "conversation": conversation,
                    "contribution": c["id"],
                    "participant": who,
                    "detail": f"delivery to {self.alias(who)} was observed to fail",
                })
        return out

    def contributions(self, conversation) -> list[dict]:
        """Each Turn AS IT NOW READS: the root's identity with its current
        version's body, and `revision` / `deleted` beside it where either is
        true. See `versions.presented`; the versions themselves are never
        linked into the Conversation, so they are never Turns of their own."""
        return self._recall(("contributions", conversation),
                            lambda: self._contributions(conversation))

    def _contributions(self, conversation) -> list[dict]:
        from .versions import presented, supersedes_relation
        def turns():
            return [e for e in self._c.read(self._linked(IN_CONVERSATION,
                                                         to=conversation))
                    if self._is(e, CONTRIBUTION)]

        def scoped():
            # WHICH OF THESE TURNS WERE EDITED OR DELETED, asked of these
            # Turns. This read every supersession link in the corpus to
            # answer it for one Conversation; the set it kept was used only
            # for membership tests on these ids, so asking about these ids
            # gives the same answer.
            entries = turns()
            superseded = {x["link"]["to"] for x in self._c.links(
                relation=supersedes_relation(self._c),
                to_any=[e["id"] for e in entries])}
            return [presented(self._c, e) if e["id"] in superseded else e
                    for e in entries]

        def whole():
            superseded = self._recall("superseded_entries", lambda: {
                x["link"]["to"] for x in self._c.links(
                    relation=supersedes_relation(self._c))})
            return [presented(self._c, e) if e["id"] in superseded else e
                    for e in turns()]

        # The scoped read has to know the Turns before it can ask which were
        # superseded, so it reads them FIRST, where the whole-corpus read took
        # them second. Taken only if nothing was written meanwhile, it saw one
        # record throughout; otherwise it is taken again, and then the old
        # order answers (`Corpus.settled`; R2 re-review, adm-6a12b15130e0).
        return self._c.settled(scoped, whole)

    def contribution_tally(self, conversation) -> tuple[int, float | None]:
        """How many Turns this Conversation holds, and when the last one landed.

        THE SAME TWO NUMBERS `len(contributions(...))` and `max(recorded_at)`
        give, without inflating a single Turn body. A summary of twenty
        Conversations was reading every Turn of every one of them -- all of their
        prose -- to produce twenty integers and twenty timestamps.

        It is faithful because `presented` moves neither identity nor time: it
        swaps in the current version's BODY and keeps the root's `recorded_at`
        (see `versions.presented`), and it never adds or drops a row -- a deleted
        Turn is still counted, with its body blanked. So the count and the newest
        time are properties of the root entries alone, which is what this asks
        the store for.
        """
        return self._c.linked_node_tally(IN_CONVERSATION, conversation,
                                         CONTRIBUTION)

    def topic_contribution_count(self, topic) -> int:
        """How many Turns are filed under this Topic now.

        `topic_contributions` reads every one of them; every consumer of this
        number only ever shows the number. The standing filter still decides
        WHICH filings are in force -- that is the meaning of the count and is not
        skipped -- but the Turns behind them are no longer fetched to be counted.

        DISTINCT TURNS, NOT FILINGS. `topic_contributions` ends at `read(ids)`,
        which answers once per id, so counting the link rows instead would say
        two where the reader says one the moment a Turn holds two standing
        filings under one Topic. `assign_topic` refuses to write a second one, so
        only a direct store write produces it -- which is precisely the standard
        under which `linked_node_tally` counts DISTINCT. The first version of
        this line counted rows while its sibling counted things.
        """
        return len({x["link"]["from"]
                    for x in self._links_now(ABOUT_TOPIC, to=topic)})

    def participants(self, conversation) -> list[str]:
        return sorted(set(self._linked(PARTICIPATES_IN, to=conversation)))

    def conversations_of(self, participant) -> list[str]:
        return sorted(set(self._linked(PARTICIPATES_IN, frm=participant)))

    def instructions(self, conversation) -> list[dict]:
        """The `conversation-instruction` material placed here, and only that.

        ITS STATED JUSTIFICATION WAS TWO CALLERS, AND IT HAD ONE. This docstring
        said the Conversation view listed instructions under that heading and
        `governs` reported on them -- but `governs` moved to `placed_procedural`
        in the same change, so the sentence was false from the moment it was
        written, and the one remaining reader was the Conversation view. That
        view has moved too, for the reason this read exists at all: a `rule`
        placed at a Conversation governs it, is delivered to every execution
        there and appears in `governs()`, and the view's instruction list left
        it out -- the owner reading the Conversation could not see the material
        directing the work in it.

        SO THIS IS NOW A NARROW READ WITH NO PRODUCTION CALLER, KEPT AND NOT
        DELETED, because "which material of this one Kind is placed here" is a
        real question a test and a future surface may ask, and it is one line.
        What it must not be is the answer to "what governs here" or "what is
        placed here": those are `governs` and `placed_procedural`, and both ask
        what the Kind DECLARES rather than what it is called.
        """
        return [e for e in self._c.read(self._linked(SCOPED_TO, to=conversation))
                if self._is(e, CONVERSATION_INSTRUCTION)]

    def _knowing(self, kind) -> str | None:
        """What this Kind's CURRENT definition says it is. See `knowing_of`."""
        return knowing_of(self._c, kind)

    def _supplied_as(self, kind) -> str | None:
        """Which ladder material of this Kind comes up, in the record's words,
        or None where the Kind declares neither."""
        return {KNOWING_THAT: "knowledge",
                KNOWING_HOW: "governance"}.get(self._knowing(kind))

    def placed_procedural(self, conversation) -> list[dict]:
        """Material placed at this Conversation WHOSE KIND DIRECTS WORK.

        WHAT MAKES PLACED MATERIAL DELIVERABLE IS WHAT IT IS, NOT WHAT IT IS
        CALLED. This used to be `instructions()`, which asked whether the entry
        was a `conversation-instruction` -- so an owner who placed a `rule` at a
        Conversation, established it, and saw it listed as governing that
        Conversation, watched it reach nobody. Nothing was wrong with the rule:
        the delivery path had one Kind's name written into it, and a Kind's name
        is exactly the thing nothing here is allowed to reason from.

        SO THE CONDITION IS THE DECLARATION. `knowing == "how"` on the Kind's
        current definition, which `rule`, `decision` and
        `conversation-instruction` all declare and which a Kind added tomorrow
        declares by saying so in a list. ABSENT IS NOT "how": material of a Kind
        that declares nothing is placed and stays where it was placed, and this
        channel does not carry it -- being silent about which ladder something
        belongs to is not an invitation to pick one.
        """
        # A PLACEMENT SOMEBODY ENDED IS NOT A PLACEMENT (`end_placement`).
        placed = self._c.read(list(dict.fromkeys(
            x["link"]["from"]
            for x in self._links_now(SCOPED_TO, to=conversation))))
        return [e for e in placed
                if e["family"] == "entry" and e.get("link") is None
                and self._knowing(self._kind_of(e)) == KNOWING_HOW]

    def placed_brain_wide(self) -> list[dict]:
        """Material placed on the WHOLE BRAIN whose Kind directs work.

        The same question `placed_procedural` asks, asked of the whole-Brain
        destination. Empty when nothing was ever placed there -- never every
        piece of material that happens to have no Conversation.
        """
        out = {}
        for where in sorted(whole_brain_ids(self._c)):
            for e in self.placed_procedural(where):
                out.setdefault(e["id"], e)
        return list(out.values())

    def governs(self, conversation) -> dict:
        """What governs work here, and what has merely been proposed for it.

        THE DISTINCTION IS NOT NEW AND IS NOT A WORKFLOW. An entry stands
        when something established it and nothing has superseded it, which
        is what `stands` has always computed. Material that was written and
        not established is a candidate: it is in the record, it is
        addressable, it can be argued with -- and it does not govern
        anything. Composition delivers what stands and says why it withheld
        the rest.

        This is a READ. It decides nothing; it reports what the links
        already say, so that what is in force here can be seen without
        anybody having to know which relations to look for.
        """
        out = {"conversation": conversation, "governing": [],
               "candidates": [], "ended": [], "replaced": []}
        # WHAT IT REPORTS IS WHAT DELIVERY WOULD USE. This read and `compose`
        # must not disagree about what governs here, so both ask the same
        # question -- is this placed, and does its Kind direct how work is done
        # -- rather than one of them naming a Kind. Reporting only
        # `conversation-instruction` while `compose` delivered a placed `rule`
        # would hide governing material from the surface the owner corrects it
        # through, which is the opposite of the defect being fixed.
        #
        # AND WHAT IS PLACED ON THE WHOLE BRAIN, because delivery carries it
        # here too. Each row says which placement brings it -- this
        # Conversation, the whole Brain, or both -- and appears once.
        here = {e["id"]: e for e in self.placed_procedural(conversation)}
        everywhere = {e["id"]: e for e in self.placed_brain_wide()}
        for e in sorted({**everywhere, **here}.values(),
                        key=lambda x: x["recorded_at"]):
            standing = self._c.stands(e["id"])
            row = {"entry": e["id"], "kind": self._kind_of(e),
                   "placed": ([CONVERSATION] if e["id"] in here else [])
                   + ([WHOLE_BRAIN] if e["id"] in everywhere else []),
                   "text": content_of(e, *rendering_of(self._c,
                                                        self._kind_of(e))),
                   "about": e["body"].get("about", ""),
                   "attributed_to": e.get("attributed_to"),
                   "written_by": e.get("written_by"),
                   "at": e.get("recorded_at"),
                   "established_by": standing["established_by"],
                   "superseded_by": standing["superseded_by"],
                   "disputed_by": standing["incoming"].get("disputes", [])}
            # The classification lives in `standing_state`, which the
            # Brain-wide register reads too, so the two cannot disagree.
            out[_GOVERNS_BUCKET[standing_state(standing)]].append(row)
        return out

    def alias(self, participant) -> str:
        """A Participant's alias; any other reference comes back as itself.

        ONLY A PARTICIPANT HAS AN ALIAS. Callers hand this whatever a record
        names -- a Link's `from` is as often a Rule, a Turn or a Topic -- and
        it read `body["alias"]` off every one, so resolving the establishment
        of a Rule failed with KeyError 'alias'. An entry without one is
        answered the way an absent one always was: by its reference."""
        got = self._entry(participant)
        if got and self._is(got[0], PARTICIPANT):
            # ITS CURRENT ALIAS: a renamed Participant is shown by its new one.
            from .versions import presented
            first = got[0]
            got = [self._recall(("participant-now", participant),
                                lambda: presented(self._c, first))]
        alias = ((got[0].get("body") or {}).get("alias") if got else None)
        return alias if isinstance(alias, str) and alias else participant

    # -- status, computed from evidence that already exists -----------------

    @contextmanager
    def reading(self):
        """One answer per question for as long as the record has not moved.

        `status_of` is asked about the same (contribution, addressee) pair up to
        three times in a single HTTP read -- by `awaiting_response`, by
        `failures_in` and again by `_turn_view` -- and each time it re-read and
        re-decoded that participant's ENTIRE delivery history. Profiled on the
        live Brain: 972 calls costing 978 ms of 1282 ms on `/api/brain`, 486
        calls costing 500 ms of 685 ms on `/api/conversations`, with 190,852
        JSON decodes behind the first of those.

        WHAT THIS IS NOT. It is not a cache of anything, and there is no second
        store: NOTHING derived is kept once the block ends.

        A WRITE ENDS IT, wherever the write came from. The first version of this
        relied on the web layer opening a scope for GET only, and that premise
        was not true: `/api/capacity` answers a GET and records the reading it
        took. Nothing broke, because that route asks nothing about status -- but
        an invariant that holds by coincidence is not an invariant. So the scope
        now checks the corpus's in-process write count and throws everything away
        the moment it moves. A read that straddles a write is correct rather than
        merely unlikely, and no list of which routes write has to be maintained.

        It is held on a thread-local on the INSTANCE, so neither two requests in
        flight nor two Conversations over two corpora in one process can see each
        other's answers. Nesting is safe: only the outermost block owns the scope
        and only it clears it. With no block open every call behaves exactly as
        it always did.
        """
        local = self._scope
        mine = getattr(local, "frame", None) is None
        if mine:
            local.frame = {"memo": {}, "writes": self._c.writes}
        try:
            yield
        finally:
            if mine:
                local.frame = None

    def _recall(self, key, compute, *, also=None):
        """`compute()`, once per key, while a `reading()` block is open AND the
        record has not moved. Outside one, straight through -- no state.

        `also(value)` names further answers the same reading settled, kept
        with it under the same terms.

        AN ANSWER COMPUTED WHILE THE RECORD MOVED IS RETURNED, NOT KEPT. If a
        write lands during `compute()`, part of what it read may predate the
        write; keeping it would carry that into the scope the write began,
        where it would outlive the write it never saw.

        NOR ONE BEGUN WHILE A COMMIT WAS UNDER WAY (R1 + R2 combined). Beside
        the writer a read does not wait for the COMMIT, so it may see the
        record before it while `writes` already counts it. Nothing is kept or
        reused then; every call reads. A kept answer was therefore begun and
        finished on the same `steady` number -- one record, the record as it
        then stood (`Corpus.steady`) -- and is reused only while `steady` is
        still that number: no commit has finished since, and none is under
        way, so it is what a read made at the moment of reuse would return.
        The memo can cost freshness nowhere; where it cannot be sure, it
        reads again."""
        frame = getattr(self._scope, "frame", None)
        if frame is None:
            return compute()
        now = self._c.steady
        if now is None:
            frame["memo"].clear()
            frame["writes"] = None
            return compute()
        if now != frame["writes"]:
            # Something was appended since these answers were taken. They are
            # about the record, so they are no longer about this record.
            frame["memo"].clear()
            frame["writes"] = now
        memo = frame["memo"]
        if key in memo:
            return memo[key]
        value = compute()
        if frame["writes"] == now == self._c.steady:
            memo[key] = value
            for k, v in (also(value) if also else {}).items():
                memo.setdefault(k, v)
        return value

    def _settled_already(self, key):
        """What this reading already settled for `key`, or None. It computes
        nothing and keeps nothing -- a question it cannot answer is left for
        the caller to read -- and it answers only on the terms `_recall`
        reuses on: a scope open, and the record not moved since, with no
        commit under way. A stale memo is left for `_recall` to clear."""
        frame = getattr(self._scope, "frame", None)
        if frame is None:
            return None
        now = self._c.steady
        if now is None or now != frame["writes"]:
            return None
        return frame["memo"].get(key)

    def status_of(self, contribution, addressee) -> dict:
        """What can honestly be said about one addressee of one contribution.

        Four separate facts, deliberately not collapsed. There is no `read` and
        no `understood`, because no runtime path establishes either.
        """
        return self._recall(("status", contribution, addressee),
                            lambda: self._status_of(contribution, addressee))

    def _answers(self, contributions) -> dict:
        """Per Turn: who replied to it, and which entries observe it, in
        append order. Two indexed reads for any number of Turns, and nothing
        about any other Turn in the corpus."""
        out = {c: (set(), []) for c in contributions}
        for e in self._c.links(relation=REPLIES_TO, to_any=contributions):
            out[e["link"]["to"]][0].add(e.get("attributed_to"))
        for x in self._c.links(relation=OBSERVES, to_any=contributions):
            out[x["link"]["to"]][1].append(x["link"]["from"])
        return out

    def _status_of(self, contribution, addressee, answers=None) -> dict:
        rec = self._recall(("entry_read", contribution),
                            lambda: self._c.read([contribution])[0])
        addressed = addressee in rec["body"]["addressed_to"]

        def _get_delivered(p):
            s = set()
            for d in self._recall(("deliveries", p),
                                  lambda: self._c.deliveries(participant=p)):
                for m in d.get("material", ()):
                    if "entry" in m:
                        s.add(m["entry"])
            return s

        delivered_set = self._recall(("delivered_set", addressee),
                                     lambda: _get_delivered(addressee))
        delivered = contribution in delivered_set

        # Asked of this Turn alone unless the caller can answer for its
        # Conversation (`_addressee_status`). Both are the same links a
        # corpus-wide read would have kept for this Turn. The caller's answer
        # is asked for HERE, as this Turn is judged, never handed in already
        # read: that is what keeps it as fresh as the record.
        got = answers() if answers is not None else None
        if got is None or contribution not in got:
            got = self._recall(("answers-of", contribution),
                               lambda: self._answers([contribution]))
        replied_by, observers = got[contribution]
        responded = addressee in replied_by

        failed = None
        if observers:
            for e in self._c.read(observers):
                if (self._is(e, OBSERVATION)
                        and e["body"]["what"] == "delivery-failed"
                        and e["body"].get("detail", "").startswith(addressee)):
                    failed = e["id"]

        return {"addressee": addressee, "addressed": addressed,
                "delivered": delivered, "responded": responded,
                "failed": failed}

    # -- orientation, computed, never cached --------------------------------

    def included_references(self, conversation) -> list[dict]:
        """The posts included in this Conversation from others, AS REFERENCES:
        each post's id, its home Conversation's id and current name, its home
        number, and the first line it now says -- oldest inclusion first.

        NOTHING ELSE OF IT. Not its words beyond that line, its parts, its
        replies, its addressees or what it governs; a deleted post says only
        that it was deleted. Whoever reads this reaches the rest, if at all,
        only through what they could already read; this grants nothing."""
        from .versions import flow_text, presented
        out, seen = [], set()
        for x in self.links_here(conversation):
            pid = x["link"]["from"]
            if pid in seen:
                continue
            seen.add(pid)
            got = self._c.read([pid])
            if not got:
                continue
            now = presented(self._c, got[0])
            home = self.conversation_of(pid)
            row = {"id": pid, "home": home,
                   "home_name": self.conversation_name(home),
                   "number": self.turn_number(pid)}
            if now.get("deleted"):
                row.update(first_line=None, deleted=True)
            else:
                row["first_line"] = first_line(
                    flow_text((now.get("body") or {}).get("parts")))
            out.append(row)
        return out

    def orientation(self, conversation, participant, *, recent=4,
                    topic=None) -> dict:
        """Compact. Not the transcript, and not stored anywhere.

        With `topic`, focus narrows to that subject -- and narrowing is not
        isolation. The reply context of focused contributions is included even
        where it lives under another Topic, and the amount of Conversation
        outside the focus is reported rather than hidden.
        """
        # UNDER ITS CURRENT NAME: a renamed Conversation reads as it now does.
        from .versions import presented as _presented
        conv = _presented(self._c, self._c.read([conversation])[0])
        everything = sorted(self.contributions(conversation),
                            key=lambda e: e["recorded_at"])
        contribs = everything
        focus, context = None, []
        if topic is not None:
            if self.conversation_of_topic(topic) != conversation:
                raise ValueError("that topic does not organise this conversation")
            from .versions import presented
            focus = presented(self._c, self._c.read([topic])[0])
            wanted = set(x["link"]["from"]
                         for x in self._links_now(ABOUT_TOPIC, to=topic))
            contribs = [c for c in everything if c["id"] in wanted]
            # what those contributions answer, even outside this Topic
            replied_to = set()
            for c in contribs:
                replied_to.update(self._linked(REPLIES_TO, frm=c["id"]))
            context = [c for c in everything
                       if c["id"] in replied_to and c["id"] not in wanted]
        # Ask only about the contributions this actually concerns. Asking for
        # every reply in the corpus was correct and got slower with the corpus:
        # 0.05ms at 66 entries, 5.4ms at 66,000, for an answer about one
        # Conversation. Measured, not guessed.
        # obligations are a Conversation fact, not a focus fact: narrowing to a
        # Topic must not hide what somebody is still waiting on you for
        mine = [c for c in everything if participant in c["body"]["addressed_to"]]
        unresolved = [c["id"] for c in mine
                      if not self._c.links(relation=REPLIES_TO, to=c["id"])]

        def render(rows):
            return [{"id": c["id"], "by": self.alias(c["attributed_to"]),
                     # SAID AS WHAT IT IS NOW. A deleted Turn is delivered as
                     # deleted, never with its old words; an edited one with
                     # its current words.
                     **({"deleted": True} if c.get("deleted") else {}),
                     **({"edited": True} if c.get("revision") else {}),
                     "parts": [p.get("type") for p in c["body"]["parts"]],
                     "topics": self.topics_of(c["id"], conversation),
                     "said": " ".join(p.get("text", "") for p in c["body"]["parts"]
                                      if p.get("type") == "text")}
                    for c in rows]

        # WHERE THIS CONVERSATION WAS OPENED FROM, if it was opened from an
        # anchor: the exact target and the reason, resolved now from the
        # immutable version and never copied into the record. Lineage, not
        # the parent's transcript -- see `anchors.origin`.
        from .anchors import origin
        opened_from = origin(self, conversation)
        # WHAT OTHER LAYERS ADD, read from the record by them (see
        # `ORIENTATION_ADDITIONS`): interrupted work and what of it is
        # preserved, so an agent oriented here knows a run stopped without
        # ending rather than finding a half-done branch and guessing.
        added = {name: add(self, conversation)
                 for name, add in ORIENTATION_ADDITIONS.items()}
        # THE POSTS INCLUDED HERE FROM OTHER CONVERSATIONS, as references and
        # nothing more: kept apart from `recent`, which is this Conversation's
        # own posts, and absent where nothing is included, so an orientation
        # with no inclusions is exactly what it was.
        included = self.included_references(conversation)
        decisions = self.owner_decisions(conversation)
        return {
            "conversation": conversation,
            "name": conv["body"]["name"],
            "about": conv["body"]["about"],
            **({"origin": opened_from} if opened_from else {}),
            **({"included": included} if included else {}),
            "topic": {"id": topic, "name": focus["body"]["name"]} if focus else None,
            "recent": render(contribs[-recent:]),
            "reply_context": render(context),
            "unresolved_for_you": unresolved,
            "withheld": max(0, len(contribs) - recent),
            "elsewhere_in_conversation": (len(everything) - len(contribs)
                                          if topic is not None else 0),
            **({"decisions": decisions} if any(decisions.values()) else {}),
            **added,
        }

    #: HOW MANY OWNER DECISIONS AN ORIENTATION NAMES, of each kind. One line
    #: each; the rest are counted, and `history`/`resolve` read them.
    ORIENTATION_DECISIONS = 5

    def owner_decisions(self, conversation, most=None) -> dict:
        """The decision questions asked in this Conversation, newest first:
        `answered` (with the owner's choice) and `open` (still owed), each
        `{expectation, post, question, answer?}` -- plus how many of each
        there are. What an orientation names so a run acts on what the owner
        already settled, and does not put a question to them twice.

        TWO READS, NOT ONE PER QUESTION: every `kind="decision"` expectation
        of the Conversation in one statement (`detail_is`), then whatever any
        of them caused in one more (`operational_under`). An answer is the
        `decision-answered` act its asker recorded; a withdrawal is its
        `expectation-met`. Nothing here is a status; it is read now."""
        most = self.ORIENTATION_DECISIONS if most is None else most
        try:
            asked = self._c.operational(conversation=conversation,
                                        act="expectation-recorded",
                                        detail_is={"expects": "decision"},
                                        newest_first=True)
        except Exception:                                # noqa: BLE001
            return {"open": [], "answered": [], "open_count": 0,
                    "answered_count": 0}
        ids = [a["id"] for a in asked]
        answered, closed = {}, set()
        for _seq, a in self._c.operational_under(ids):
            if a["act"] == DECISION_ANSWERED:
                answered.setdefault(a["caused_by"], a)
            elif a["act"] == "expectation-met":
                closed.add(a["caused_by"])
        open_, settled = [], []
        for a in asked:
            d = a.get("detail") or {}
            said = d.get("question") or a.get("because") or ""
            words = first_line(said if isinstance(said, str) else "", 140)
            row = {"expectation": a["id"], "post": a.get("turn"),
                   "question": words or "(no question words)"}
            got = answered.get(a["id"])
            if got:
                gd = got.get("detail") or {}
                # THE OPTION'S LABEL, or -- answered in the owner's own
                # words, which live in their reply -- where to read them.
                label = gd.get("label")
                row["answer"] = (
                    first_line(label, 100) if isinstance(label, str) and label
                    else f"in their own words, reply {gd['reply']}"
                    if gd.get("reply") else "answered")
                settled.append(row)
            elif a["id"] not in closed:
                open_.append(row)
        return {"open": open_[:most], "answered": settled[:most],
                "open_count": len(open_), "answered_count": len(settled)}

    # -- composition --------------------------------------------------------

    def compose(self, *, conversation=None, participant, persona=None,
                material=(), request="", recent=4, topic=None,
                behavioural=(), brain=None, question=None) -> Composition:
        """One seam. Several sources. Every component keeps its origin.

        Nothing is dropped SILENTLY to fit a budget. Where there is a bound --
        the knowledge channel has one, and it is a real budget -- everything it
        excludes is named in `withheld` with the bound stated, because Mark III
        dropped three items without even being able to say which. An honest cut
        is a cut whose remainder is in the answer.

        TWO LADDERS REACH AN EXECUTION HERE, AND THEY ARE CHOSEN BY DIFFERENT
        QUESTIONS. Procedural material is chosen by PLACEMENT -- somebody put it
        here and established it, so it governs work done here. Propositional
        material is chosen by RELEVANCE -- `question` is what is being asked,
        and `knowledge.considered` finds standing material whose words overlap
        it. Neither question can answer the other: a rule is not relevant, it
        applies; a finding does not apply, it may be pertinent. Collapsing them
        into one "context" list is how a record loses the difference between
        something it knows and something that binds.

        `question` ABSENT MEANS NOBODY ASKED, and nothing propositional is
        supplied. It is not a default to be filled in from the recent turns.

        AND THE PROPOSITIONAL LADDER ARRIVES IN TWO TIERS. What stands comes as
        adopted knowledge; what was recorded and not adopted may come as
        relevant experience, labelled so it cannot be read as either, with
        its trailer (`_knowledge_channel`). Governing material is chosen
        exactly as before and gains only its why-this-holds note.
        """
        components, withheld = [], []

        if persona is not None:
            p = self._c.read([persona])[0]
            standing = self._c.stands(persona)
            if not standing["stands"]:
                # WHAT GOVERNS IS WHAT STANDS. Checking only supersession
                # let a candidate through -- material somebody wrote and
                # nobody established -- so anything an agent authored would
                # have governed the next execution merely because it was
                # written down. `stands` is the answer the record already
                # computes: established, and not since superseded.
                withheld.append({"source_kind": PERSONA, "source_id": persona,
                                 "why": ("superseded"
                                          if standing["superseded_by"]
                                          else "not established")})
            else:
                components.append(Component(
                    PERSONA, persona, "invocation:persona",
                    self._said_with_links(p),
                    f"the participant is operating as {p['body']['name']}",
                    p["body"].get("about", ""),
                    self._supplied_as(PERSONA), title=self._title_of(p)))
            # WHAT THE PERSONA CARRIES, RIGHT AFTER IT. Material placed ON the
            # Persona -- its Disciplines, or any procedural material -- reaches
            # an execution operating as that Persona, asked the same two
            # questions every placement is: does its Kind direct work, and
            # does it stand. A Persona that does not stand carries nothing, and
            # each item it would have carried is withheld with that reason,
            # exactly as the named block below withholds.
            carried_scope = f"{PERSONA_CARRIED_PREFIX}{persona}"
            for ins in sorted(self.persona_carried(persona),
                              key=lambda e: e["id"]):
                kind = self._kind_of(ins)
                held = self._c.stands(ins["id"])
                why_not = (None if held["stands"] else
                           "superseded" if held["superseded_by"] else
                           "not established")
                if why_not is None and not standing["stands"]:
                    why_not = ("carried by a Persona that does not stand "
                               "(superseded)" if standing["superseded_by"]
                               else "carried by a Persona that is not "
                                    "established")
                if why_not:
                    withheld.append({"source_kind": kind,
                                     "source_id": ins["id"],
                                     "scope": carried_scope, "why": why_not})
                    continue
                components.append(Component(
                    kind, ins["id"], carried_scope,
                    self._said_with_links(ins),
                    f"carried by the Persona {p['body']['name']} this "
                    f"participant is operating as",
                    ins["body"].get("about", ""),
                    self._supplied_as(kind), title=self._title_of(ins)))

        # durable behavioural material named explicitly for this invocation.
        # Material that should reach every invocation is placed on the whole
        # Brain instead (below); naming is still how one invocation is given
        # something nothing else carries.
        for eid in behavioural:
            got = self._c.read([eid])
            if not got:
                # A REFERENCE THE RECORD DOES NOT HOLD IS AN ANSWER, NOT A
                # CRASH. This indexed straight into the read, so an unknown id
                # raised `list index out of range` out of composition and took
                # the whole dispatch with it -- while the code that named the
                # material claimed this gate withheld with a reason. Found by
                # independent review. No new standing state: nothing is asked
                # of `stands`, because there is no entry to ask about, and the
                # Kind is ABSENT rather than guessed -- an unknown reference
                # has no Kind, and naming one here would invent it.
                withheld.append({"source_kind": None, "source_id": eid,
                                 "why": "not in this record"})
                continue
            item = got[0]
            standing = self._c.stands(eid)
            if not standing["stands"]:
                # THE SAME RULE, ON THE PATH THAT NAMES MATERIAL DIRECTLY.
                # Asking for a candidate by name is still asking for
                # something nobody established, and a caller that can name
                # an id would otherwise have been the one way to deliver
                # material that does not govern.
                withheld.append({"source_kind": self._kind_of(item),
                                 "source_id": eid,
                                 "why": ("superseded"
                                          if standing["superseded_by"]
                                          else "not established")})
                continue
            # NAMED AND ALSO CARRIED BY THE PERSONA: delivered once, under the
            # Persona, saying it was named too.
            carried = next((i for i, c in enumerate(components)
                            if c.source_id == eid), None)
            if carried is not None:
                c = components[carried]
                if "invocation:named" not in c.also:
                    components[carried] = replace(c, also=(*c.also, "invocation:named"))
                continue
            components.append(Component(
                self._kind_of(item), eid, "invocation:named",
                self._said_with_links(item),
                "named explicitly for this invocation",
                item["body"].get("about", ""),
                self._supplied_as(self._kind_of(item)),
                title=self._title_of(item)))

        # WHAT IS PLACED HERE AND DIRECTS WORK -- asked of the Kind's own
        # declaration, never of its name. See `placed_procedural` for why this
        # stopped being `instructions()`: a `rule` an owner placed and
        # established was reported as governing this Conversation and reached
        # nobody, because one Kind's name was written into this loop.
        scoped = self.placed_procedural(conversation) if conversation else []
        for ins in sorted(scoped, key=lambda e: e["id"]):
            kind = self._kind_of(ins)
            standing = self._c.stands(ins["id"])
            if not standing["stands"]:
                # THE REAL KIND IN THE WITHHELD ROW TOO. A reader asking why
                # nothing governs here is owed the name of the material that
                # would have, not the name of the Kind this path used to assume.
                if not any(w.get("source_id") == ins["id"] for w in withheld):
                    withheld.append({
                        "source_kind": kind,
                        "source_id": ins["id"],
                        "why": ("superseded" if standing["superseded_by"]
                                else "not established")})
                continue
            named = next((i for i, c in enumerate(components)
                          if c.source_id == ins["id"]), None)
            if named is not None:
                c = components[named]
                components[named] = replace(c, also=(*c.also, f"conversation:{conversation}"))
                continue
            components.append(Component(
                kind, ins["id"], f"conversation:{conversation}",
                # THE SAME CHOICE THE OWNER'S SURFACES MAKE, so that what
                # governs and what is shown as governing cannot differ.
                self._said_with_links(ins),
                "durable material placed at this conversation",
                ins["body"].get("about", ""),
                self._supplied_as(kind), title=self._title_of(ins)))

        #
        # AND WHAT IS PLACED ON THE WHOLE BRAIN, which reaches every
        # Conversation and Brain-scope work alike. It is asked the same
        # questions -- does its Kind direct work, does it stand -- and the
        # same material is never delivered twice: placed here as well, it is
        # one component under this Conversation's scope that says it is also
        # placed on the whole Brain; named for this invocation as well, the
        # named component says the same.
        everywhere = {e["id"]: e for e in self.placed_brain_wide()}
        for eid, ins in sorted(everywhere.items()):
            kind = self._kind_of(ins)
            standing = self._c.stands(eid)
            if not standing["stands"]:
                if not any(w.get("source_id") == eid for w in withheld):
                    withheld.append({
                        "source_kind": kind, "source_id": eid,
                        "scope": WHOLE_BRAIN_SCOPE,
                        "why": ("superseded" if standing["superseded_by"]
                                else "not established")})
                continue
            existing = next((i for i, c in enumerate(components)
                             if c.source_id == eid), None)
            if existing is not None:
                c = components[existing]
                if WHOLE_BRAIN_SCOPE not in c.also:
                    components[existing] = replace(c, also=(*c.also, WHOLE_BRAIN_SCOPE))
                continue
            components.append(Component(
                kind, eid, WHOLE_BRAIN_SCOPE, self._said_with_links(ins),
                "durable material placed on the whole Brain",
                ins["body"].get("about", ""),
                self._supplied_as(kind), title=self._title_of(ins)))

        for m in material:
            components.append(Component(
                "invocation", None, "invocation",
                m, "supplied for this invocation only"))

        # Topic reaches composition ONLY through orientation. It is not a
        # behavioural placement scope in this slice, and no material is
        # selected or withheld because of it.
        if conversation is not None:
            o = self.orientation(conversation, participant, recent=recent,
                                 topic=topic)
            components.append(Component(
                "orientation", conversation, f"conversation:{conversation}",
                _render_orientation(o), "compact orientation, computed now"))
            if o["withheld"]:
                withheld.append({"source_kind": "contribution",
                                 "source_id": None,
                                 "why": f"{o['withheld']} earlier contributions "
                                        "not included in compact orientation"})
        elif brain is not None:
            bo = brain.orientation(participant=participant, recent=recent)
            components.append(Component(
                "brain-orientation", None, "brain",
                brain.render(bo),
                "compact brain orientation, computed now; names and counts only"))
            withheld.append({
                "source_kind": "conversation", "source_id": None,
                "why": f"{len(bo['conversations'])} conversations are named but "
                       "their contents are not included; ask each one"})

        if request:
            components.append(Component("request", None, "invocation", request,
                                        "what is being asked now"))

        # ---- the knowledge channel ----------------------------------------
        # LAST, AND AFTER THE REQUEST, because it is the only material here
        # that was chosen BY the question rather than placed regardless of it,
        # and a reader meets what is being asked before what may bear on it.
        #
        # AND THE CUT THIS PATH MAKES IS SAID OUT LOUD. The claim that nothing
        # is withheld here used to stand in this comment, and it was false: the
        # read was called with a budget of five, so a question overlapping nine
        # standing lessons delivered five and `withheld` was EMPTY. Four items
        # this Brain carries forward, considered and found relevant, left no
        # trace anywhere -- which is precisely the Mark III failure the
        # docstring above names ("dropped three items without even being able
        # to say which"), reproduced by the fix for it.
        #
        # THE BOUND STAYS. It is a real budget and removing it would put a
        # question's whole overlap in front of an execution. What changes is
        # that `considered` returns EVERYTHING it considered and this loop owns
        # the cut, so every excluded row is named in `withheld` with the real
        # reason and the bound stated, in the same row shape every other
        # withheld row uses.
        #
        # TWO TIERS NOW, EACH WITH ITS OWN BOUND (owner decision 4). Adopted
        # knowledge -- what stands -- and Relevant experience -- what was
        # recorded and not adopted, under `ladder.experience_refusal`'s
        # conditions. Separate bounds so that a question overlapping forty
        # recorded findings can never push the Brain's adopted position out of
        # a delivery, and every row either bound cuts is named with its tier
        # and rank.
        if question:
            got, cut = self._knowledge_channel(question, conversation)
            components.extend(got)
            withheld.extend(cut)

        # GOVERNING MATERIAL CARRIES WHY IT HOLDS AND WHAT IS CHALLENGED. Its
        # tier and its note are added here, once, for every component that
        # governs -- however it arrived -- by the same predicate the rest of
        # delivery uses (`Composition.governing`), never by where it was built.
        from .ladder import GOVERNING, why_this_holds
        governing = set(Composition(tuple(components), (), ()).governing())
        components = [replace(c, tier=GOVERNING,
                              trailer=why_this_holds(self._c, c.source_id))
                      if c in governing else c for c in components]

        return Composition(tuple(components), _conflicts(components),
                           tuple(withheld))

    def _knowledge_channel(self, question, conversation) -> tuple[list, list]:
        """The components the question brings, and what it brought and cut.

        ADOPTED FIRST, THEN EXPERIENCE, each ranked by the same overlap and
        each cut at its own bound. A matched entry brings its neighbourhood
        into the experience tier right behind it -- what was concluded from it
        and how each of those went when tried -- and those count inside the
        experience bound, because they are delivered material like any other.

        WHAT IS KEPT OUT IS NAMED, NOT DROPPED. A recorded entry that matched
        and may not reach this run -- the words of an act, superseded, deleted
        -- is in `withheld` with that reason. Recall is Brain-wide (owner
        decision 3), so the Conversation it was recorded in is said in its
        trailer rather than used to exclude it; `conversation` is unused here.
        """
        from . import ladder
        from .knowledge import considered, recorded_matching
        a_bound, bound = ladder.ADOPTED_BOUND, ladder.EXPERIENCE_BOUND
        components, withheld = [], []

        def cut(row, tier, rank, bound, why_bound):
            withheld.append({
                "source_kind": row["kind"], "source_id": row["entry"],
                "tier": tier, "rank": rank,
                "why": f"relevant to the question on "
                       f"{'+'.join(row['answered'])}, and beyond the bound "
                       f"for it: {why_bound} {bound} most relevant and this "
                       f"ranked {rank}"})

        adopted = considered(self._c, question)
        for rank, row in enumerate(adopted, start=1):
            if rank > a_bound:
                cut(row, ladder.ADOPTED_TIER, rank, a_bound,
                    "adopted knowledge carries the")
                continue
            components.append(Component(
                row["kind"], row["entry"],
                # THE SCOPE SAYS WHY IT WAS SUPPLIED. Every other scope
                # here names WHERE material was placed, because placement
                # is why placed material is deliverable. This material was
                # placed nowhere; the reason it is here is the overlap, so
                # the overlap is the scope and the delivery record keeps it.
                "question:" + "+".join(row["answered"]),
                row["text"],
                # NOT PHRASED AS AN INSTRUCTION, and that is the whole care
                # taken here. A `finding` rendered beside a `rule` must not
                # acquire the force of one from the sentence introducing it,
                # so this says what the material IS and asks for nothing.
                "answers the question asked",
                "",
                self._supplied_as(row["kind"]),
                tier=ladder.ADOPTED_TIER,
                trailer=ladder.trailer(self._c, self, row["entry"])))

        # ---- Relevant experience ----
        delivered_ids = {r["entry"] for r in adopted}
        seen, ranked = set(delivered_ids), []

        def eligible(eid, kind):
            return ladder.experience_refusal(self._c, self, eid, kind)

        for row in recorded_matching(self._c, question):
            if row["entry"] in seen:
                continue
            seen.add(row["entry"])
            why_not = eligible(row["entry"], row["kind"])
            if why_not:
                withheld.append({"source_kind": row["kind"],
                                 "source_id": row["entry"],
                                 "tier": ladder.EXPERIENCE,
                                 "why": f"relevant to the question on "
                                        f"{'+'.join(row['answered'])}, and "
                                        f"not delivered as experience: "
                                        f"{why_not}"})
                continue
            scope = "question:" + "+".join(row["answered"])
            ranked.append((row["entry"], row["kind"], row["text"], scope,
                           ladder.EXPERIENCE_SAYS, row))
        # THE NEIGHBOURHOOD of every matched item on either tier, right
        # behind it: a matched problem, then what was concluded from it, then
        # how each of those went. Neighbours of ADOPTED matches have no
        # experience row to follow, so they lead the tier, in adopted order.
        def neighbours_of(parent, scope):
            out = []
            for eid, rel, via in ladder.neighbourhood(self._c, parent):
                if eid in seen:
                    continue
                got = self._c.read([eid])
                if not got:
                    continue
                kind = self._kind_of(got[0])
                if not ladder.propositional(self._c, kind):
                    continue
                text = (got[0].get("body") or {}).get("text") or ""
                if not isinstance(text, str) or not text.strip():
                    continue
                seen.add(eid)
                if self._c.stands(eid)["stands"]:
                    continue
                why_not = eligible(eid, kind)
                if why_not:
                    withheld.append({"source_kind": kind, "source_id": eid,
                                     "tier": ladder.EXPERIENCE,
                                     "why": f"{rel} {via}, which the "
                                            f"question reached, and not "
                                            f"delivered as experience: "
                                            f"{why_not}"})
                    continue
                said = ("concluded from " if rel == ladder.DERIVED_FROM
                        else "an outcome of ") + via
                out.append((eid, kind, text, scope,
                            f"{said}, which the question reached; "
                            + ladder.EXPERIENCE_SAYS, None))
            return out

        with_neighbours = []
        for r in adopted[:a_bound]:
            with_neighbours += neighbours_of(
                r["entry"], "question:" + "+".join(r["answered"]))
        for x in ranked:
            with_neighbours.append(x)
            with_neighbours += neighbours_of(x[0], x[3])

        says = "relevant experience carries the"
        for rank, (eid, kind, text, scope, why, row) in enumerate(
                with_neighbours, start=1):
            if rank > bound:
                cut({"kind": kind, "entry": eid,
                     "answered": scope.split(":", 1)[1].split("+")},
                    ladder.EXPERIENCE, rank, bound, says)
                continue
            components.append(Component(
                kind, eid, scope, text, why, "",
                self._supplied_as(kind), tier=ladder.EXPERIENCE,
                trailer=ladder.trailer(self._c, self, eid)))
        return components, withheld

    # -- executions, machine-local ------------------------------------------

    def begin_execution(self, *, participant, conversation=None, persona=None,
                        material=(), runtime=None, for_expectation=None
                        ) -> Execution:
        """Start a live execution. This NEVER creates a durable Participant.

        `conversation` is optional. A Participant may be invoked at Brain scope
        without one, and no fake Conversation is created to stand in for it.

        `for_expectation` names the request this execution is carrying, where
        the caller knows it. It is what lets one carrier hold several live
        executions in one Conversation without any of them being mistaken for
        the others -- see `expectation_state`. Absent it stays absent: an
        execution nobody tied to a request is reported as exactly that.
        """
        # ONE reference for one execution. These used to be two -- the handle
        # minted its own id and the delivery boundary minted another -- so
        # `verify_use(execution.reference, ...)` could never match the delivery
        # records that execution had actually produced. Found by the
        # coordination experiment asking exactly that question.
        boundary = self._c.execution(conversation=conversation)
        ex = Execution(boundary.reference, participant, conversation, persona,
                       tuple(material), runtime=runtime,
                       for_expectation=for_expectation)
        ex.boundary = boundary
        self._executions[ex.reference] = ex
        return ex

    def end_execution(self, reference):
        ex = self._executions[reference]
        ex.ended = True
        ex.material = ()          # invocation material does not outlive it
        return ex

    def active_executions(self, *, conversation=None) -> list[Execution]:
        return [e for e in self._executions.values()
                if not e.ended
                and (conversation is None or e.conversation == conversation)]

    def record_delivery(self, execution, composition, *, mechanism,
                        entry_ids=(), operation_ok=True) -> str:
        """Delivery evidence: what crossed, to whom, by what means, from where.

        One record. Says nothing about reading, understanding or acting, and
        carries no field in which that could be written.
        """
        return execution.boundary.deliver(
            list(entry_ids), mechanism=mechanism, rendered="composed",
            participant=execution.participant, runtime=execution.runtime,
            behavioural_sources=composition.sources(),
            operation_ok=operation_ok)


#: WHAT ANOTHER LAYER ADDS TO A CONVERSATION'S ORIENTATION: name -> a
#: function of (Conversations, conversation) returning what it reads from the
#: record. Registered by that layer when it is imported, so this one reaches
#: no further inward than the spine (`mentis.wakecheck` adds
#: `interrupted_work`, which `_render_orientation` says).
ORIENTATION_ADDITIONS: dict = {}


#: HOW MUCH OF A POST AN ORIENTATION SAYS: its first line, cut here. The
#: orientation is a NAVIGATION BRIEF (owner, 2026-10-27: "a short,
#: task-specific navigation brief with references to relevant Turns and
#: requirements. Retrieve detailed context when needed rather than injecting
#: large histories"). It used to paste every recent post whole, and one
#: dispatch measured ~64,000 characters around a 331-character request.
ORIENTATION_LINE = 120

#: HOW A RUN READS WHAT THE BRIEF ONLY NAMES. The read tools every execution
#: holds (`worker.READS`); said once, under the references.
_REFERENCE = re.compile(r"\b(?:ent|opr|adm)-[0-9a-f]{12}\b")

ORIENTATION_FETCH = (
    "These are references, not content: read a post or entry in full with "
    "resolve <id>, earlier posts and acts with history "
    "conversation=<id>, and search what was said (the owner's requirements "
    "and decisions included) with find.")


def _render_orientation(o: dict) -> str:
    cid = o.get("conversation")
    lines = [f"Conversation: {o['name']}" + (f" ({cid})" if cid else "")]
    if o["about"]:
        lines.append(first_line(o["about"], 300))
    if o.get("origin"):
        from .anchors import origin_lines
        lines.extend(origin_lines(o["origin"]))
    if o.get("topic"):
        lines.append(f"Focused on topic: {o['topic']['name']}")

    def say(r):
        # A RECORD IS RENDERED AS IT IS: a part type that is not a string
        # (an older record, or another Brain's) is said as such rather than
        # ending the orientation -- and with it the dispatch -- in a TypeError.
        # ONE LINE PER POST, WITH ITS ID: the reference and the first thing
        # it says, never its whole body (`ORIENTATION_LINE`).
        kinds = ",".join(t if isinstance(t, str) else "untyped"
                         for t in r["parts"])
        said = first_line(r["said"], ORIENTATION_LINE)
        ref = f"{r['id']} " if r.get("id") else ""
        return f"  {ref}{r['by']}: {said or '(' + kinds + ')'}"

    if o.get("recent") or o.get("reply_context"):
        lines.append("Recent posts (oldest first):")
    for r in o.get("reply_context", []):
        lines.append(say(r) + "   [answered from another topic]")
    for r in o["recent"]:
        lines.append(say(r))
    if o.get("withheld"):
        lines.append(f"  {o['withheld']} earlier posts not shown")
    if o.get("elsewhere_in_conversation"):
        # focus is not isolation: say what is outside it rather than imply
        # that nothing is
        lines.append(f"  {o['elsewhere_in_conversation']} further contributions "
                     "in this conversation, under other topics or none")
    if o.get("included"):
        # REFERENCES, NOT CONTENT: where each included post lives and the
        # first line it says, kept apart from this Conversation's own posts.
        lines.append("Included here from other conversations (references, "
                     "not their content):")
        for r in o["included"]:
            lines.append(f"  {r['id']}: #{r['number']} in "
                         f"“{r['home_name']}” ({r['home']}): "
                         + ("(deleted)" if r.get("deleted")
                            else r["first_line"] or "(no text)"))
    if o["unresolved_for_you"]:
        waiting = o["unresolved_for_you"]
        lines.append(f"  awaiting you: {len(waiting)}"
                     + (f" (newest: {', '.join(waiting[-3:][::-1])})"
                        if waiting else ""))
    d = o.get("decisions") or {}
    if d.get("answered"):
        # WHAT THE OWNER ALREADY SETTLED HERE, so a run acts on it rather
        # than putting the same question to them again.
        lines.append(f"Owner decisions already answered here "
                     f"({d['answered_count']}, newest first; they bind this "
                     f"work):")
        for r in d["answered"]:
            lines.append(f"  {r['expectation']}: {r['question']} -> "
                         f"{r['answer']}")
    if d.get("open"):
        lines.append(f"Owner decisions still open here ({d['open_count']}, "
                     f"newest first; already asked, do not ask them again):")
        for r in d["open"]:
            lines.append(f"  {r['expectation']}: {r['question']}")
    for w in (o.get("interrupted_work") or [])[:5]:
        kept = w["preserved"]
        held = ([f"{len(kept['artifacts'])} returned artifact(s)"]
                if kept["artifacts"] else [])
        if kept["branch"]:
            held.append(f"branch {kept['branch']['branch']} at "
                        f"{kept['branch']['path']}")
        if w.get("state") == "ended-unseen":
            held.append("its runtime's final message, recoverable as the "
                        "run's result")
        review = w.get("review")
        lines.append(
            f"  {w.get('state') or 'interrupted'}: {w['carrier']}'s run "
            f"{w['run']} of request {w['request']} stopped without Mentis "
            f"seeing it end ({w['because']}); it is still owed and nothing "
            f"restarts it by itself. Preserved: "
            f"{', '.join(held) or 'nothing Mentis holds'}"
            + (f". Owner asked to keep/resume/discard ({review['decision']}, "
               + (f"answered: {review['answer']!r}" if review.get("answer")
                  else "answered" if review["answered"] else "unanswered")
               + ")" if review else ""))
    # SAID ONLY WHERE SOMETHING IS REFERENCED: a brief naming no post,
    # decision or run has nothing to fetch.
    if any(_REFERENCE.search(line) for line in lines[1:]):
        lines.append(ORIENTATION_FETCH)
    return "\n".join(lines)


def _conflicts(components) -> tuple[Conflict, ...]:
    """Two components speaking to the same declared subject, differently.

    Deterministic, and it decides nothing. Both stay in the composition.

    THE SUBJECT IS COMPARED AS PEOPLE TYPE IT, NOT BYTE FOR BYTE. `Evidence`
    and ` evidence ` are one subject written twice, and an exact comparison
    told nobody that a rule and an instruction about it disagreed. Surrounding
    space is dropped and case is folded for the COMPARISON only; the subject a
    conflict reports is the first component's own wording, trimmed. A subject
    that is only whitespace names nothing and compares with nothing.
    """
    by_subject: dict[str, list[Component]] = {}
    said: dict[str, str] = {}
    for c in components:
        subject = (c.about or "").strip()
        if subject:
            key = subject.casefold()
            said.setdefault(key, subject)
            by_subject.setdefault(key, []).append(c)
    out = []
    for key, group in sorted(by_subject.items()):
        if len({c.text for c in group}) > 1:
            out.append(Conflict(said[key], tuple(group)))
    return tuple(out)


def provisional_name(at=None) -> str:
    """The name a Conversation opened without one stands under until somebody
    names it: "Unnamed" and when, as an ISO date and time (UTC)."""
    import datetime as _dt
    at = at or _dt.datetime.now(_dt.timezone.utc)
    return "Unnamed " + at.strftime("%Y-%m-%dT%H:%M:%SZ")


def first_line(text, most=160) -> str:
    """The first line of what somebody wrote that says anything, cut at
    `most` characters: what a reference shows of a post, and no more."""
    for line in (text or "").splitlines():
        line = line.strip()
        if line:
            return line if len(line) <= most else line[:most - 1] + "…"
    return ""


def _alias_key(alias) -> str:
    """Two aliases are the same name when they differ only in case or the
    leading `@`."""
    return str(alias or "").strip().lstrip("@").casefold()


def open_conversations(corpus) -> Conversations:
    return Conversations(corpus)
