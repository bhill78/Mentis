"""Changing the Workflow that governs a request while the work is under way.

WHY THIS EXISTS. A request is named with a Workflow when it is asked
(`posting.owe`, `governed`), and the work then learns things: a bug turns out to
be a gap in the requirements, research turns into an approved build. The
Workflow it was asked with stops describing the work. Until now the only way
to say so was a NEW request continuing the old one (`carried_workflows`); the
active request itself kept the Workflow it started with.

HOW, WITH WHAT ALREADY EXISTS. A change is one more `expectation-assigned` act
under the request, carrying `governed` -- the act every reader of "what this
request is governed by" already resolves newest-first
(`Conversations.governed_named`, `dispatch._governed_for`). So the next run of
the request, first or resumed, is composed and condensed against the new
Workflow by the dispatch that already exists, and nothing else learns a new
rule. The act NAMES NO CARRIER (`about` is empty): every reader of who carries
a request (`assigned_carrier`, `_carriers`, `imported._carrier_here`) already
counts only assignments that name somebody, so a change of Workflow is never
mistaken for a change of hands.

WHAT IS KEPT. The append-only record keeps the request's own `governed`, every
earlier change, and every result, delegation and decision under the work;
`history` reads them back in order. Nothing is rewritten.

WHAT IT IS NOT. Not a Workflow engine: no stage, no position, no rule decides a
change. A person decides it -- the owner, or the carrier by its own judgment
under the authority the request already has -- and says why and on what
evidence. A Workflow grants nothing (the Kind says so), so changing one grants
nothing either: grants, run consent, Task Gravity and the request's reach are
read from where they always were, and this writes none of them.
"""

from __future__ import annotations

#: The key on the assignment act that marks it a Workflow change, beside the
#: `governed` it resolves through.
CHANGE = "workflow_change"

#: Who made the change, as the act records it.
OWNER, CARRIER = "owner", "carrier"

#: How long a reason may be; a reason is a sentence or two, not the evidence.
REASON_LIMIT = 2000
EVIDENCE_LIMIT = 20


class Refused(ValueError):
    """The change was refused and nothing was written. The message says why."""


def _is_workflow(cv, entry) -> bool:
    from mentis.conversation import ROW_GROUP, fields_with_input
    kind = (entry.get("definition") or {}).get("name")
    return bool(kind and fields_with_input(cv.corpus, kind, ROW_GROUP))


def workflows_of(cv, refs) -> list[str]:
    """The Workflow-kind references among `refs`, in order."""
    out = []
    for ref in refs or ():
        got = cv.corpus.read([ref]) if isinstance(ref, str) and ref else []
        if got and _is_workflow(cv, got[0]) and ref not in out:
            out.append(ref)
    return out


def _standing_workflow(cv, ref) -> str:
    """The standing Workflow `ref` means: an id followed forward along its
    supersession line, or an exact standing name. Refused otherwise."""
    from mentis.conversation import current_of
    ref = str(ref or "").strip()
    if not ref:
        raise Refused("name the Workflow to change to")
    if ref.startswith("ent-"):
        got = cv.corpus.read([ref])
        if not got:
            raise Refused(f"{ref!r} is not something this record holds")
        if not _is_workflow(cv, got[0]):
            raise Refused(f"{ref!r} is not a Workflow")
        cur = current_of(cv.corpus, ref)
        if not cur["stands"]:
            raise Refused(f"{ref!r} does not stand ({cur['why']}); nothing "
                          f"that does not stand governs work")
        return cur["entry"]
    found = [e["id"] for e in cv.corpus.entries_of_kind("workflow")
             if (e.get("body") or {}).get("name") == ref
             and cv.corpus.stands(e["id"])["stands"]]
    if len(found) != 1:
        raise Refused(f"{len(found)} standing Workflows are named {ref!r}"
                      + (f" ({', '.join(found)}); name one by id" if found
                         else ""))
    return found[0]


def _evidence(cv, evidence) -> list[str]:
    """The evidence references, each one the record holds. At least one."""
    refs = []
    for x in evidence or ():
        x = str(x or "").strip()
        if x and x not in refs:
            refs.append(x)
    if not refs:
        raise Refused("a Workflow change needs evidence: the reference of at "
                      "least one finding, result, decision or post it rests on")
    if len(refs) > EVIDENCE_LIMIT:
        raise Refused(f"at most {EVIDENCE_LIMIT} evidence references")
    for ref in refs:
        held = (cv.corpus.read([ref]) if ref.startswith("ent-")
                else [cv._act(ref)] if ref.startswith("opr-") else [])
        if not held or not held[0]:
            raise Refused(f"{ref!r} is not something this record holds "
                          f"(evidence is an ent- or opr- reference)")
    return refs


