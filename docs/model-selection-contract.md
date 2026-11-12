# Model discovery and selection — build contract (2026-11-11 overnight)

The shared interfaces of the hybrid selector the owner approved. Each workstream
owns the files named for it; anything shared is changed only here, by the
integrator. Nothing here is deployed; DAY-TO-DAY is not touched.

## Owner decisions in force (do not change)

- D1. Agents may PROPOSE model-suitability statements; only the OWNER
  establishes standing suitability.
- D2. Newly discovered models may receive bounded, verifiable EXPLORATORY work.
- D3. Expiring capacity may favour a STRONGER suitable model when its allowance
  would otherwise go unused.
- D4. A substantive failure triggers REASSESSMENT, never automatic escalation of
  reasoning or model strength.
- Kept as they are: named runtime/model/effort are never substituted (refused
  or run exactly, disclosed); capability gate; quota holds; review independence;
  authority (one door, `/api/worker`); append-only record; no new background
  mechanism (discovery refreshes only inside `keep_current`'s activity window).

## 1. MARS: model catalogue (`_mars/backends`, per backend) — Workstream A

`routingModels` and `effectiveDefaultModel` stay exactly as they are (the
rollback pair and today's Mentis read them). NEW, additive:

```json
"modelCatalogue": {
  "complete": true,                 // false: the list may be partial (why says how)
  "why": null,                      // or plain words: timed out, not reported, ...
  "source": "configOptions" | "agy models" | "ollama /api/tags" | "lmstudio /v1/models" | "kimi ..." | "backends.json" | null,
  "readAt": 1794450000.0,           // when this list was read (epoch s); null if never
  "models": [{
    "id": "claude-opus-5",          // exactly what is sent to select it
    "displayName": "Opus 5" | null,
    "aliases": ["opus"],            // other ids/values that select the same thing, ONLY where the runtime says so
    "aliasOf": null | "claude-opus-5-5", // for an alias entry: what it resolved to, only if observed
    "status": "listed" | "launched" | "refused" | "unknown",
    "statusAt": 1794450000.0 | null,
    "statusWhy": null | "words",    // e.g. the refusal MARS saw
    "efforts": ["low","medium","high"] | null,   // null = not known for THIS model
    "effortsVerified": true,        // true only when read with this model selected
    "effortInId": false,            // effort is part of the id (antigravity)
    "defaultEffort": "medium" | null,
    "contextWindow": null | 200000, // only if the runtime reports it
    "locality": "remote" | "local" | "unknown",
    "capabilities": {"tools": "supported"|"unsupported"|"unknown"}, // model-level, only where measured/reported (ollama /api/show)
    "quotaGroup": null | "fable",   // the capacity window group this model draws on, only where known
    "providerSaid": null | "text"   // the runtime's own description, verbatim; NEVER evidence
  }]
}
```

Rules: nothing inferred (no effort list, context window, tool support or reset
time that the runtime did not report). Unknown is `null`/`"unknown"` plus `why`.
Discovery is bounded (per-call deadlines) and cached; a slow or failed read keeps
the last list with `complete:false` and says so. `status` launched/refused is what
MARS itself observed setting the model on a session in this process. Capacity
readings mark model-scoped windows with the existing `group` field and the
existing `model_groups` mapping (as antigravity already does), so Mentis's
`_report_view` judges a model against its own window. AMENDED (integration,
2026-11-12, independent review): a model-scoped window that sits beside
account-wide windows (Claude's `seven_day_fable`) is marked with the additive
`modelGroup` instead, `group` staying null, so a Mentis released before this one
reads it exactly as before; this Mentis reads `group` or `modelGroup`. A window
with no group is shared by every model; a group window serves only its models.

## 2. Mentis: work requirements — Workstream B (`mentis/core/requirements.py`)

Recorded on the request (`routing.requirements`) and on `execution-started`:

```json
"requirements": {
  "solution":  {"value": "specified"|"open"|"unstated", "source": S, "from": [ids]},
  "reasoning": {"value": "light"|"substantial"|"deep"|"unstated", "source": S, "from": [ids]},
  "relation":  {"value": "new"|"continues"|"revises"|"implements"|"verifies", "ref": [ids], "source": S},
  "exploratory": {"value": true|false, "done_when": "text"|null, "source": S},
  "requires": ["build_ui", ...]
}
```
S is one of `stated`, `inherited`, `compat` (from legacy `difficulty`), `default`.

Legacy compatibility (`difficulty`): mechanical → specified/light; bounded,
routine → specified/substantial; complex, architecture, debugging → open/deep.
`ordinary`/`default`/absent → unstated (the soft default applies).
Review and authority-sensitive work keep today's force: needed level `deep`,
open allowed (frontier today), whatever else is stated.

Needed suitability (`need(req)`): `level` = reasoning (unstated → `substantial`,
the soft default, matching DEFAULT_TIER coding) and `open` = solution == open.
Effort floor: light → low, substantial → medium, deep → high (today's targets).
Scope/size is NOT an input.

Lineage: `continues`/`revises` inherit solution+reasoning from the work they
continue (a stated value lower than inherited is RAISED to the inherited one and
the delegator is warned); `implements` (must ref an approved artifact/decision)
and `verifies` take their own stated requirements; `new` inherits nothing.
Continuation is found from the record: references to a returned result, a Turn
that REPLIES to a returned result, and the existing same parent/participant/activity
rule (`dispatch.inherited_routing`). Only requirements are inherited, never a
model or effort.

D4 reassessment: a `revises` of an attempt that failed SUBSTANTIVELY (owner
rejected, review blocked, or a substantive failure class) is refused unless the
call states `solution` and `reasoning` explicitly; the refusal shows the prior
attempt's requirements, model/effort and the evidence. Nothing is escalated
automatically. The delegation records `reassessment: {prior, evidence, restated}`.

## 3. Mentis: suitability — Workstream C (`mentis/suitability.py`, `mentis/evidence.py`)

Statements are append-only operational acts (vocabulary is data):
`suitability-proposed` (any agent, via worker op `propose_suitability`; the
owner too), `suitability-established` (OWNER ONLY, owner HTTP route), 
`suitability-superseded` (owner only), `suitability-declined` (owner only).

Statement body:
```json
{"pattern": "claude-opus-*", "runtimes": ["claude","antigravity"] | null,
 "reasoning_max": "light"|"substantial"|"deep", "open": true|false,
 "insufficient": false,           // true: owner states it is NOT suitable for what it names
 "basis": "words", "evidence": [act/entry ids], "proposed_by": id, "supersedes": id|null}
```

Legacy standing: the tier table the owner approved (#1401) is carried as
standing statements with source `legacy-tier` (not agent-established):
economy → light/specified, coding → substantial/specified, frontier → deep/open,
for exactly the ids MARS tagged (claude-haiku-4-5-20251001, claude-sonnet-5,
claude-opus-5, claude-fable-5, gpt-6-luna, gpt-6.1-terra, gpt-6.1-sol). These
come from a fixed Mentis-side table `LEGACY_STANDING` (moved out of MARS's role;
MARS keeps emitting `routingModels` only for rollback) and can be superseded by
the owner.

API (pure, read-only over the record):
```python
standing(cv) -> list[Statement]             # established, not superseded, plus LEGACY_STANDING
verdict(statements, runtime, model_id, aliases, need) -> {
    "verdict": "established"|"unknown"|"insufficient",
    "by": "direct"|"pattern"|"legacy"|None, "statement": id|None, "why": "words"}
```
Matching: a statement matches when `pattern` (fnmatch, case-sensitive) matches the
id or an alias, and `runtimes` is null or contains the runtime. An exact-id pattern
is `direct`; a wildcard is `pattern`. Established requires reasoning_max ≥
need.level and (not need.open or statement.open). `insufficient` only from an
explicit owner statement. Otherwise `unknown`.

Outcome evidence (`mentis/evidence.py`): per execution, the ladder
`claimed` (outcome-claimed) < `recorded` (expectation-met) < `verified`
(review-verdict pass by another participant) < `owner_accepted` /
`owner_rejected` (NEW act `result-verdict`, OWNER ONLY, owner route, about the
request: {"verdict": "accepted"|"rejected", "why", "result": act id}); and the
failure class: `substantive` | `infrastructure` | `quota` | `permission` |
`cancelled` | `interrupted` | `capability_missing` | `unclassified`. A report
counts recorded facts per runtime × model × requirement profile; no scores.
Evidence never changes standing by itself (D1).

## 4. Mentis: selection — Workstream D (`mentis/core/selection.py` + `execution_select`)

Candidates are (runtime, model, effort) from `modelCatalogue` (falling back to
`routingModels`/catalogue models when a backend has no catalogue). Order:
1. named constraints (unchanged semantics); 2. capability gate (unchanged);
3. suitability per candidate (`verdict`); 4. unknown handling; 5. availability,
model status `refused`, capacity gate and quota holds (per model group);
6. review independence; confirmed-before-unconfirmed (unchanged);
7. capacity preference among ADEQUATE candidates; 8. effort; 9. tie-break.

- Established candidates are used first. Unknown candidates are never dropped
  silently: each is listed as `deferred` with its reason. They are used:
  (a) when the request is `exploratory` with a `done_when` — then unknown
  candidates meeting the capability gate are PREFERRED (D2); never for review,
  authority-sensitive work, or need.level == deep with open solution unless named;
  (b) as a fallback when no established candidate survives and the need is the
  soft default or light — disclosed.
  `insufficient` candidates are excluded with the statement cited.
- Capacity (D3): among adequate established candidates, the existing pace rule
  (`_by_capacity`: budget that would expire unused per hour to its reset, the
  overdue guard, rotation, catalogue order), evaluated per candidate against the
  window group that serves its model. A candidate stronger than the least
  sufficient is preferred only when its window's pace is known, its budget left is
  ≥ GUARD_SUBSTANTIAL, and its pace exceeds the least sufficient candidate's;
  otherwise least sufficient wins. Never trades a required capability or
  established suitability for quota.
- Effort: the least advertised canonical effort ≥ the floor for that model.
  Model with unknown efforts: no effort is sent (runtime default), recorded as
  `effort_floor_unverified`, and it ranks after candidates with verified efforts.
- Effort conflicts (`routing.effort_conflicts`) unchanged.
- Recorded on `execution-started` (additive): `requirements`, `selection.candidates`
  = every meaningful candidate with `verdict`, `by`, `statement`, `capacity`,
  `outcome` (`selected` | `deferred` | `excluded`) and `why`;
  `selection.recommendation` when a named field differs from what automatic
  selection would have chosen (said, not acted on).
- Old fields (`routing`, `selected_*`, `selection_because`, `field_binding`) are
  still written, so existing readers and historical records keep working.

## Files and ownership

| Workstream | Repo / branch | Owns |
|---|---|---|
| A (Codex) | MARS `model-discovery` | `rust/crates/mars/src/backends/*`, `catalog.rs`, `capacity.rs`, `registry.rs`, local worker model listing, MARS contract docs/tests |
| B+D | Mentis `model-selection` | `mentis/core/requirements.py`, `mentis/core/selection.py`, `mentis/core/routing.py`, `mentis/core/service.py` (selection parts), `mentis/web/dispatch.py` (routing/lineage parts), `mentis/worker.py` (delegate schema/routing), `conversation/posting.py` (routing parts), their tests |
| C | Mentis `msel-suitability` | `mentis/suitability.py`, `mentis/evidence.py`, worker op `propose_suitability`, owner routes (`/api/suitability*`, `/api/requests/<id>/verdict`), their tests |

Interfaces between B+D and C: exactly `suitability.standing/verdict` and
`evidence` above. B+D may stub them until C merges.
