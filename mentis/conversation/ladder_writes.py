"""The ladder's writes, shared by worker and owner surfaces.

Recording confers no authority. Requests and objections use established notes,
as disputes already do, but never establish the material they concern. Every
multi-append operation joins one transaction, including the ask it opens.
"""
from __future__ import annotations

import re

from mentis.conversation import (CONTRIBUTION, CONVERSATION, PRODUCED,
                                 body_refusal, knowing_of, placements_now)
from mentis.conversation.versions import inert_refusal


def held(corpus, ref):
    got = corpus.read([ref]) if isinstance(ref, str) else []
    if not got:
        raise ValueError(f"the record holds no such reference: {ref!r}")
    refusal = inert_refusal(corpus, ref)
    if refusal:
        raise ValueError(refusal["error"])
    return got[0]


def reason(because):
    if not isinstance(because, str) or not because.strip():
        raise ValueError("say why in `because`; a blank reason records nothing")
    return because.strip()


def definition(corpus, entry):
    kind = (entry.get("definition") or {}).get("name")
    current = corpus.current_definition(kind) if kind else None
    return (current or {}).get("body") or {}


def adoptable(corpus, entry):
    """Only Kinds declaring `standing_apt: true` are adoptable (owner decision
    2): findings, outcomes, problems, solutions and notes stay evidence."""
    d = definition(corpus, entry)
    return d.get("knowing") in ("that", "how") and d.get("standing_apt") is True


NOT_ADOPTABLE = ("this Kind does not declare standing_apt true, so its material "
                 "stays evidence and is not adoptable; to adopt what it says, "
                 "record a lesson from it")


def cycle_refusal(corpus, source, target):
    """A citation may not eventually cite itself, through either basis relation."""
    seen, todo = set(), [target]
    while todo:
        item = todo.pop()
        if item == source:
            raise ValueError("this basis would close a derived-from/extracted-from cycle")
        if item in seen:
            continue
        seen.add(item)
        for rel in ("derived-from", "extracted-from"):
            todo.extend(e["link"]["to"] for e in corpus.links(relation=rel, frm=item))


def basis_reference(corpus, ref):
    if not isinstance(ref, str):
        raise ValueError("each basis must be a held reference")
    match = re.fullmatch(r"(adm-[0-9a-f]{12})(?:@([0-9a-f]{12,64})\[(\d+):(\d+)\])?", ref)
    base = match[1] if match else ref
    entry = held(corpus, base)
    if match:
        from mentis.artifacts import describe
        artifact = describe(corpus, base)
        if artifact.get("state") != "held":
            raise ValueError(f"basis artifact {base!r} is not held")
        if match[2]:
            if not artifact["digest"].startswith(match[2]):
                raise ValueError("the citation digest does not match the held artifact")
            start, end = int(match[3]), int(match[4])
            size = len(artifact["_bytes"])
            if not 0 <= start < end <= size:
                raise ValueError("the citation byte range lies outside the held artifact")
    relation = ("extracted-from" if match or
                (entry.get("definition") or {}).get("name") == CONTRIBUTION
                else "derived-from")
    return base, relation, ref if match and match[2] else None


def edge(corpus, source, target, relation, *, by, writer=None, body=None):
    if relation in ("derived-from", "extracted-from"):
        cycle_refusal(corpus, source, target)
    return corpus.write(body=body or {}, attributed_to=by, written_by=writer,
                        link={"from": source, "to": target, "relation": relation})


BASIS = ("derived-from", "extracted-from")
CONTEXT = ("outcome-of", "in-context")


def _declares(corpus, kind):
    return ((corpus.current_definition(kind) or {}).get("body") or {}) if kind else {}


def contextual(corpus, kind):
    """The current fields declare contextual results, so peer Kinds get the
    same check without an interpreter maintaining a list of Kind names."""
    return {"result", "attempted"}.issubset(_declares(corpus, kind).get("fields") or ())


