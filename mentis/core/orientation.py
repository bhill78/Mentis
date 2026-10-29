"""Prepared orientation: foundation and agent-specific context.

Operating model contract §5 and §6.

- `foundation(brain, conversation, *, scope)` is shared across agents in the
  conversation with the same scope, cached under:
  deps: `governance`, `conversation:<id>`, `work`, `participants`.
- `for_agent(brain, foundation, *, participant, ...)` is the agent-specific
  part (persona, workflow, condensed disciplines, task gravity, recall),
  cached under: deps add `knowledge`.
"""

from __future__ import annotations

import hashlib
from typing import Any

from mentis.conversation import first_line
from mentis.core.context_cache import cache_for, revisions_for
from mentis.operational import (
    ASK,
    UNRESTRICTED,
    discovery,
    follow_up_of,
    follow_up_value,
)


def _get_entry(cv, eid: str | None) -> dict | None:
    if not eid or not isinstance(eid, str):
        return None
    got = cv._entry(eid)
    if isinstance(got, list):
        return got[0] if got else None
    if isinstance(got, dict):
        return got
    return None


def _entry_in_full(corpus, eid: str | None) -> dict | None:
    if not eid or not isinstance(eid, str):
        return None
    from mentis.conversation import content_of, rendering_of
    from mentis.conversation.versions import presented

    got = corpus.read([eid])
    if not got:
        return None
    item = presented(corpus, got[0])
    kind = (item.get("definition") or {}).get("name")
    fields, form = rendering_of(corpus, kind)
    body = item.get("body") or {}
    text = content_of(item, fields, form)
    return {
        "id": eid,
        "kind": kind,
        "name": body.get("name") or eid,
        "about": body.get("about", ""),
        "text": text,
        "body": body,
    }


def foundation(brain: Any, conversation: str, *, scope: str) -> dict:
    """Shared orientation foundation for a conversation under an access scope.

    Built ONLY from existing reads: Conversations.orientation, governs,
    placed_procedural, operational.work_overview, Conversations.owner_decisions.
    Deps: governance, conversation:<id>, work, participants.
    """
    cv = brain.conversations
    corpus = getattr(brain, "corpus", None) or getattr(brain, "primary", None) or cv.corpus()
    cid = conversation.strip()

    deps = frozenset(
        {"governance", f"conversation:{cid}", "work", "participants"}
    )
    cache = cache_for(corpus)
    rev_token = revisions_for(corpus).token(deps)
    key = (
        "foundation",
        corpus.corpus_id,
        rev_token,
        cid,
        None,
        None,
        scope,
    )

    def compute() -> dict:
        # 1. Identity and purpose
        conv_entry = _get_entry(cv, cid)
        body = (conv_entry.get("body") if conv_entry else {}) or {}
        name = body.get("name") or cid
        about = body.get("about") or ""

        # 2. Participants and the Personas worn there
        participants = []
        for p in cv.participants(cid):
            pid = p["id"] if isinstance(p, dict) else str(p)
            alias = cv.alias(pid)
            persona = None
            if hasattr(cv, "persona_of"):
                persona = cv.persona_of(pid)
            if not persona and isinstance(p, dict):
                persona = (p.get("body") or {}).get("persona")
            if not persona:
                acts = corpus.operational(
                    actor=pid,
                    conversation=cid,
                    act="execution-started",
                    limit=1,
                    newest_first=True,
                )
                if acts:
                    persona = (acts[0].get("detail") or {}).get("persona")
            participants.append({"id": pid, "alias": alias, "persona": persona})

        # 3. Outstanding work and open owner decisions (ids + titles)
        from mentis.operational import work_overview as wo

        overview = wo.overview(
            cv,
            viewer=wo.owner_of(cv),
            conversation=cid,
            runtime={"runs": None, "why_not": "orientation read"},
        )
        outstanding = [
            {"id": i["expectation"], "title": i.get("title") or i["expectation"]}
            for i in overview.get("items", [])
            if i.get("objective_met") is not True
        ]

        decisions = cv.owner_decisions(cid)
        open_decisions = [
            {"id": d["expectation"], "title": d.get("question") or d["expectation"]}
            for d in decisions.get("open", [])
        ]

        # 4. Applicable Workflows and Disciplines as condensed references
        # 5. Standing governance (ids, titles, delivery level)
        gov_res = cv.governs(cid)
        gov_rows = gov_res.get("governing", [])
        applicable_workflows = []
        applicable_disciplines = []
        standing_governance = []

        for r in gov_rows:
            eid = r["entry"]
            entry_dict = _get_entry(cv, eid)
            kind = cv._kind_of(entry_dict) if entry_dict else r.get("kind")
            title = first_line(
                r.get("text")
                or r.get("about")
                or (entry_dict.get("body", {}).get("name") if entry_dict else None)
                or eid
            )
            # WHAT THE OWNER SAID AT PLACEMENT (Governance Condensation);
            # absent is full, as every placement was before delivery levels.
            placed_as = cv.placement_delivery(eid, cid) or {}
            delivery = placed_as.get("delivery") or "full"
            scope_list = list(r.get("placed") or ())
            standing_governance.append(
                {"id": eid, "title": title, "delivery": delivery, "scope": scope_list}
            )

            ref_row = {
                "id": eid,
                "kind": kind,
                "title": title,
                "delivery": "reference",
            }
            if kind == "workflow":
                applicable_workflows.append(ref_row)
            elif kind == "discipline":
                applicable_disciplines.append(ref_row)

        # 6. Recent-context pointers (last N Turn ids + first lines)
        recent_turns = []
        contribs = sorted(
            cv.contributions(cid), key=lambda e: e.get("recorded_at", 0)
        )
        for c in contribs[-5:]:
            text_str = ""
            for p in (c.get("body", {}).get("parts") or []):
                if p.get("type") == "text":
                    text_str += p.get("text", "") + " "
            recent_turns.append(
                {"id": c["id"], "summary": first_line(text_str.strip(), 120)}
            )

        return {
            "conversation": cid,
            "name": name,
            "about": about,
            "scope": scope,
            "participants": participants,
            "outstanding_work": outstanding,
            "open_owner_decisions": open_decisions,
            "applicable_workflows": applicable_workflows,
            "applicable_disciplines": applicable_disciplines,
            "standing_governance": standing_governance,
            "recent_context": recent_turns,
        }

    return cache.get(key, compute, deps=deps)