def _repository_admitted(projects, repository) -> bool:
    """Whether a Workflow's `projects` admit the request's repository: by its
    full path or its folder name, ignoring case. No projects admits any."""
    import ntpath
    import posixpath
    names = [str(p).strip().lower() for p in projects or () if str(p).strip()]
    if not names or not repository:
        return True
    repo = str(repository).strip().rstrip("\\/").lower()
    base = ntpath.basename(repo) or posixpath.basename(repo)
    return repo in names or base in names


def check(cv, expectation, workflow, *, because, evidence, role) -> dict:
    """Everything a change must satisfy, whoever makes it. Writes nothing.

    Returns what `record` writes: the request, the Workflow ids it is governed
    by now and will be, the full `governed` list after the change (material
    named for the request that is not a Workflow -- a Discipline, a rule --
    stays), the reason and the evidence. Raises `Refused`.

    The request must be a piece of work in its own right (a trunk: not a
    decision, not a delegated child, whose step is its parent's to give), and
    not already met. A carrier is further held to the request's scope: the
    Workflow's `projects`, where it names any, must admit the repository the
    request declared. The owner is not; the owner decides the scope.
    """
    from mentis.operational.work import is_trunk
    act = cv._act(expectation)
    if act is None or act.get("act") != "expectation-recorded":
        raise Refused(f"{expectation!r} is not a request in this record")
    if not is_trunk(cv, act):
        raise Refused(
            f"{expectation!r} is not a piece of work in its own right (a "
            f"decision, an input, or a delegated step); its Workflow is the "
            f"work it was asked under")
    state = cv.expectation_state(expectation)
    if state.get("satisfied_by"):
        raise Refused(f"{expectation!r} is already met; a Workflow change is "
                      f"for work that is still under way")
    reason = str(because or "").strip()
    if not reason:
        raise Refused("say why the Workflow changes (`because`)")
    if len(reason) > REASON_LIMIT:
        raise Refused(f"the reason is longer than {REASON_LIMIT} characters; "
                      f"put the detail in the evidence it cites")
    refs = _evidence(cv, evidence)
    target = _standing_workflow(cv, workflow)
    named = cv.governed_named(expectation)
    before = workflows_of(cv, named)
    if before == [target]:
        raise Refused(f"{expectation!r} is already governed by {target}")
    if role == CARRIER:
        from mentis.web.dispatch import declared
        body = (cv.corpus.read([target])[0].get("body") or {})
        repository = declared(cv, expectation)
        # A DECLARED DIRECTORY, in either form a request records it: a path,
        # or `{"path": ...}` / `{"base": ...}`. A review request declares what
        # it reviews (`review_of`), not a directory, and is not held to it.
        if isinstance(repository, dict):
            repository = repository.get("path") or repository.get("base")
        if isinstance(repository, str) and not _repository_admitted(
                body.get("projects"), repository):
            raise Refused(
                f"{target} is written for {body.get('projects')}, and this "
                f"request declared {repository!r}. Changing to it would take "
                f"the work outside the scope it was asked in; ask the owner "
                f"(request_decision)")
        # SOMETHING LEARNED, NOT THE ASK RESTATED: a carrier changing the
        # Workflow on its own authority cites a finding, result, decision or
        # post beyond the request's own post and record. The owner's word is
        # its own evidence; a carrier's is not (found by independent review).
        if not [r for r in refs if r not in (expectation, act.get("turn"))]:
            raise Refused(
                "a carrier's Workflow change cites evidence beyond the request "
                "itself: the finding, result or decision that shows the work "
                "is now something else")
    others = [g for g in named if g not in before]
    return {"expectation": expectation, "from": before, "to": [target],
            "governed": [*others, target], "because": reason,
            "evidence": refs, "role": role}


