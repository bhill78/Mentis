"""Computed reads over operational ancestry: graph, deferral, reconstruction.

These began as trial code. The web surface needs them, and production must not
import from the trial tree -- a standing test enforces that, and it caught this
when the web layer first reached for them. So the canonical implementations
live here and the trials re-export them, which also means there is one
implementation rather than two that drift apart.

Everything here is COMPUTED. Nothing is stored, nothing is cached, and deleting
any of it loses nothing. Mentis decides no priority and reaches no verdict: it
reports the shape of the work and the reader decides what it means.

Built on the public seam only -- no store, no SQL, no record shapes.
"""

from __future__ import annotations

from dataclasses import dataclass

REPLIES_TO = "replies-to"


# ---------------------------------------------------------------------------
# ancestry


def causal_path(brain, act_id) -> list[dict]:
    """Walk `caused_by` back to the beginning. This is the ancestry."""
    cv = brain.conversations
    by_id = {a["id"]: a for a in cv.history()}
    chain, cur, seen = [], act_id, set()
    while cur and cur in by_id and cur not in seen:
        seen.add(cur)
        a = by_id[cur]
        chain.insert(0, {"act": a["act"], "actor": cv.alias(a["actor"]),
                         "id": a["id"], "turn": a["turn"],
                         "conversation": a["conversation"],
                         "because": a["because"]})
        cur = a["caused_by"]
    return chain


def trunk_of(brain, act_id) -> dict:
    """The chain back to the act that began the work, and its Turn if it had one.

    Brain-scoped work has no originating Turn, and this says None rather than
    borrowing one from somewhere else.

    A FINDING IS THE ROOT OF ITS OWN TRUNK. Discovered work is caused by the
    request that found it, and that link is kept as its provenance
    (`discovered_under`) -- but it is not membership: the walk stops at the
    finding, so work done on it is never counted as the work it was found
    under, and neither holds the other open. `causal_path` still walks the
    whole chain.

    WALKED, NEVER LOADED: one indexed read per step up the chain. This read
    every act in the record to walk one chain, and `deferred()` called it once
    per finding -- measured 2026-10-09 at 25s on the live Brain (158 findings,
    3.16 million JSON decodes), stalling the Conversation list while it ran.
    """
    cv = brain.conversations
    chain, cur, seen, finding = [], act_id, set(), False
    while cur and cur not in seen:
        a = cv._act(cur)
        if a is None:
            break
        seen.add(cur)
        chain.insert(0, a)
        if _is_finding(cv, a):
            finding = True
            break
        cur = a["caused_by"]
    root = chain[0] if chain else None
    return {"chain": [a["id"] for a in chain], "depth": len(chain),
            "root_act": root["id"] if root else None,
            "originating_turn": root["turn"] if root else None,
            "discovered_under": root["caused_by"] if finding else None,
            "actors": [cv.alias(a["actor"]) for a in chain]}


def _is_finding(cv, act) -> bool:
    """A request kept as discovered work (`record_discovered_work`)."""
    return act["act"] == "expectation-recorded" and cv.is_finding(act["id"])


def graph(brain, *, conversation=None) -> dict:
    """Nodes and edges for a work-history view. A UI could draw this."""
    from mentis.operational.products import products_of
    cv, corpus = brain.conversations, brain.primary
    nodes, edges, seen = [], [], set()

    def node(nid, kind, label, **extra):
        if nid and nid not in seen:
            seen.add(nid)
            nodes.append({"id": nid, "kind": kind, "label": label, **extra})

    for p in cv.all_participants():
        node(p["id"], "participant", p["body"]["alias"])
    for conv in cv.all_conversations():
        if conversation and conv["id"] != conversation:
            continue
        node(conv["id"], "conversation", conv["body"]["name"])
        for row in cv.turns(conv["id"]):
            e = row["entry"]
            said = " ".join(x.get("text", "") for x in e["body"]["parts"]
                            if x.get("type") == "text")
            node(row["turn"], "turn", f"#{row['number']} {said[:48]}",
                 conversation=conv["id"], number=row["number"])
            edges.append({"from": row["turn"], "to": conv["id"], "edge": "in"})
            edges.append({"from": e["attributed_to"], "to": row["turn"],
                          "edge": "said"})
            for r in corpus.links(relation=REPLIES_TO, frm=row["turn"]):
                edges.append({"from": row["turn"], "to": r["link"]["to"],
                              "edge": "replies-to"})

    # PRODUCTION IS ITS OWN EDGE, and it is drawn from the `produced` Relation
    # alone. An act that only appears under `about` REFERENCED what it names.
    # Merging the two would make a reference indistinguishable from the work
    # that made the thing, which is the one thing this graph must not do.
    #
    # Products are noded FIRST because a product's own Kind is the best
    # description of it that exists: `about` below falls back to calling an
    # unrecognised reference an artifact, and a node is written once.
    history = list(cv.history(conversation=conversation))
    made = products_of(brain, [a["id"] for a in history])
    for act_id, rows in made.items():
        for p in rows:
            node(p["entry"], p["kind"] or p["family"] or "entry",
                 (p["summary"] or p["kind"] or p["entry"])[:48],
                 family=p["family"], meaning=p["meaning"])

    for a in history:
        node(a["id"], "act", a["act"], at=a["at"], actor=a["actor"],
             because=a["because"])
        edges.append({"from": a["actor"], "to": a["id"], "edge": "did"})
        for p in made.get(a["id"], []):
            edges.append({"from": a["id"], "to": p["entry"], "edge": "produced"})
        if a["caused_by"]:
            edges.append({"from": a["caused_by"], "to": a["id"], "edge": "caused"})
        if a["turn"]:
            edges.append({"from": a["id"], "to": a["turn"], "edge": "concerns"})
        if a["execution"]:
            node(a["execution"], "execution", a["execution"][:12],
                 runtime=a["runtime"])
            edges.append({"from": a["id"], "to": a["execution"], "edge": "in"})
        for ref in a["about"]:
            if ref.startswith("ent-"):
                got = corpus.read([ref])
                if got:
                    kind = (got[0].get("definition") or {}).get("name")
                    node(ref, kind or "entry",
                         (got[0]["body"].get("text") or kind or ref)[:48])
            else:
                node(ref, "artifact", ref)
            edges.append({"from": a["id"], "to": ref, "edge": "about"})
    return {"nodes": nodes, "edges": edges}