def for_agent(
    brain: Any,
    foundation: dict,
    *,
    participant: str,
    persona: str | None = None,
    work: str | None = None,
    workflow: str | None = None,
    follow_up: Any = None,
    expectation: str | None = None,
) -> dict:
    """The agent's own part of the prepared orientation. Never shared across
    Personas, work, grants or Participants: all of them are in its key.

    ONE COMPOSITION, THE ONE A DISPATCHED RUN IS GIVEN. `Conversations.compose`
    with the Persona worn and the Workflow named for the work, so what the
    Persona carries arrives with it and supersession was resolved before any
    of this saw it; then condensed (`mentis.conversation.condense`): the Persona
    and the named Workflow in full, placed material at the level its placement
    says, a condition the work is known to meet in full. `persona` and
    `workflow` are ids the caller has already resolved to standing entries
    (`mentis.worker.standing_material`).
    """
    from mentis.conversation.condense import condense, render
    from mentis.operational import follow_up_label

    cv = brain.conversations
    corpus = getattr(brain, "corpus", None) or getattr(brain, "primary", None) or cv.corpus()
    cid = foundation["conversation"]
    scope = foundation.get("scope", "brain")
    deps = frozenset({"governance", f"conversation:{cid}", "work",
                      "participants", "knowledge"})
    cache = cache_for(corpus)
    rev_token = revisions_for(corpus).token(deps)
    task_digest = (
        hashlib.sha256(work.encode("utf-8")).hexdigest()[:16] if work else None
    )
    key = ("for_agent", corpus.corpus_id, rev_token, cid, task_digest, persona,
           (scope, participant, workflow, expectation, repr(follow_up)))

    def compute() -> dict:
        comp = cv.compose(conversation=cid, participant=participant,
                          persona=persona,
                          behavioural=[workflow] if workflow else (),
                          question=work)
        deliveries = condense(corpus, comp, question=work)
        # WHAT GOVERNS AND WHAT THE BRAIN KNOWS ABOUT THE WORK: every tier the
        # composition delivers, in its own order (governing, then the request's
        # knowledge -- adopted, then experience). The orientation and the
        # request are left out: the foundation already says the one, and the
        # caller already holds the other.
        governing = [d for d in deliveries
                     if d.component.tier in ("governing", "adopted", "experience")
                     or d.component.scope == "invocation:persona"]
        # THE TASK GRAVITY IN FORCE: the original request's, read by the same
        # walk pickup is decided by (`discovery`, `follow_up_of`).
        given = follow_up
        generation = 0
        if expectation:
            disc = discovery(cv, expectation)
            generation = disc.get("generation", 0)
            if given is None:
                given = follow_up_of(cv, disc.get("origin"))
        try:
            setting = follow_up_value(given) if given is not None else ASK
        except ValueError:
            setting = ASK
        may_pursue_next = (setting == UNRESTRICTED or (
            isinstance(setting, dict) and generation + 1 <= setting["depth"]))
        return {
            "for": participant,
            "persona": persona,
            "workflow": workflow,
            "delivered": render(governing),
            "levels": [{"id": d.component.source_id,
                        "kind": d.component.source_kind,
                        "scope": d.component.scope, "level": d.level,
                        "condition": d.condition, "why": d.why}
                       for d in governing],
            "withheld": list(comp.withheld),
            "task_gravity": {"setting": setting,
                             "label": follow_up_label(setting),
                             "generation": generation,
                             "may_pursue_next": may_pursue_next},
        }

    return cache.get(key, compute, deps=deps)