def record(cv, change, *, by, execution=None, runtime=None) -> str:
    """Write a checked change: one `expectation-assigned` act naming no
    carrier, carrying `governed` and the change itself. Returns its id."""
    act = cv._act(change["expectation"])
    return cv.record_act(
        actor=by, act="expectation-assigned",
        conversation=act["conversation"], turn=act["turn"],
        execution=execution, runtime=runtime,
        because=change["because"], caused_by=change["expectation"], about=[],
        detail={"governed": list(change["governed"]),
                CHANGE: {"from": list(change["from"]), "to": list(change["to"]),
                         "evidence": list(change["evidence"]),
                         "role": change["role"],
                         # SAID ON THE ACT, so nobody reading it later takes a
                         # Workflow change for a widening of authority.
                         "grants": "nothing: authority, consent, Task Gravity "
                                   "and reach are unchanged",
                         # AND HELD TO IT: what the work could do when its
                         # Workflow changed. Dispatch refuses a later run whose
                         # authority is wider than this unless the owner
                         # widened it since (`authority_widened`).
                         "authority": authority_snapshot(
                             cv, change["expectation"])}})


def history(cv, expectation) -> dict:
    """Which Workflow governs this request now, where that came from, and
    every change in order. Read from the record; nothing is stored.

        current   [{entry, name}] the Workflows the request is governed by now
        origin    how the current Workflow came to govern it:
                  "named" (asked with it), "continued" (carried from the
                  request it continues), "changed" (by the latest change),
                  "placed" (none named; one placed where it runs), or "none"
        history   [{kind: "asked" | "changed", at, by, by_alias, ...}]
    """
    def name(ref):
        got = cv.corpus.read([ref]) if ref else []
        return ((got[0].get("body") or {}).get("name") or None) if got else None

    def named(refs):
        return [{"entry": r, "name": name(r)} for r in refs]

    act = cv._act(expectation) or {}
    detail = act.get("detail") or {}
    asked = workflows_of(cv, detail.get("governed") or ())
    events = [{"kind": "asked", "at": act.get("at"), "by": act.get("actor"),
               "by_alias": cv.alias(act["actor"]) if act.get("actor") else None,
               "workflows": named(asked),
               "from": detail.get("governed_from") or (
                   "named" if asked else None),
               "continues": detail.get("governed_continues")}]
    changes = sorted((a for a in cv.history(caused_by=expectation)
                      if a["act"] == "expectation-assigned"
                      and CHANGE in (a.get("detail") or {})),
                     key=lambda a: a["at"])
    for a in changes:
        c = a["detail"][CHANGE]
        events.append({
            "kind": "changed", "act": a["id"], "at": a["at"],
            "by": a["actor"], "by_alias": cv.alias(a["actor"]),
            "role": c.get("role"), "because": a.get("because"),
            "from": named(c.get("from") or ()), "to": named(c.get("to") or ()),
            "evidence": [{"ref": r, **_evidence_label(cv, r)}
                         for r in c.get("evidence") or ()],
            "runtime": a.get("runtime"), "execution": a.get("execution")})
    current = workflows_of(cv, cv.governed_named(expectation))
    if current and changes and workflows_of(
            cv, changes[-1]["detail"].get("governed") or ()) == current:
        origin = "changed"
    elif current:
        origin = "continued" if detail.get("governed_from") == "continued" \
            else "named"
    else:
        placed = sorted(e for e in cv.governing_now(act.get("conversation"),
                                                    (), None)
                        if workflows_of(cv, [e]))
        current, origin = (placed, "placed") if placed else ([], "none")
    return {"current": named(current), "origin": origin, "history": events}


def _evidence_label(cv, ref) -> dict:
    """What a reader is shown for an evidence reference: its post number and
    Conversation where it is a Turn or an act on one."""
    try:
        if ref.startswith("opr-"):
            a = cv._act(ref) or {}
            turn = a.get("turn")
            return {"act": a.get("act"), "turn": turn,
                    "number": cv.turn_number(turn) if turn else None,
                    "conversation": a.get("conversation")}
        number = cv.turn_number(ref)
        return {"turn": ref if number is not None else None, "number": number}
    except Exception:                                     # noqa: BLE001
        return {}


# -- execution authority is not the Workflow's ---------------------------------
#
# OWNER RULING 2026-10-29: changing a Workflow never expands execution
# authority; a move from Research to Software change authorises no
# implementation that was not already authorised, and that is enforced where
# work is executed, not only said to the agent. Execution authority is decided
# from the owner's records alone -- the request's granted operations
# (`authority_of`), its run consent (`consent.of_request`: mode, workspaces,
# categories, web research) and its Task Gravity -- and the permission policy
# reads nothing else. These functions hold that line at dispatch: a change
# records what the work could do at that moment, and a later run of the
# request whose authority is wider is refused before anything starts, unless
# the owner has acted on the work since the change.

