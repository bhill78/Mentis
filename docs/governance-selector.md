# Governance relevance selector: interface proposal (Tev readiness)

Status: **proposal only.** Nothing here is implemented or active. The owner decides whether
and when a selector is wired in, and which one.

## Why one might be wanted

Procedural material (rules, decisions, disciplines) reaches an execution by **placement**
(`compose`, `mentis/conversation/__init__.py`): placed at the Conversation, placed on the
whole Brain, carried by a Persona, or named for the invocation. A rule "is not relevant, it
applies". That keeps delivery exact and small, but it leaves two gaps the 2026-10-28 audit
measured:

- a rule that matters for only some work must either be placed whole-Brain (delivered to
  every run, so the universal set grows) or not placed (delivered to nobody unless named);
- a hand-started CLI session receives nothing it does not ask for.

A selector closes the first gap without growing the universal set: it chooses, for one piece
of work, which of a bounded set of *eligible* rules to include. It never decides what is
eligible.

## Division of responsibility

| Mentis (unchanged authority) | Selector (optional, advisory) |
|---|---|
| which material stands (`Corpus.stands`: established, not superseded) | reads the task context and the catalogue |
| supersession resolved before anything is offered | returns candidate ids, best first |
| placement and scope: what is eligible for this work at all | nothing else |
| the authoritative text delivered (read from the record, never from the selector) | |
| grants and authority (`/api/worker`, `permitted`) | |
| recording what was delivered and why (`delivery.behavioural_sources`) | |

The selector cannot establish, place, supersede or challenge material, grant authority, or
change governance. It has no write path: it is called with data and returns ids.

## Eligibility: where the catalogue comes from

A new placement *mode*, not a new placement: material placed (whole-Brain or at a
Conversation) **when relevant** instead of **always**. Today every placement is "always".

- **always** — delivered by placement, exactly as now. Keep this set small and universal.
- **when relevant** — eligible for this scope; delivered only if selected.

The catalogue for one composition is: standing, supersession-resolved procedural material
whose placement is *when relevant* and whose scope admits this work (whole-Brain, or this
Conversation), bounded (e.g. at most 50 entries; if more are eligible, the bound and the
remainder are named in `withheld`, as the knowledge channel already does).

## Interface

```
select(request: SelectionRequest, *, budget_ms: int) -> SelectionResult
```

`SelectionRequest` (built by Mentis; data only):

```json
{
  "work": "the task description (request text, or the CLI's recall question)",
  "conversation": {"id": "ent-…", "name": "…", "about": "…"} | null,
  "persona": "Builder" | null,
  "repository": "C:\\Work\\Mentis" | null,
  "catalogue": [
    {"id": "ent-…", "kind": "rule", "title": "…", "summary": "≤300 chars",
     "about": "…", "scope": "whole-brain" | "conversation"}
  ],
  "limit": 5
}
```

`SelectionResult`:

```json
{"selected": [{"id": "ent-…", "why": "short reason"}],
 "selector": "tev1:0.8b" | "terms" | "none",
 "elapsed_ms": 140}
```

Mentis then:

1. drops any returned id not in the catalogue (a selector cannot widen eligibility);
2. caps at `limit`;
3. reads each entry's authoritative text from the record;
4. composes them as governing components with `scope` = their placement and
   `why` = "selected as relevant to this work by <selector>: <why>";
5. records the selector name and the selection in the delivery's `behavioural_sources`, so
   what reached a run, and why, stays auditable.

## Optional and nonblocking

- The call has a budget (e.g. 300 ms for a local model). On timeout, error, or malformed
  output, Mentis uses the fallback and records `selector: "<name> failed: <reason>"`.
  Composition never waits beyond the budget and never fails because a selector did.
- With no selector configured, *when-relevant* material is **listed, not delivered**: the
  composition carries a one-line index (id + title) of eligible rules so the agent can ask
  `governed` for any it judges relevant. This is the zero-model default.
- Selection is never a gate: it adds context, it never blocks work or authority.

## Implementations behind the same interface

- **Tev** (`tev1:0.8b` on the local Ollama server, `http://127.0.0.1:11434`): prompt =
  work + catalogue titles/summaries; output = JSON list of ids. Small enough to answer
  within the budget on this machine; reached through MARS's local backend or directly by
  HTTP — a decision for when it is wired.
- **Another configured model**: the same request/response, through MARS (any backend) or an
  HTTP endpoint named in configuration.
- **Deterministic fallback ("terms")**: term overlap between `work` and each catalogue
  entry's title/summary/about, the same method `mentis/conversation/knowledge.py` uses for
  propositional material (`tokens_of`, `_matching`). No model, always available, and the
  fallback when a model selector fails.
- **"none"**: the listing default above.

## Where it would plug in

One seam in `compose` (`Conversations.compose` / `Brain.compose`), beside the existing
procedural selection and before the knowledge channel; `question` is already passed there by
dispatch and by `/api/context?work=`, and the CLI's `recall` reaches the same `compose`. Every
caller therefore gets the same selection, whatever runtime runs the work.

## What must be decided before implementing

1. The *when relevant* placement mode (vocabulary: a property on the `scoped-to` link body).
2. Which rules move from always to when-relevant (an owner act per rule).
3. Selector configuration (which selector, budget, limit) — Brain-wide setting, owner's.
4. Whether selection runs for hand-started `recall` as well as dispatch (recommended: yes,
   same seam).