# ---------------------------------------------------------------------------
# deferral and reconsideration -- Task Gravity's evidence, never its verdict


def deferred(brain) -> list[dict]:
    """Side work recorded and then not followed.

    Not a field and not a status: an act that noticed a problem, or a finding
    recorded with `record_discovered_work`, that has NOTHING CAUSED BY IT. A
    finding is followed when anything is caused by its expectation -- an
    assignment, a claim it was met, the owner pursuing or dismissing it -- so it
    stops being deferred the moment somebody acts on it, with nothing updated.
    A finding the owner chose to keep deferred has nothing caused by it, and
    stays here.
    """
    from mentis.operational.products import products_of
    cv = brain.conversations
    acts = cv.history()
    followed = {a["caused_by"] for a in acts if a["caused_by"]}
    candidates = [a for a in acts if a["id"] not in followed and (
        a["act"] == "problem-noticed"
        or (a["act"] == "work-discovered" and a["about"]
            and a["about"][0] not in followed))]
    made = products_of(brain, [a["id"] for a in candidates])
    out = []
    for a in candidates:
        anc = trunk_of(brain, a["id"])
        finding = a["about"][0] if a["act"] == "work-discovered" else None
        out.append({"act": a["id"], "by": cv.alias(a["actor"]),
                    "because": a["because"] or _said(cv, finding),
                    "about": a["about"], "at": a["at"],
                    "conversation": a["conversation"],
                    # THE FINDING'S OWN IDENTITY, where it is one: the
                    # expectation it was kept as, which is what is chosen,
                    # assigned and carried. None for a noticed problem.
                    "finding": finding,
                    "originating_turn": anc["originating_turn"],
                    "depth_from_root": anc["depth"],
                    # What the side observation actually left behind, if
                    # anything. Still no status field: this is the same
                    # `produced` read as everywhere else.
                    "produced": made.get(a["id"], [])})
    return out


def _said(cv, expectation) -> str | None:
    """What a finding says it is: its reason, else the words of its Turn.

    Findings recorded before their reason was written on them say what they
    are only in their Turn, and are read from there rather than left blank.
    """
    exp = cv._act(expectation) if expectation else None
    if not exp:
        return None
    if exp.get("because"):
        return exp["because"]
    got = cv._c.read([exp["turn"]]) if exp.get("turn") else []
    words = " ".join(p.get("text", "") for p in
                     (got[0]["body"].get("parts") or [])
                     if p.get("type") == "text").strip() if got else ""
    return words or None


# ---------------------------------------------------------------------------
# follow-up permission -- the owner's, on the original request
#
# AS DECIDED (owner, 2026-10-09). Agents judge whether discovered work is
# necessary to the trunk (ordinary delegation), deferred (recorded), or worth
# pursuing on its own. Whether they may pursue it WITHOUT ASKING is the owner's
# permission, given when they ask: ask afterward (the default), up to N
# generations of independently pursued discovery, or unrestricted. It belongs
# to the ORIGINAL request and carries through its follow-ups: read from the
# record's lineage, never from a run, so starting another execution cannot
# reset it. Permission allows pursuit; it requires none. What is not pursued
# is put to the owner when the trunk it was found under is finished.

ASK = "ask"
UNRESTRICTED = "unrestricted"