#: How far each consent mode lets work proceed without the owner. `deny` and
#: `task` both proceed with routine work in the approved workspaces; they
#: differ in whether the rest is refused or asked, which widens nothing.
_MODE_REACH = {"ask": 0, "deny": 1, "task": 1, "all": 2}


def authority_snapshot(cv, expectation) -> dict:
    """What the work may do now, from the owner's records only."""
    from mentis.operational import discovery, follow_up_of
    from mentis.operational import consent as _consent
    got = cv.authority_of(expectation)
    c = _consent.of_request(cv, expectation)
    try:
        follow = follow_up_of(cv, discovery(cv, expectation)["origin"])
    except Exception:                                     # noqa: BLE001
        follow = None
    return {"operations": sorted(got.get("operations") or ()),
            "consent": {"mode": c.get("mode"),
                        "workspaces": sorted(c.get("workspaces") or ()),
                        "categories": sorted(c.get("categories") or ()),
                        "research": bool((c.get("research") or {})
                                         .get("authorized"))},
            "follow_up": follow}


def _follow_reach(value) -> float:
    if value in (None, "ask"):
        return 0
    if value == "unrestricted":
        return float("inf")
    if isinstance(value, dict):
        return float(value.get("depth") or 0)
    return 0


def _wider(before, now) -> list[str]:
    """Every way `now` lets the work do more than `before`, in words."""
    from mentis.operations import inside
    out = []
    added = sorted(set(now["operations"]) - set(before["operations"]))
    if added:
        out.append(f"organising operations {added}")
    b, n = before["consent"], now["consent"]
    if _MODE_REACH.get(n["mode"], 0) > _MODE_REACH.get(b["mode"], 0):
        out.append(f"consent {b['mode']} -> {n['mode']}")
    reach = _MODE_REACH.get(n["mode"], 0)
    cats = sorted(set(n["categories"]) - set(b["categories"]))
    if cats and reach:
        out.append(f"consent categories {cats}")
    ws = [w for w in n["workspaces"]
          if not any(inside(w, x) for x in b["workspaces"])]
    if ws and reach:
        out.append(f"workspaces {ws}")
    if n["research"] and not b["research"]:
        out.append("web research")
    if _follow_reach(now["follow_up"]) > _follow_reach(before["follow_up"]):
        out.append(f"follow-up {before['follow_up']!r} -> {now['follow_up']!r}")
    return out


def _owner_authorised_since(cv, expectation, at) -> bool:
    """Whether the owner, after `at`, said what this work may do: set its
    consent (`consent-set`), granted it authority (`authority-granted`), or
    changed its Workflow themselves -- on this request or one above it. Only
    these: answering a question or posting under the work says nothing about
    what it may do (found by independent review)."""
    from mentis.conversation.owner import _owner
    from mentis.operational.consent import SET, _lineage
    owner = _owner(cv)
    if not owner:
        return False
    for level in _lineage(cv, expectation):
        for a in cv._c.operational(caused_by=level["id"]):
            if a.get("actor") != owner or (a.get("at") or 0) <= at:
                continue
            d = a.get("detail") or {}
            if (a["act"] in (SET, "authority-granted")
                    or (CHANGE in d and (d[CHANGE] or {}).get("role") == OWNER)):
                return True
    return False


def _changes(cv, expectation) -> list[dict]:
    return sorted((a for a in cv.history(caused_by=expectation)
                   if a["act"] == "expectation-assigned"
                   and CHANGE in (a.get("detail") or {})),
                  key=lambda a: a["at"])


def pending_carrier_change(cv, expectation) -> dict | None:
    """The carrier's Workflow change the owner has not yet authorised past,
    on this request or a request above it, or None.

    WHILE ONE IS PENDING, WHAT THE WORK MAY MODIFY IS ONLY WHAT THE OWNER
    EXPLICITLY CONSENTED TO. A Workflow change never authorises
    implementation (owner ruling 2026-10-29), so the run's implicit allowance
    to edit files in its own workspace (`permissions.standing_answer`) does
    not apply: an edit proceeds only under the consent the owner gave (routine
    work in approved workspaces), is asked of them under `ask`, and refused
    under `deny`. It ends when the owner sets consent, grants authority or
    changes the Workflow themselves (`_owner_authorised_since`)."""
    from mentis.operational.consent import _lineage
    for level in _lineage(cv, expectation):
        carrier = [a for a in _changes(cv, level["id"])
                   if (a["detail"][CHANGE] or {}).get("role") == CARRIER]
        if carrier and not _owner_authorised_since(cv, level["id"],
                                                   carrier[-1]["at"]):
            return carrier[-1]
    return None