def basis_refs(corpus, kind, basis, *, inherited=()):
    """The basis a new entry of `kind` is written with, checked, as
    (ref, relation, cite) -- or a refusal.

    OWNER DECISION 1, READ FROM ITS OWN DECLARATION, AT EVERY DOOR. Recording,
    the generic authoring door, a proposed replacement, a revision and an edit
    all write a new entry; a `requires_basis` Kind gets none of them without
    saying what it rests on. `requires_basis` and nothing else: `capturable`
    stays a description, and absent is not true. A new VERSION given no basis
    of its own rests on what the version it replaces rested on (`inherited`):
    rewording a lesson does not change its evidence.
    """
    basis = [] if basis is None else basis
    if not isinstance(basis, (list, tuple)) or not all(isinstance(ref, str) for ref in basis):
        raise ValueError("basis must be a list of references")
    refs = [basis_reference(corpus, ref) for ref in dict.fromkeys(basis)] or list(inherited)
    if _declares(corpus, kind).get("requires_basis") is True and not refs:
        raise ValueError(f"{kind!r} declares requires_basis: recording one needs "
                         "at least one basis reference -- what it was concluded "
                         "or drawn from (an outcome, a Turn, an entry or an "
                         "artifact cite) -- given as `basis`, a list of held "
                         "references")
    return refs


def outcome_refs(corpus, kind, body, outcome_of, in_context):
    """An outcome's grounds -- what was tried, and where -- checked, as
    (relation, ref) pairs; a refusal when a contextual Kind lacks either."""
    if contextual(corpus, kind):
        if not outcome_of or not in_context:
            raise ValueError("an outcome needs both outcome_of and in_context: "
                             "what was tried (an `outcome-of` link to a held "
                             "entry) and where (an `in-context` link to a held "
                             "Turn or Conversation)")
        if not body.get("result") or not isinstance(body.get("attempted"), bool):
            raise ValueError("an outcome needs result and a boolean attempted")
    if outcome_of:
        held(corpus, outcome_of)
    if in_context:
        e = held(corpus, in_context)
        if (e.get("definition") or {}).get("name") not in (CONTRIBUTION, CONVERSATION):
            raise ValueError("in_context must name a held Turn or Conversation")
    return [(rel, ref) for rel, ref in (("outcome-of", outcome_of),
                                        ("in-context", in_context)) if ref]


def version_grounds(corpus, kind, body, predecessor, basis=None):
    """What a new version of `predecessor` is written with: its own basis or
    the predecessor's, and -- for a contextual Kind -- the predecessor's
    outcome-of and in-context, or an edited outcome would stop being an
    outcome of anything. Checked as a new entry is; returns
    (basis refs, context pairs)."""
    links = corpus.links(frm=predecessor) if predecessor else []
    inherited = [(x["link"]["to"], x["link"]["relation"], (x.get("body") or {}).get("cite"))
                 for x in links if x["link"]["relation"] in BASIS]
    refs = basis_refs(corpus, kind, basis, inherited=inherited)
    ctx = {x["link"]["relation"]: x["link"]["to"] for x in links
           if x["link"]["relation"] in CONTEXT}
    pairs = (outcome_refs(corpus, kind, body, ctx.get("outcome-of"), ctx.get("in-context"))
             if contextual(corpus, kind) or ctx else [])
    return refs, pairs


def write_grounds(corpus, eid, refs, pairs=(), *, by, writer=None):
    links = [edge(corpus, eid, ref, rel, by=by, writer=writer,
                  body={"cite": cite}) for ref, rel, cite in refs]
    links += [edge(corpus, eid, ref, rel, by=by, writer=writer) for rel, ref in pairs]
    return links


def record(cv, *, kind, body, by, basis=(), outcome_of=None, in_context=None,
           writer=None, context=None, persona=None):
    corpus = cv._c
    # NOT A DOOR TO THE FORMS KINDS, whatever their definitions come to say
    # about `knowing` (`versions.generic_write_refusal`).
    from mentis.conversation.versions import generic_write_refusal
    closed = generic_write_refusal(kind)
    if closed:
        raise ValueError(closed["error"])
    if knowing_of(corpus, kind) not in ("that", "how"):
        raise ValueError(
            f"{kind!r} is not material this surface can record: its current "
            f"definition declares no usable `knowing`, so nothing says whether "
            f"its material states something ('that') or directs how work is "
            f"done ('how')")
    if not isinstance(body, dict) or not body:
        raise ValueError("recorded material needs a body")
    from mentis.api import capability_names
    refusal = body_refusal(corpus, kind, body, capability_names())
    if refusal:
        raise ValueError(refusal["error"])
    refs = basis_refs(corpus, kind, basis)
    pairs = outcome_refs(corpus, kind, body, outcome_of, in_context)
    with corpus.atomic():
        eid = corpus.write(kind=kind, body=body, attributed_to=by, written_by=writer)
        links = write_grounds(corpus, eid, refs, pairs, by=by, writer=writer)
        act = cv.record_act(actor=by, act="material-recorded", about=[eid],
                            detail={"kind": kind, "links": links, "persona": persona}, **(context or {}))
        rel = corpus.current_definition(PRODUCED)
        produced = bool(rel and "relation" in rel["body"])
        if produced:
            edge(corpus, act, eid, PRODUCED, by=by, writer=writer)
    result = {"ok": True, "entry": eid, "kind": kind, "links": links,
              "act": act, "status": "recorded", "stands": False,
              "production_recorded": produced}
    if not produced:
        result["why_not"] = (f"this Brain does not define {PRODUCED!r} as a Relation; "
                             "it defines it as something else, or not at all")
    return result