def follow_up_value(raw):
    """The owner's follow-up permission as recorded, or ValueError in words.
    Absent is the default, "ask"; a depth is a positive whole number."""
    if raw in (None, ASK):
        return ASK
    if raw == UNRESTRICTED:
        return UNRESTRICTED
    depth = raw.get("depth") if isinstance(raw, dict) else None
    if isinstance(depth, int) and not isinstance(depth, bool) and depth >= 1:
        return {"depth": depth}
    raise ValueError("follow_up is \"ask\", \"unrestricted\", or "
                     "{\"depth\": N} with N a whole number of 1 or more")


def discovery(cv, expectation) -> dict:
    """Where work stands among discoveries: the ORIGINAL request it serves,
    and how many GENERATIONS of independently pursued discovery separate it
    from that objective. Each finding on the way up is one generation;
    necessary work delegated inside a trunk is none. Walked up `caused_by`,
    one indexed read a step -- the lineage is the record."""
    origin, generation, cur, seen = None, 0, expectation, set()
    while cur and cur not in seen:
        a = cv._act(cur)
        if a is None or a["act"] != "expectation-recorded":
            break
        seen.add(cur)
        origin = a
        if cv.is_finding(cur):
            generation += 1
        cur = a["caused_by"]
    return {"origin": origin["id"] if origin else None,
            "generation": generation}


def follow_up_of(cv, origin) -> object:
    """The permission the owner gave on this original request."""
    exp = cv._act(origin) if origin else None
    try:
        return follow_up_value(((exp or {}).get("detail") or {})
                               .get("follow_up"))
    except ValueError:
        return ASK


def pursuit_permitted(cv, finding) -> dict | None:
    """Whether the owner's permission lets this finding be pursued without
    asking again -- {"origin", "generation", "follow_up"} -- or None."""
    if not cv.is_finding(finding) or owner_decided(cv, finding):
        return None
    where = discovery(cv, finding)
    allowed = follow_up_of(cv, where["origin"])
    ok = (allowed == UNRESTRICTED
          or (isinstance(allowed, dict)
              and where["generation"] <= allowed["depth"]))
    return {**where, "follow_up": allowed} if ok else None


def owner_decided(cv, finding) -> str | None:
    """What the owner has said about this finding that permission may not
    override, or None: dismissed, kept deferred, or put to them and not yet
    answered. Permission lets agents pursue without ASKING; it never lets
    them pursue what the owner turned down or is still deciding."""
    if any(a["act"] == "work-dismissed" for a in cv.history(caused_by=finding)):
        return "dismissed"
    latest = None                     # the owner's LATEST answer stands
    for offer in cv.history(act=RECONSIDERATION_OFFERED):
        if finding not in ((offer["detail"] or {}).get("findings") or ()):
            continue
        decision = offer["detail"]["decision_expectation"]
        done = resolution_of(cv, decision)
        if done is None:
            # WITHDRAWN IS NOT DECIDED. The owner closed the question without
            # choosing, so the finding is neither pursued nor dismissed -- and
            # permission does not get to answer it in their place.
            if withdrawal_of(cv, decision):
                latest = "withdrawn"
                continue
            return "awaiting the owner's decision"
        latest = done["detail"]["selections"].get(finding) or latest
    if latest == "withdrawn":
        return "in a decision the owner withdrew"
    return "kept deferred" if latest == "defer" else None


def trunk_findings(brain, originating_turn) -> list[dict]:
    """Findings discovered under THIS trunk that nobody has followed, in the
    shape `deferred()` gives. Walked down from the trunk's own requests --
    each step one indexed read of what it caused -- through work delegated
    inside it, stopping at findings (each is its own trunk). Nothing outside
    this trunk is read."""
    cv = brain.conversations
    # THE TRUNK, AS `trunk_of` DEFINES IT, WALKED DOWNWARD: from the acts on
    # its Turn that begin it -- caused by nothing, or a finding, which is the
    # root of its own trunk -- through everything they caused, stopping at
    # findings. One indexed read per act in this trunk; nothing else.
    stack = [a for a in cv.history(turn=originating_turn)
             if not a["caused_by"] or _is_finding(cv, a)]
    seen, found, noticed = {a["id"] for a in stack}, [], []
    while stack:
        for c in cv.history(caused_by=stack.pop()["id"]):
            if c["id"] in seen:
                continue
            seen.add(c["id"])
            if _is_finding(cv, c):
                found.append(c["id"])
                continue
            if c["act"] == "problem-noticed":
                noticed.append(c)
            stack.append(c)
    # A NOTICED PROBLEM nothing followed is set aside too, as it always was.
    out = [{"act": a["id"], "by": cv.alias(a["actor"]),
            "because": a["because"], "about": a["about"], "at": a["at"],
            "conversation": a["conversation"], "finding": None,
            "originating_turn": originating_turn, "depth_from_root": 0,
            "produced": []}
           for a in noticed if not cv.history(caused_by=a["id"])]
    for f in found:
        if cv.history(caused_by=f):
            continue                       # assigned, chosen, met: followed
        exp = cv._act(f)
        disc = next((a for a in cv.history(turn=exp["turn"])
                     if a["act"] == "work-discovered"
                     and f in (a["about"] or ())), None)
        if disc is None:
            continue
        out.append({"act": disc["id"], "by": cv.alias(disc["actor"]),
                    "because": disc["because"] or _said(cv, f),
                    "about": disc["about"], "at": disc["at"],
                    "conversation": disc["conversation"], "finding": f,
                    "originating_turn": originating_turn,
                    "depth_from_root": trunk_of(brain, disc["id"])["depth"],
                    "generation": discovery(cv, f)["generation"],
                    "produced": []})
    return out


