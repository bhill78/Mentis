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
            delivery = r.get("delivery", "full")
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
    """Agent-specific orientation context, never shared across personas/tasks.

    - Persona in full
    - Named workflow in full
    - Disciplines condensed per §3 with question=work
    - Task gravity in force (§6) with its generation
    - recall(work) tiers
    Deps: foundation deps + knowledge.
    """
    cv = brain.conversations
    corpus = getattr(brain, "corpus", None) or getattr(brain, "primary", None) or cv.corpus()
    cid = foundation["conversation"]
    scope = foundation.get("scope", "brain")

    deps = frozenset(
        {
            "governance",
            f"conversation:{cid}",
            "work",
            "participants",
            "knowledge",
        }
    )
    cache = cache_for(corpus)
    rev_token = revisions_for(corpus).token(deps)
    task_digest = (
        hashlib.sha256(work.encode("utf-8")).hexdigest()[:16] if work else None
    )
    key = (
        "for_agent",
        corpus.corpus_id,
        rev_token,
        cid,
        task_digest,
        persona,
        (scope, participant, workflow, expectation),
    )

    def compute() -> dict:
        # 1. Persona in full
        persona_full = _entry_in_full(corpus, persona) if persona else None

        # 2. Named Workflow in full
        workflow_full = _entry_in_full(corpus, workflow) if workflow else None

        # 3. Disciplines condensed per §3 with question=work
        comp = cv.compose(
            conversation=cid, participant=participant, question=work
        )
        try:
            # Condense module is built in parallel by another agent; import lazily
            from mentis.conversation.condense import condense, render

            deliveries = condense(corpus, comp, question=work)
            disciplines_condensed = render(deliveries)
        except ImportError:
            # Fallback to Composition.payload() when condense is absent
            disciplines_condensed = comp.payload()

        # 4. Task Gravity in force (§6) with its generation
        nonlocal follow_up
        if expectation:
            disc = discovery(cv, expectation)
            gen = disc.get("generation", 0)
            if follow_up is None:
                follow_up = follow_up_of(cv, disc.get("origin"))
        else:
            gen = 0

        try:
            setting = (
                follow_up_value(follow_up) if follow_up is not None else ASK
            )
        except ValueError:
            setting = ASK

        if setting == ASK:
            label = "Asks before pursuing side work"
            may_pursue_next = False
        elif setting == UNRESTRICTED:
            label = "May pursue side work freely"
            may_pursue_next = True
        elif isinstance(setting, dict) and "depth" in setting:
            depth = setting["depth"]
            label = f"May pursue side work {depth} generation(s) deep"
            may_pursue_next = (gen + 1) <= depth
        else:
            label = "Asks before pursuing side work"
            may_pursue_next = False

        task_gravity = {
            "setting": setting,
            "label": label,
            "generation": gen,
            "may_pursue_next": may_pursue_next,
        }

        # 5. recall(work) tiers
        recall_tiers = None
        if work:
            from mentis.worker import Surface

            surface = Surface(corpus.root, corpus=corpus)
            recall_tiers = surface.recall(
                work,
                cid,
                participant=participant,
                full=False,
                limit=12,
                scope=scope,
            )

        return {
            "for": participant,
            "persona": persona_full,
            "workflow": workflow_full,
            "disciplines": disciplines_condensed,
            "task_gravity": task_gravity,
            "recall": recall_tiers,
        }

    return cache.get(key, compute, deps=deps)