def requests(corpus, eid, *, open_only=False):
    declines = {x["body"].get("request") for x in corpus.links(relation="declines", to=eid)}
    return [x for x in corpus.links(relation="proposes", to=eid)
            if not open_only or x["id"] not in declines]


def proposed_predecessors(corpus, eid):
    """Old revision proposals carry their intended replacements as relations."""
    relation = corpus.proposal_relation("supersedes")
    if not relation:
        return []
    return [e["link"]["to"] for e in corpus.links(relation=relation, frm=eid)
            if not corpus.stands(e["id"])["superseded_by"]]


def request(cv, *, by, because, entry=None, of=None, body=None, scope=None,
            replaces=None, writer=None, context=None, persona=None,
            requested_by=None):
    """Ask the owner to adopt `entry`, or a revision of `of` written from
    `body`. `by` is who performs this act; `requested_by` is whose request it
    is, when that is somebody else -- the migration writes old proposals'
    requests as their PROPOSER's, and records itself as `migrated_by`."""
    from mentis.wakecheck import _owner
    corpus = cv._c
    said = reason(because)
    if bool(entry) == bool(of):
        raise ValueError("name either entry, or of plus body")
    original = held(corpus, entry or of)
    if not adoptable(corpus, original):
        raise ValueError(NOT_ADOPTABLE)
    if entry and corpus.stands(entry)["stands"]:
        raise ValueError("this material already stands")
    if of and (not isinstance(body, dict) or not body):
        raise ValueError("a revision needs its whole new body")
    if scope is not None and not isinstance(scope, dict):
        raise ValueError("scope must be an object")
    if replaces is not None and (not isinstance(replaces, list) or not all(isinstance(r, str) for r in replaces)):
        raise ValueError("replaces must be a list of held references")
    replaced = list(dict.fromkeys(replaces if replaces is not None else ([of] if of else proposed_predecessors(corpus, entry))))
    for ref in replaced:
        held(corpus, ref)
    if entry in replaced:
        raise ValueError("material cannot replace itself")
    owner = _owner(cv)
    if not owner:
        raise ValueError("the record names no owner to ask for adoption")
    ctx = dict(context or {})
    conversation = ctx.get("conversation")
    if conversation:
        destination = held(corpus, conversation)
        if (destination.get("definition") or {}).get("name") != CONVERSATION:
            raise ValueError("the request Conversation must name a held Conversation")
    with corpus.atomic():
        if not conversation:
            # A manual session or an old entry may have no originating Turn.
            # Give its explicit ask a home without inventing source provenance.
            homes = [e for e in corpus.entries_of_kind(CONVERSATION)
                     if e["body"].get("about") == "explicit ladder adoption requests"
                     and corpus.stands(e["id"])["stands"]]
            conversation = (homes[0]["id"] if homes else cv.open_conversation(
                "Adoption requests", about="explicit ladder adoption requests",
                attributed_to=by, written_by=writer))
            ctx["conversation"] = conversation
        if of:
            candidate = record(cv, kind=original["definition"]["name"], body=body,
                               basis=[of], by=by, writer=writer, context=ctx,
                               persona=persona)
            entry = candidate["entry"]
            corpus.propose_supersession(entry, replaced, attributed_to=by,
                                       written_by=writer, reason=said)
        existing = requests(corpus, entry, open_only=True)
        if existing:
            return {"entry": entry, "request": existing[-1]["id"], "already_requested": True}
        asker = requested_by or by
        migrated = {"migrated_by": by} if asker != by else {}
        note = corpus.create_and_establish(kind="note", body={"text": said},
                                           attributed_to=asker, written_by=writer)
        link = edge(corpus, note, entry, "proposes", by=asker, writer=writer,
                    body={"scope": scope, "replaces": replaced,
                          "wording": body if of else None, "requested_by": asker,
                          **migrated})
        from mentis.conversation import text as text_part
        turn = cv.say(conversation, by, [text_part(f"Request adoption of {entry}: {said}")],
                      addressed_to=[owner], written_by=writer)
        ask = cv.expect(turn, of=owner, kind="decision", by=asker, because=said,
                        caused_by=ctx.get("caused_by"), material=[entry],
                        detail={"adoption_request": link})
        act = cv.record_act(actor=by, act="adoption-requested", about=[entry],
                            because=said, detail={"request": link, "ask": ask,
                                                  "persona": persona,
                                                  "requested_by": asker, **migrated},
                            **ctx)
    return {"ok": True, "entry": entry, "request": link, "ask": ask,
            "act": act, "stands": False, "status": "adoption_requested"}