def trunk_state(brain, originating_turn) -> dict:
    """Is the originating work finished? Read from the expectations on its Turn.

    FINISHED IS ITS CARRIER'S CLAIM, NOT A REPLY. A reply on the way is a
    progress report, and a run ending without claiming the work met left it
    unfinished; only `expectation-met` says the work is done -- the same claim
    that ends a wait on it. And nothing it declared it waits on -- a child it
    needs back, a decision it asked, work it awaits -- may be outstanding:
    that is `waiting_on`, the one waiting model, asked as it is.
    """
    cv = brain.conversations
    exps = [a["id"] for a in cv.history(turn=originating_turn)
            if a["act"] == "expectation-recorded"]
    states = [cv.expectation_state(e) for e in exps]
    waiting = [o for e in exps for o in cv.waiting_on(e)["outstanding"]]
    return {"originating_turn": originating_turn,
            "turn_number": cv.turn_number(originating_turn),
            "complete": (bool(states) and not waiting
                         and all(s["satisfied_by"] for s in states)),
            "outstanding_on_trunk": [s["expects"] for s in states
                                     if not s["satisfied_by"]],
            "waiting_on": waiting}


def reconsideration(brain, originating_turn) -> dict:
    """What a reader should be offered once the trunk is done. It decides nothing."""
    state = trunk_state(brain, originating_turn)
    items = trunk_findings(brain, originating_turn)
    out = {"trunk": state, "deferred": items,
           "due_for_reconsideration": state["complete"] and bool(items)}
    offers = _offers(brain.conversations, originating_turn)
    if offers:
        out["reconsideration_offer"] = offers[-1]["id"]
        out["reconsideration_expectation"] = \
            offers[-1]["detail"]["decision_expectation"]
    return out


RECONSIDERATION_OFFERED = "reconsideration-offered"

#: What the owner may do with each finding. Nothing else is a choice.
CHOICES = ("pursue", "defer", "dismiss")


def _offers(cv, originating_turn=None) -> list[dict]:
    return [a for a in cv.history(act=RECONSIDERATION_OFFERED)
            if originating_turn is None
            or (a["detail"] or {}).get("originating_turn") == originating_turn]


def reconsider_after(brain, expectation) -> dict | None:
    """A run of `expectation` ended: offer its trunk's findings, if it is done.

    Called from the end of every run (`dispatch.resume_if_ready`), because a
    run ending is the only moment a trunk can become finished -- its carrier
    claimed it met inside the run, or the last child it was waiting on ended.
    """
    turn = (trunk_of(brain, expectation)["originating_turn"]
            if expectation else None)
    return offer_reconsideration(brain, turn) if turn else None


def offer_reconsideration(brain, originating_turn) -> dict | None:
    """ONE consolidated decision for the owner, once the trunk is finished.

    Asks about every finding discovered under this trunk that is still
    deferred, in one ordinary decision -- `expectation-recorded`, kind
    decision, of the owner, with its options -- so it is owed, shown and
    answered exactly as any decision is. Nothing runs because of it.

    ONCE PER COMPLETION. The offer names the claim that finished the trunk,
    and is checked and written in one transaction, so a retry or two runs
    ending together find it already written and return it. A finding already
    in an offer nobody has answered is not asked about again; one the owner
    kept deferred is asked about again only if the trunk is finished again.

    THE DECISION DOES NOT HOLD THE TRUNK. It is caused by the claim that the
    trunk was met, not by the trunk's request, so it is not something that
    request waits on: the trunk is finished, and this is about what it left.
    """
    if not originating_turn:
        return None
    cv = brain.conversations
    with cv._c.atomic():
        if not trunk_state(brain, originating_turn)["complete"]:
            return None
        trunk = [a for a in cv.history(turn=originating_turn)
                 if a["act"] == "expectation-recorded"][0]
        met = cv.expectation_state(trunk["id"])["satisfied_by"][-1]
        offers = _offers(cv)
        mine = [a for a in offers if a["detail"].get("completion") == met]
        if mine:
            return mine[-1]
        # A WITHDRAWN OFFER HOLDS NOTHING BACK: nothing was chosen, so what
        # it asked about is asked again, like anything kept deferred.
        pending = {f for a in offers
                   if not resolution_of(cv, a["detail"]["decision_expectation"])
                   and not withdrawal_of(cv,
                                         a["detail"]["decision_expectation"])
                   for f in a["detail"]["findings"]}
        findings = [d["finding"] for d in trunk_findings(brain,
                                                         originating_turn)
                    if d["finding"] and d["finding"] not in pending]
        if not findings:
            return None
        asked = ask_about_findings(
            brain, findings, conversation=trunk["conversation"],
            by=cv.assigned_carrier(trunk["id"])["carrier"] or trunk["actor"],
            owner=_owner_of(brain, trunk), caused_by=met, completion=met,
            originating_turn=originating_turn, replies_to=originating_turn,
            question="Finished. These were found along the way and kept "
                     "aside: pursue, keep deferred or dismiss each.")
        return cv._act(asked["offer"])


