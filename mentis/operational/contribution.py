"""`contribute`: an independent agent's attributed contribution, kept for the owner.

WS-I of `docs/modernization/CONTRACT.md`. THE INCIDENT THIS EXISTS FOR
(2026-11-10): an owner-authorized CLI cleanup session found a real defect and
could not record it -- `record_discovered_work` refused, because the session
carried no request, and nothing else a session holds said "here is something
the owner should see". `contribute` is that: any hand-started session may call
it, with no request and no `coordinate`.

WHAT IT WRITES, AND ALL IT WRITES:
  * a Turn in the owner's **Contributions** Conversation (created once per
    Brain, the first time anybody contributes), attributed to the session's
    Participant, saying the kind, the text, the evidence, what it regards and
    who authorized it;
  * a `contribution-recorded` act on that Turn, with the same as data;
  * for a `finding` or `problem`, the ladder material of that Kind
    (`ladder_writes.record`), resting on the Turn and on whatever evidence is a
    held reference -- `stands: False`, as everything recorded is;
  * for `proposed-work`, an expectation of a result that is UNASSIGNED
    (`of=None`), ADDRESSED TO THE OWNER (the Turn is addressed to them and the
    expectation says so) and caused by nothing, so it is its own piece of work
    in Work Overview, carried by nobody.

WHAT IT NEVER DOES: dispatch anybody, assign anybody, establish anything, or
confer standing. Owner adoption stays the only path to standing, and the owner
choosing to carry proposed work is the only way it starts.
"""

from __future__ import annotations

from typing import Any

#: What may be contributed.
KINDS = ("finding", "problem", "observation", "proposed-work")

#: The ladder Kind each contribution kind is also recorded as. An observation
#: is the Turn alone: no seeded Kind is "something somebody observed" that a
#: session should write (`note` is explicitly not an observation, and
#: `source-material` is a connector's).
MATERIAL = {"finding": "finding", "problem": "problem"}

#: The Conversation every contribution goes to.
CONVERSATION_NAME = "Contributions"
CONVERSATION_ABOUT = ("Contributions from independently launched agents: "
                      "findings, problems, observations and proposed work, "
                      "attributed and not standing. Nothing here is "
                      "established or dispatched; the owner adopts or carries "
                      "what they choose.")
_ONCE = "contributions-conversation"
_ONCE_REQUEST = {"route": "contributions", "name": CONVERSATION_NAME}

MAX_EVIDENCE = 30
MAX_REGARDING = 20

_WORDS = {"finding": "Finding", "problem": "Problem",
          "observation": "Observation", "proposed-work": "Proposed work"}
_SOURCE_WORDS = {"owner-in-chat": "the owner, in the chat that started this "
                                  "session",
                 "request": "a recorded request", "none": "nobody"}


def contributions_conversation(cv, *, actor: str, written_by: str | None) -> str:
    """The Brain's Contributions Conversation, opened the first time it is needed.

    ONCE PER BRAIN, by the record's own operation key across actors
    (`anchors.prior_outcome(across_actors=True)`), asked and written inside the
    caller's transaction so two first contributions cannot open two."""
    from mentis.conversation import anchors
    from mentis.conversation.owner import _owner
    corpus = cv.corpus
    with corpus.atomic():
        prior = anchors.prior_outcome(cv, actor, _ONCE, _ONCE_REQUEST,
                                      across_actors=True)
        if prior is not None and cv._is_kind(prior.get("conversation") or "",
                                             "conversation"):
            return prior["conversation"]
        cid = cv.open_conversation(CONVERSATION_NAME, about=CONVERSATION_ABOUT,
                                   attributed_to=actor, written_by=written_by)
        owner = _owner(cv)
        if owner:
            cv.join(owner, cid, attributed_to=actor, written_by=written_by)
        anchors.record_outcome(cv, actor, _ONCE, _ONCE_REQUEST,
                               {"conversation": cid}, conversation=cid)
        cv.record_act(actor=actor, act="conversation-opened", conversation=cid,
                      about=[], detail={"contributions": True})
        return cid


def _strings(value, what: str, limit: int) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, (list, tuple)) or not all(
            isinstance(v, str) for v in value):
        raise ValueError(f"{what} is a list of strings")
    out = [v.strip() for v in value if v.strip()]
    if len(out) > limit:
        raise ValueError(f"{what} names at most {limit}")
    return list(dict.fromkeys(out))


def _held_basis(corpus, evidence: list[str]) -> list[str]:
    """The evidence that is a reference the record holds, usable as basis."""
    from mentis.conversation import ladder_writes
    out = []
    for ref in evidence:
        try:
            ladder_writes.basis_reference(corpus, ref)
        except (ValueError, LookupError, KeyError, TypeError):
            continue
        out.append(ref)
    return out