def challenge(cv, *, target, because, evidence=(), by, writer=None, context=None,
              persona=None):
    corpus = cv._c
    held(corpus, target)
    said = reason(because)
    if not isinstance(evidence, (list, tuple)) or not all(isinstance(r, str) for r in evidence):
        raise ValueError("evidence must be a list of held references")
    for ref in evidence:
        held(corpus, ref)
    with corpus.atomic():
        note = corpus.create_and_establish(kind="note", body={"text": said},
                                           attributed_to=by, written_by=writer)
        link = edge(corpus, note, target, "disputes", by=by, writer=writer,
                    body={"reason": said})
        for ref in evidence:
            edge(corpus, note, ref, "supports", by=by, writer=writer)
        act = cv.record_act(actor=by, act="material-disputed", about=[target],
                            because=said, detail={"link": link, "objection": note,
                                                  "persona": persona},
                            **(context or {}))
    return {"entry": target, "disputed": link, "objection": note, "act": act,
            "revokes": "nothing", "standing": corpus.stands(target)}


def challenge_link(corpus, target, dispute):
    """The `disputes` link `dispute` names, if it is recorded against target."""
    got = corpus.read([dispute]) if isinstance(dispute, str) and dispute else []
    link = (got[0].get("link") or {}) if got else {}
    if not got or link.get("relation") != "disputes" or link.get("to") != target:
        raise ValueError("name the challenge: a `disputes` link recorded "
                         "against this entry")
    return got[0]


def withdraw(cv, *, dispute, because, by, target=None, writer=None, context=None,
             persona=None):
    """The challenger takes their own challenge back, and says why (D7).

    ONLY THE PARTICIPANT THE `disputes` LINK IS ATTRIBUTED TO. Setting aside
    somebody else's challenge is the owner's act and is not this one. Nothing
    is removed: a note holding the reason `withdraws` the challenged entry,
    naming the dispute, and both stay readable in the item and its history.
    """
    from mentis.conversation.ladder import challenges_of
    corpus = cv._c
    got = corpus.read([dispute]) if isinstance(dispute, str) and dispute else []
    if not got:
        raise ValueError("name the challenge to withdraw: a `disputes` link id")
    target = target or (got[0].get("link") or {}).get("to")
    link = challenge_link(corpus, target, dispute)
    said = reason(because)
    if link.get("attributed_to") != by:
        raise ValueError("only the participant who made a challenge may "
                         "withdraw it; this one is attributed to "
                         f"{link.get('attributed_to')!r}. Setting aside another "
                         "participant's challenge is the owner's act")
    row = next((c for c in challenges_of(corpus, target) if c["link"] == dispute), None)
    if row and row["resolution"] != "open":
        raise ValueError(f"that challenge is already {row['resolution'].replace('_', ' ')}")
    with corpus.atomic():
        note = corpus.create_and_establish(kind="note", body={"text": said},
                                           attributed_to=by, written_by=writer)
        wid = edge(corpus, note, target, "withdraws", by=by, writer=writer,
                   body={"dispute": dispute})
        act = cv.record_act(actor=by, act="challenge-withdrawn", about=[target],
                            because=said, detail={"dispute": dispute, "link": wid,
                                                  "note": note, "persona": persona},
                            **(context or {}))
    return {"entry": target, "withdrawn": wid, "dispute": dispute, "note": note,
            "act": act, "standing": corpus.stands(target)}