def ask_about_findings(brain, findings, *, conversation, by, owner,
                       caused_by, originating_turn, question,
                       replies_to=None, completion=None,
                       written_by=None) -> dict:
    """Put findings to their owner as ONE ordinary decision. The only way.

    Used when a trunk is finished (`offer_reconsideration`) and when the agent
    carrying it proposes, before then, that a finding be pursued on its own
    (`request_decision` naming findings). Either way it is a Turn, a decision
    expectation of the owner carrying structured options, and a
    `reconsideration-offered` act naming the findings -- which is what makes
    an answer to it a choice about them, and nothing else is.
    """
    from mentis.conversation import text as part
    cv = brain.conversations
    labels = [(_said(cv, f) or f)[:80] for f in findings]
    said = "\n".join([question] + [f"  {i}. {lab} [{f}]" for i, (f, lab)
                                   in enumerate(zip(findings, labels), 1)])
    turn = cv.say(conversation, by, [part(said)], addressed_to=[owner],
                  replies_to=replies_to, written_by=written_by)
    options = _options(findings, labels)
    decision = cv.expect(
        turn, of=owner, kind="decision", by=by, caused_by=caused_by,
        because="what to do with work found along the way",
        detail={"options": options,
                "reconsideration": {"originating_turn": originating_turn,
                                    "findings": list(findings)}})
    offer = cv.record_act(
        actor=by, act=RECONSIDERATION_OFFERED, conversation=conversation,
        turn=turn, caused_by=decision, about=[decision, *findings],
        detail={"originating_turn": originating_turn,
                "decision_expectation": decision, "findings": list(findings),
                "completion": completion})
    return {"turn": turn, "expectation": decision, "offer": offer,
            "options": options}


def _owner_of(brain, trunk) -> str:
    """Whose work a trunk is: whoever asked for it.

    A finding was recorded by the run that found it, but it is somebody's work
    only because its owner chose it -- and the owner who may choose it is the
    owner of the work it was found under.
    """
    found = trunk_of(brain, trunk["id"])["discovered_under"]
    if found:
        up = brain.conversations._act(trunk_of(brain, found)["root_act"])
        if up and up["act"] == "expectation-recorded":
            return _owner_of(brain, up)
    return trunk["actor"]


def _options(findings, labels) -> list[dict]:
    """The alternatives, each carrying what it selects as data.

    WHAT AN OPTION MEANS IS ITS `selections`, never its label: the label is
    for a person to read, and resolution reads only the recorded structure.
    The one alternative that cannot be written in advance -- a different
    choice for each finding -- is an option too, `per_finding`, whose
    selections the owner supplies and which are checked against the findings
    it lists.
    """
    def every(c):
        return {f: c for f in findings}
    pursue = ("becomes its own piece of work, assigned and started for you; "
              "where it was found stays recorded")
    if len(findings) == 1:
        return [{"label": f"Pursue: {labels[0]}", "consequence": pursue,
                 "selections": every("pursue")},
                {"label": f"Keep deferred: {labels[0]}",
                 "consequence": "stays recorded and unassigned; nothing runs",
                 "selections": every("defer")},
                {"label": f"Dismiss: {labels[0]}",
                 "consequence": "kept in the record as dismissed; it can no "
                                "longer be picked up",
                 "selections": every("dismiss")}]
    return [{"label": "Pursue all findings", "consequence": pursue,
             "selections": every("pursue")},
            {"label": "Keep all deferred",
             "consequence": "they stay recorded and unassigned; nothing runs",
             "selections": every("defer")},
            {"label": "Dismiss all findings",
             "consequence": "kept in the record as dismissed",
             "selections": every("dismiss")},
            {"label": "Decide each finding",
             "consequence": "pursue, keep deferred or dismiss each one",
             "per_finding": True,
             "findings": [{"ref": f, "label": lab}
                          for f, lab in zip(findings, labels)]}]