def authority_widened(cv, expectation) -> str | None:
    """Why a run of this request must not start, or None.

    None unless the request's Workflow was changed. Then: the authority the
    run would be given is compared with what the work could do when its
    Workflow last changed; anything wider that no owner act since explains is
    a widening the change would have brought, and the run is refused."""
    changes = [a for a in _changes(cv, expectation)
               if (a["detail"][CHANGE] or {}).get("authority")]
    if not changes:
        return None
    # THE BASELINE IS THE FIRST CHANGE SINCE THE OWNER LAST SAID WHAT THE WORK
    # MAY DO: a later change records whatever stood then, so comparing with the
    # last one would let a second change carry a widening forward.
    since = [a for a in changes
             if not _owner_authorised_since(cv, expectation, a["at"])]
    if not since:
        return None
    last = since[0]
    wider = _wider(last["detail"][CHANGE]["authority"],
                   authority_snapshot(cv, expectation))
    if not wider:
        return None
    return (f"this request's Workflow was changed ({last['id']}), and the run "
            f"would now be allowed more than the work could do then: "
            f"{'; '.join(wider)}. A Workflow change never widens what work may "
            f"do; only the owner can, and nothing the owner recorded since "
            f"the change says so")


def changeable(cv, expectation) -> dict:
    """Whether the owner's change can succeed here, and why not: the
    conditions `check` holds before a Workflow or evidence is chosen -- a
    piece of work in its own right, not met, with an owner on record and
    another standing Workflow to change to."""
    from mentis.conversation.owner import _owner
    from mentis.operational.work import is_trunk
    act = cv._act(expectation)
    if act is None or act.get("act") != "expectation-recorded":
        return {"owner": False, "why": "not a request"}
    if not _owner(cv):
        return {"owner": False, "why": "this record names no owner"}
    if not is_trunk(cv, act):
        return {"owner": False,
                "why": "a decision, an input or a delegated step: its Workflow "
                       "is the work it was asked under"}
    if cv.expectation_state(expectation).get("satisfied_by"):
        return {"owner": False, "why": "the work is met"}
    current = set(workflows_of(cv, cv.governed_named(expectation)))
    others = [e for e in cv.corpus.entries_of_kind("workflow")
              if e["id"] not in current and cv.corpus.stands(e["id"])["stands"]]
    # Governed by several, changing to one of them is a change too (`check`).
    if not others and len(current) < 2:
        return {"owner": False, "why": "no other standing Workflow to change to"}
    return {"owner": True, "why": None}


def authority_line(cv, expectation) -> str | None:
    """What a run of a request whose Workflow changed is told about it, from
    the record: which change, and that it authorised nothing. None when the
    Workflow never changed. Information for the agent; the enforcement is
    `authority_widened` at dispatch and the permission policy."""
    changes = _changes(cv, expectation)
    if not changes:
        return None
    last = changes[-1]
    c = last["detail"][CHANGE]

    def names(refs):
        out = []
        for r in refs or ():
            got = cv.corpus.read([r])
            out.append(((got[0].get("body") or {}).get("name") if got else None)
                       or r)
        return ", ".join(out) or "none"
    from mentis.operational import consent as _consent
    label = _consent.of_request(cv, expectation).get("label")
    held = (" Until the owner says otherwise, editing files is limited to "
            "what they consented to: an edit outside it is asked of them, or "
            "refused under deny." if pending_carrier_change(cv, expectation)
            else "")
    return (f"This request's Workflow was changed from {names(c.get('from'))} "
            f"to {names(c.get('to'))} by {cv.alias(last['actor'])} "
            f"({c.get('role')}): {last.get('because') or 'no reason recorded'}"
            f". The change authorises nothing. What this work may do is what "
            f"it could before ({label}), and Mentis will not run it with "
            f"more.{held} Work the owner has not asked for is still theirs to "
            f"approve (request_decision).")