def _link_regarding(cv, record_id: str, ids: list[str], actor: str) -> list:
    """WS-C's neutral `regards` links from this record to each id.

    TODO(WS-C integration): `mentis.operational.completion.link_regarding` is
    added by the mod-completion workstream. Where it exists it writes the
    links; until then the ids are kept in the contribution's `detail.regarding`
    (always written, below) and nothing else is linked. The integrator wires
    nothing more than this import."""
    try:
        from mentis.operational.completion import link_regarding
    except ImportError:
        return []
    return list(link_regarding(cv, record_id, ids, actor) or ())


def contribute(cv, args: dict, *, actor: str, execution: str | None,
               runtime: str | None, written_by: str | None,
               caused_by: str | None = None,
               authorized_by: dict | None = None,
               persona: str | None = None) -> dict[str, Any]:
    """Record one contribution. Raises `ValueError` saying what is wrong."""
    from mentis.conversation import ladder_writes
    from mentis.conversation import text as text_part
    from mentis.conversation.owner import _owner
    corpus = cv.corpus
    kind = str(args.get("kind") or "").strip()
    if kind not in KINDS:
        raise ValueError(f"kind is one of {', '.join(KINDS)}")
    text = str(args.get("text") or "").strip()
    if not text:
        raise ValueError("a contribution needs its text: what was found, "
                         "what is wrong, what was seen or what work is proposed")
    evidence = _strings(args.get("evidence"), "evidence", MAX_EVIDENCE)
    regarding = _strings(args.get("regarding"), "regarding", MAX_REGARDING)
    for ref in regarding:
        if not (cv._act(ref) or corpus.read([ref])):
            raise ValueError(f"regarding names {ref!r}, which this record "
                             f"does not hold")
    alias = cv.alias(actor)
    lines = [f"**{_WORDS[kind]}** — contributed by {alias}", text]
    if evidence:
        lines.append("Evidence:\n" + "\n".join(f"- {e}" for e in evidence))
    if regarding:
        lines.append("Regarding: " + ", ".join(regarding))
    if authorized_by:
        said = _SOURCE_WORDS.get(authorized_by.get("source"), "unstated")
        if authorized_by.get("request"):
            said += f" ({authorized_by['request']})"
        if authorized_by.get("note"):
            said += f": {authorized_by['note']}"
        lines.append(f"Authorized by {said}; executed by {alias}.")
    lines.append("Not established and not dispatched: the owner adopts or "
                 "carries what they choose.")
    owner = _owner(cv)
    with corpus.atomic():
        cid = contributions_conversation(cv, actor=actor, written_by=written_by)
        if actor not in cv.participants(cid):
            cv.join(actor, cid, attributed_to=actor, written_by=written_by)
        addressed = (owner,) if kind == "proposed-work" and owner else ()
        turn = cv.say(cid, actor, [text_part("\n\n".join(lines))],
                      addressed_to=addressed, written_by=written_by)
        material = None
        if kind in MATERIAL:
            basis = list(dict.fromkeys([turn] + _held_basis(corpus, evidence)))
            material = ladder_writes.record(
                cv, kind=MATERIAL[kind], body={"text": text}, basis=basis,
                by=actor, writer=written_by,
                context={"conversation": cid, "turn": turn,
                         "execution": execution, "runtime": runtime,
                         "caused_by": caused_by},
                persona=persona)
        proposed = None
        if kind == "proposed-work":
            proposed = cv.expect(
                turn, of=None, kind="result", by=actor, because=text,
                caused_by=None,
                detail={"expects": "result", "proposed_work": True,
                        "contribution": True, "addressed_to": owner,
                        "proposed_by": actor,
                        **({"evidence": evidence} if evidence else {}),
                        **({"regarding": regarding} if regarding else {})})
        about = [turn] + ([material["entry"]] if material else []) + (
            [proposed] if proposed else [])
        act = cv.record_act(
            actor=actor, act="contribution-recorded", conversation=cid,
            turn=turn, execution=execution, runtime=runtime,
            caused_by=caused_by, about=about,
            because=f"{kind} contributed by a hand-started session",
            detail={"kind": kind, "evidence": evidence,
                    "regarding": regarding, "stands": False,
                    "material": material["entry"] if material else None,
                    "proposed": proposed, "addressed_to":
                        owner if kind == "proposed-work" else None,
                    **({"authorized_by": authorized_by}
                       if authorized_by else {})})
        linked = _link_regarding(cv, act, regarding, actor) if regarding else []
    out = {"ok": True, "kind": kind, "conversation": cid, "turn": turn,
           "recorded": act, "stands": False, "dispatched": False,
           "material": material["entry"] if material else None,
           "regarding": regarding, "regards_links": linked,
           "note": ("kept as an attributed contribution in Contributions; it "
                    "does not stand and nothing was dispatched. Only the "
                    "owner adopts or carries it")}
    if proposed:
        out.update(expectation=proposed, assigned=None,
                   addressed_to=owner,
                   note=("kept as proposed work: owed, carried by nobody, and "
                         "addressed to the owner, who decides whether anybody "
                         "takes it on. Nothing was dispatched"))
    return out