def reconsideration_choices(cv, decision_exp, *, actor, chose=None,
                            pursue=None, defer=None, dismiss=None) -> dict:
    """What the owner chose for each finding, or why that is not a choice.

    Checked against the record and nothing else: the decision must be a
    reconsideration Mentis offered; only the person it was asked of may
    answer it -- never whoever happens to coordinate, and never a default;
    and every finding named must be one it offered, with one choice each.
    A finding not named is kept deferred. Reads only; writes nothing.
    """
    exp = cv._act(decision_exp) if decision_exp else None
    meta = ((exp or {}).get("detail") or {}).get("reconsideration")
    if (not exp or exp["act"] != "expectation-recorded" or not meta
            or not any((a["detail"] or {}).get("decision_expectation")
                       == decision_exp for a in _offers(cv))):
        return {"error": "that is not a reconsideration decision Mentis "
                         "offered", "expectation": decision_exp}
    owner = exp["about"][0] if exp["about"] else None
    if not actor or actor != owner:
        return {"error": "only the person this decision was asked of can "
                         "make it", "expectation": decision_exp,
                "asked_of": owner}
    findings = list(meta["findings"])
    if chose is not None:
        options = exp["detail"].get("options") or []
        index = chose.get("option") if isinstance(chose, dict) else None
        if (not isinstance(index, int) or isinstance(index, bool)
                or not 0 <= index < len(options)):
            return {"error": "that is not one of the options offered"}
        option = options[index]
        if option.get("per_finding"):
            given = chose.get("selections")
        else:
            given = option.get("selections")
            if chose.get("selections") not in (None, given):
                return {"error": "that option already says what it selects"}
        if not isinstance(given, dict):
            return {"error": "deciding each finding names a choice for each"}
    else:
        given = {}
        for c, refs in (("pursue", pursue), ("defer", defer),
                        ("dismiss", dismiss)):
            for f in refs or ():
                if given.setdefault(f, c) != c:
                    return {"error": "a finding can be given one choice",
                            "finding": f}
    stray = [f for f in given if f not in findings]
    if stray:
        return {"error": "this decision did not offer those", "named": stray,
                "offered": findings}
    wrong = {f: c for f, c in given.items() if c not in CHOICES}
    if wrong:
        return {"error": f"each finding is one of {list(CHOICES)}",
                "named": wrong}
    return {"decision": decision_exp, "owner": owner, "exp": exp,
            "selections": {f: given.get(f, "defer") for f in findings}}


def resolution_of(cv, decision_exp) -> dict | None:
    """The owner's recorded resolution of a reconsideration, or None.

    It is the decision's own `expectation-met`, by the person it was asked of,
    carrying the selections -- the same act that answers any request.
    """
    exp = cv._act(decision_exp) if decision_exp else None
    if not exp or not exp["about"]:
        return None
    return next((a for a in cv.history(caused_by=decision_exp)
                 if a["act"] == "expectation-met"
                 and a["actor"] == exp["about"][0]
                 and "selections" in (a["detail"] or {})), None)


def withdrawal_of(cv, decision_exp) -> dict | None:
    """The owner's recorded withdrawal of a decision, or None.

    Also the decision's own `expectation-met` by the person it was asked of,
    but marked `withdrawn` and carrying NO selections: it closes the decision
    and chooses nothing, so `resolution_of` never reads it as a choice.
    """
    exp = cv._act(decision_exp) if decision_exp else None
    if not exp or not exp["about"]:
        return None
    return next((a for a in cv.history(caused_by=decision_exp)
                 if a["act"] == "expectation-met"
                 and a["actor"] == exp["about"][0]
                 and (a["detail"] or {}).get("withdrawn")), None)


def owner_selected(cv, finding) -> dict | None:
    """The owner's resolved choice to pursue this finding, or None.

    The only thing that lets discovered work be picked up. Read back from the
    record and checked again -- the pursuit and the resolution it names, by
    the same person, who was the one asked, saying `pursue` for this finding --
    so no act written any other way can stand in for it.
    """
    for a in cv.history(caused_by=finding):
        if a["act"] != "work-pursued":
            continue
        done = resolution_of(cv, (a["detail"] or {}).get("decision"))
        if (done and done["actor"] == a["actor"]
                and done["detail"]["selections"].get(finding) == "pursue"):
            return a
    return None