def _brain_wide(row) -> bool:
    """Placed on the whole Brain and not at this Conversation as well."""
    placed = [str(p) for p in (row.get("scope") or ())]
    return bool(placed) and all("whole" in p for p in placed)


def blocks(shared: dict, mine: dict) -> list[dict]:
    """The prepared orientation as three blocks, MOST STABLE FIRST.

    WHY BLOCKS, AND WHY THIS ORDER (borrowed from how OpenHands builds its
    system prompt: a static block shared across conversations, then a
    per-conversation block, volatile values last). Whatever an agent is given
    becomes the front of its prompt, and a model runtime reuses a prefix only
    while it is byte-identical. So:

      brain        standing material placed on the whole Brain -- the core
                   operating material. The same text in every Conversation;
                   it moves only when the owner changes governance.
      conversation this Conversation's own governance and guidance, who is
                   here, then the work outstanding and recent posts (the parts
                   that move with the work come last).
      agent        this caller's part: Task Gravity, then what it is given in
                   full or by condition (Persona, Workflow, Disciplines).

    Every agent in the Conversation shares the first two blocks exactly. Lists
    are in a fixed order and nothing says when it was computed. `digest` lets a
    client see whether a prefix it holds is still the current one; Mentis
    places no cache markers itself -- the runtime owns its prompt."""
    import hashlib as _h
    gov = sorted(shared.get("standing_governance") or (), key=lambda r: r["id"])

    def line(g):
        return f"- {g['id']} [{g.get('delivery') or 'full'}] {g.get('title')}"

    brain = ["# Standing on the whole Brain"]
    brain.extend(line(g) for g in gov if _brain_wide(g))
    conv = [f"# Conversation: {shared.get('name')}"]
    if shared.get("about"):
        conv.append(shared["about"])
    here = [line(g) for g in gov if not _brain_wide(g)]
    if here:
        conv.append("\n## Standing governance here")
        conv.extend(here)
    for label, rows in (("Workflows that apply (by reference)",
                         shared.get("applicable_workflows")),
                        ("Disciplines that apply (by reference)",
                         shared.get("applicable_disciplines"))):
        if rows:
            conv.append(f"\n## {label}")
            conv.extend(f"- {r['id']} {r.get('title')}"
                        for r in sorted(rows, key=lambda r: r["id"]))
    conv.append("\n## Participants")
    conv.extend(f"- {p.get('alias') or p['id']}"
                + (f" (as Persona {p['persona']})" if p.get("persona") else "")
                for p in sorted(shared.get("participants") or (),
                                key=lambda p: p["id"]))
    if shared.get("outstanding_work"):
        conv.append("\n## Outstanding work")
        conv.extend(f"- {w['id']} {w.get('title')}"
                    for w in shared["outstanding_work"])
    if shared.get("open_owner_decisions"):
        conv.append("\n## Open owner decisions")
        conv.extend(f"- {d['id']} {d.get('title')}"
                    for d in shared["open_owner_decisions"])
    if shared.get("recent_context"):
        conv.append("\n## Recent posts")
        conv.extend(f"- {r['id']} {r.get('summary')}"
                    for r in shared["recent_context"])
    gravity = mine.get("task_gravity") or {}
    agent = ["# For you",
             f"Task Gravity for this run: {gravity.get('label')} "
             f"(this work is generation {gravity.get('generation', 0)})."]
    if mine.get("delivered"):
        agent += ["", mine["delivered"]]
    out = []
    for tier, text_lines in (("brain", brain), ("conversation", conv),
                             ("agent", agent)):
        text = "\n".join(text_lines)
        out.append({"tier": tier, "text": text,
                    "digest": _h.sha256(text.encode("utf-8")).hexdigest()[:16]})
    return out


def render(shared: dict, mine: dict) -> str:
    """The three blocks as one text, in their order (`blocks`)."""
    return "\n\n---\n\n".join(b["text"] for b in blocks(shared, mine))