def owner_act(cv, eid, act, payload, *, by, writer=None, context=None):
    """Adoption and its answer commit together; a failure leaves neither half."""
    from mentis.wakecheck import _owner
    from mentis.web import (_answered_asks, _falsifier_refusal_for_kind,
                            _supersession_refusal)
    corpus = cv._c
    original = held(corpus, eid)
    if by != _owner(cv):
        raise ValueError("only the owner may adopt or decline adoption")
    said = reason(payload.get("because"))
    open_requests = requests(corpus, eid, open_only=True)
    with corpus.atomic():
        if act == "decline":
            selected = payload.get("request")
            chosen = [r for r in open_requests if not selected or r["id"] == selected]
            if not chosen:
                raise ValueError("name an open adoption request for this entry")
            note = corpus.create_and_establish(kind="note", body={"text": said},
                                               attributed_to=by, written_by=writer)
            links = [edge(corpus, note, eid, "declines", by=by, writer=writer,
                          body={"request": r["id"]}) for r in chosen]
            oid = cv.record_act(actor=by, act="adoption-declined", about=[eid],
                                because=said, detail={"links": links}, **(context or {}))
            return {"entry": eid, "declined": links, "act": oid,
                    **_answered_asks(cv, eid, by=by, act="declined")}
        if not adoptable(corpus, original):
            raise ValueError(NOT_ADOPTABLE)
        fields = payload.get("body")
        if fields is None and corpus.stands(eid)["stands"]:
            raise ValueError("this material already stands; adopting it again "
                             "would establish it twice")
        kind = original["definition"]["name"]
        refusal = _falsifier_refusal_for_kind(corpus, kind, payload, entry=eid)
        if refusal:
            raise ValueError(refusal["error"])
        target = eid
        if fields is not None:
            target = record(cv, kind=kind, body=fields, basis=[eid], by=by,
                            writer=writer, context=context)["entry"]
        req = open_requests[-1]["body"] if open_requests else {}
        replaced = payload.get("replaces")
        if replaced is None:
            replaced = (req["replaces"] if req.get("replaces") is not None
                        else proposed_predecessors(corpus, eid))
        if not isinstance(replaced, list) or not all(isinstance(ref, str) for ref in replaced):
            raise ValueError("replaces must be a list of held entries")
        replaced = list(dict.fromkeys([*replaced, *([eid] if fields is not None else [])]))
        places = list(placements_now(corpus, eid))
        established = corpus.establish(target, attributed_to=by, written_by=writer, reason=said)
        for ref in replaced:
            held(corpus, ref)
            places.extend(placements_now(corpus, ref))
        scope = payload.get("scope", req.get("scope"))
        if scope is not None:
            if not isinstance(scope, dict):
                raise ValueError("scope must be an object")
            where = scope.get("where") or scope.get("conversation")
            if scope.get("whole_brain"):
                if where:
                    raise ValueError("scope names where or whole_brain, not both")
                where = cv.whole_brain(create=True, by=by, written_by=writer)
            if where:
                held(corpus, where)
                places.append(where)
        if knowing_of(corpus, kind) == "how":
            from mentis.conversation import declared_placement_refusal
            for place in dict.fromkeys(places):
                refusal = declared_placement_refusal(corpus, target, place)
                if refusal:
                    raise ValueError(refusal["error"])
                if cv.is_whole_brain(place):
                    refusal = cv.whole_brain_refusal(target)
                    if refusal:
                        raise ValueError(refusal["error"])
                edge(corpus, target, place, "scoped-to", by=by, writer=writer,
                     body={"reason": said})
        for ref in replaced:
            refusal = _supersession_refusal(corpus, ref, target)
            if refusal:
                raise ValueError(refusal["error"])
        links = [edge(corpus, target, ref, "supersedes", by=by, writer=writer,
                      body={"reason": said}) for ref in replaced]
        for ref in replaced:
            cv.carry_intake_forward(ref, target, by=by, written_by=writer)
        oid = cv.record_act(actor=by, act="material-adopted", about=[eid, target],
                            because=said, detail={"established": established,
                            "replaces": replaced, "links": links, "scope": scope,
                            "falsifier": payload.get("falsifier")}, **(context or {}))
        answers = _answered_asks(cv, eid, by=by, act="adopted")
        for ref in replaced:
            if ref != eid:
                answers["answers"] += _answered_asks(cv, ref, by=by, act="adopted")["answers"]
    return {"entry": target, "adopted": established, "act": oid,
            "standing": corpus.stands(target), **answers}