def resolve_reconsideration_decision(brain_or_cv, decision_exp, *,
                                     chose=None, pursue=None, dismiss=None,
                                     defer=None, actor=None,
                                     turn=None) -> dict:
    """Record the owner's choice for each finding, once.

    One transaction: the decision's `expectation-met` carrying every
    selection -- so it stops being owed, and what was kept deferred is
    recorded as chosen -- and `work-pursued` / `work-dismissed` caused by each
    finding so chosen, which is what stops it being deferred. Nothing is
    assigned or started here.

    A RETRY IS ANSWERED WITH THE FIRST RESULT and writes nothing; a different
    choice after one was recorded is refused, never applied beside it.
    Returns an `error` and writes nothing when the choice is not the owner's,
    or not one this decision offered.
    """
    cv = getattr(brain_or_cv, "conversations", brain_or_cv)
    with cv._c.atomic():
        got = reconsideration_choices(cv, decision_exp, actor=actor,
                                      chose=chose, pursue=pursue,
                                      defer=defer, dismiss=dismiss)
        if "error" in got:
            return got
        chosen, exp = got["selections"], got["exp"]
        # A WITHDRAWN DECISION IS CLOSED. Choosing on it now would start or
        # dismiss work on a question the owner took back.
        gone = withdrawal_of(cv, decision_exp)
        if gone:
            return {"error": "this decision was withdrawn",
                    "expectation": decision_exp, "withdrawn": gone["id"]}
        done = resolution_of(cv, decision_exp)
        if done:
            if done["detail"]["selections"] != chosen:
                return {"error": "this decision was already made otherwise",
                        "expectation": decision_exp,
                        "decided": done["detail"]["selections"]}
            return _resolved(decision_exp, chosen, done["id"], repeat=True)
        # ONE EFFECT PER FINDING, whichever decision asked about it. A finding
        # another decision already pursued or dismissed is not chosen again
        # here: refused, with what was chosen, and nothing written.
        before = {f: a for f, c in chosen.items() if c != "defer"
                  for a in cv.history(caused_by=f)
                  if a["act"] in ("work-pursued", "work-dismissed")}
        if before:
            return {"error": "another decision already chose what to do "
                             "with these findings",
                    "expectation": decision_exp,
                    "decided": {f: {"act": a["act"],
                                    "decision": a["detail"].get("decision")}
                                for f, a in before.items()}}
        meta = exp["detail"]["reconsideration"]
        for f, c in chosen.items():
            if c != "defer":
                cv.record_act(
                    actor=actor, act=("work-pursued" if c == "pursue"
                                      else "work-dismissed"),
                    conversation=exp["conversation"], turn=exp["turn"],
                    caused_by=f, about=[f],
                    because=f"the owner chose to {c} it",
                    detail={"decision": decision_exp,
                            "originating_turn": meta["originating_turn"]})
        met = cv.record_act(
            actor=actor, act="expectation-met",
            conversation=exp["conversation"], turn=exp["turn"],
            caused_by=decision_exp, about=[turn] if turn else [],
            because="the owner chose what to do with each finding",
            detail={"selections": chosen})
        return _resolved(decision_exp, chosen, met, repeat=False)


def _resolved(decision, chosen, met, *, repeat) -> dict:
    return {"ok": True, "decision": decision, "resolution": met,
            "selections": chosen, "repeat": repeat,
            **{k: [f for f, c in chosen.items() if c == one]
               for k, one in (("pursued", "pursue"), ("deferred", "defer"),
                              ("dismissed", "dismiss"))}}


# ---------------------------------------------------------------------------
# reconstruction


@dataclass
class Reconstruction:
    who: dict
    where: dict
    persona: dict | None
    completed: list
    outstanding: list
    sufficient: bool
    missing: list
    sources: list

    def rendered(self) -> str:
        lines = [f"You are {self.who['alias']} ({self.who['participant']})."]
        if self.where["kind"] == "conversation":
            lines.append(f"You are working in: {self.where['name']} "
                         f"- {self.where['about']}")
        else:
            lines.append("You are operating at Brain scope, in no particular "
                         "conversation.")
        if self.persona:
            lines.append(f"Behaving as {self.persona['name']}: "
                         f"{self.persona['behaviour']}")
        if self.completed:
            lines.append("Already finished, and NOT to be done again:")
            for c in self.completed:
                lines.append(f"  - {c['text']}   [{c['id']}]")
        else:
            lines.append("Nothing durable records any completed step.")
        if self.outstanding:
            lines.append("Outstanding:")
            for o in self.outstanding:
                lines.append(f"  - {o['text']}   [{o['id']}]")
        if not self.sufficient:
            lines.append("MENTIS DOES NOT HOLD ENOUGH TO CONTINUE THIS WORK. "
                         "Missing: " + "; ".join(self.missing) + ". "
                         "Say so plainly and do not invent what happened.")
        lines.append("Mentis holds a great deal more. Ask it about anything you "
                     "run into rather than assuming.")
        return "\n".join(lines)


def reconstruct(brain, who: str, *, conversation=None) -> Reconstruction:
    """A bounded operating context for a FRESH execution.

    Durable records and delivery evidence only. Never runtime history, never a
    transcript replay, and it reports what is missing rather than filling it.

    `who` IS A REFERENCE WHERE ONE EXISTS, AND A NAME ONLY WHERE IT MUST BE.
    This used to take an alias and resolve it with `find_participant`, which
    returns the FIRST match -- so with two deliberate Participants both called
    `@Ada`, the second reconstructed as the first: its Conversation, its
    Persona, its completed work. Dispatch already carries the durable
    reference and the record already keeps it, on every operational act and
    every delivery, so a caller holding one passes it and nothing is guessed.

    AN ALIAS THAT NAMES SEVERAL IS ANSWERED AS AMBIGUOUS, NOT AS THE FIRST.
    Older material may hold nothing but a name, and that stays reconstructable
    for as long as the name means one Participant. Where it means more than
    one, the candidates are returned and the context is reported insufficient,
    because choosing here would be presenting a guess about who somebody is as
    a fact about it.
    """
    cv = brain.conversations
    corpus = brain.primary
    missing, sources = [], []

    if str(who).startswith("ent-"):
        # A reference identifies itself. It is still checked for being a
        # Participant rather than trusted, so a stale or mistyped one is said
        # out loud instead of reconstructing something that is not a somebody.
        got = corpus.read([who])
        kind = (got[0].get("definition") or {}).get("name") if got else None
        if kind != "participant":
            return Reconstruction(
                who={"alias": None, "participant": None, "asked_for": who},
                where={"kind": "unknown"}, persona=None, completed=[],
                outstanding=[], sufficient=False,
                missing=["that reference is not a durable Participant" if got
                         else "the record holds no such reference"],
                sources=[])
        participant, alias = who, cv.alias(who)
    else:
        alias = who
        named = cv.participants_named(alias)
        if len(named) > 1:
            return Reconstruction(
                who={"alias": alias, "participant": None, "candidates": named},
                where={"kind": "unknown"}, persona=None, completed=[],
                outstanding=[], sufficient=False,
                missing=[f"{alias} names {len(named)} durable Participants; "
                         "say which by reference, because picking one here "
                         "would be a guess about who this is"],
                sources=list(named))
        participant = named[0] if named else None
    if participant is None:
        return Reconstruction(
            who={"alias": alias, "participant": None}, where={"kind": "unknown"},
            persona=None, completed=[], outstanding=[], sufficient=False,
            missing=["no durable Participant with that alias"], sources=[])
    sources.append(participant)

    where = {"kind": "brain"}
    if conversation is None:
        joined = cv.conversations_of(participant)
        conversation = joined[0] if len(joined) == 1 else None
    if conversation is not None:
        conv = cv.conversation_now(conversation) or \
            corpus.read([conversation])[0]
        where = {"kind": "conversation", "conversation": conversation,
                 "name": conv["body"]["name"], "about": conv["body"]["about"]}
        sources.append(conversation)

    persona, ended_persona = None, None
    for d in reversed(corpus.deliveries(participant=participant)):
        for s in d["behavioural_sources"]:
            if s["source_kind"] != "persona" or not s["source_id"]:
                continue
            # WHAT WAS DELIVERED IS HISTORY; WHAT APPLIES NOW IS STANDING.
            # This took the most recent delivery that named a Persona and
            # rendered it as `Behaving as ...`, so a Persona that had since
            # been superseded came back as current operating behaviour --
            # this is a context for FRESH work, so ended behaviour must not
            # be handed to it as though it still held.
            if not corpus.stands(s["source_id"])["stands"]:
                ended_persona = ended_persona or s["source_id"]
                continue
            p = corpus.read([s["source_id"]])[0]
            persona = {"id": s["source_id"], "name": p["body"]["name"],
                       "behaviour": p["body"]["behaviour"]}
            sources.append(s["source_id"])
            break
        if persona:
            break
    if persona is None:
        missing.append(
            "the Persona this name last operated as no longer stands, so "
            "it is not carried into fresh work" if ended_persona else
            "no delivery evidence records which Persona it was using")

    completed, outstanding = [], []
    if conversation is not None:
        for c in sorted(cv.contributions(conversation),
                        key=lambda e: e["recorded_at"]):
            said = " ".join(p.get("text", "") for p in c["body"]["parts"])
            if c["attributed_to"] == participant:
                completed.append({"id": c["id"], "text": said})
                sources.append(c["id"])
        for a in cv.awaiting_response(conversation):
            item = corpus.read([a["contribution"]])[0]
            outstanding.append({"id": a["contribution"],
                                "text": " ".join(p.get("text", "")
                                                 for p in item["body"]["parts"])})
            sources.append(a["contribution"])
        if not completed and not outstanding:
            missing.append("nothing durable records what it did or what is left")
    else:
        missing.append("no conversation context; brain scope assumed")

    return Reconstruction(
        who={"alias": alias, "participant": participant}, where=where,
        persona=persona, completed=completed, outstanding=outstanding,
        sufficient=not missing, missing=missing, sources=sources)
