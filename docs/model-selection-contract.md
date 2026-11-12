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
  "relation":  {"value": "new"|"continues"|"revises"|"implements"|"verifies", "ref": [ids], "source": S,
                "found": ["<request>: <how the record found it>"],      // detected only
                "approval": {"ref": id, "by": "owner_decision"|"owner_verdict"|"owner_turn", "why": "words"}, // implements only
                "detected": {"value": "continues", "ref": [ids], "found": [...], "overridden": true}},       // stated relation over a detected one
  "exploratory": {"value": true|false, "done_when": "text"|null, "source": S},
  "scope": {"value": "narrow"|"broad"|"unstated", "source": S},
  "requires": ["build_ui", ...]
}
```
S is one of `stated`, `inherited`, `compat` (from legacy `difficulty`), `default`.
A value that was raised also carries `raised_from: {value, source}`. `found`,
`approval`, `detected` and `scope` are additive (round 2, 2026-11-12); older
records without them read as before.

Legacy compatibility (`difficulty`): mechanical → specified/light; routine →
specified/substantial; complex, architecture, debugging → open/deep.
`ordinary`/`default`/absent → unstated (the soft default applies).
AMENDED (round 2): `bounded` is SCOPE, not a known answer → `scope: narrow`,
`reasoning: substantial`, `solution` UNSTATED (it no longer claims
`specified`). Its need is unchanged (substantial, not open, tier coding), so no
historical pick changes. The evidence profile reads it the same way.
Review and authority-sensitive work keep today's force: needed level `deep`,
open allowed (frontier today), whatever else is stated.

Scope (`narrow` | `broad`) is informational: stated (delegate `scope`, the
composer's dispatch `scope`) or read from `bounded`, recorded, never inherited
and NEVER an input to the need. Narrow scope is not low reasoning.

Needed suitability (`need(req)`): `level` = reasoning (unstated → `substantial`,
the soft default, matching DEFAULT_TIER coding) and `open` = solution == open.
Effort floor: light → low, substantial → medium, deep → high (today's targets).
Scope/size is NOT an input.

Lineage: `continues`/`revises` inherit solution+reasoning from the work they
continue. A stated OR LEGACY value lower than inherited is RAISED to the
inherited one; the warning to the delegator says so (naming the legacy word
where that is what was lower) and the recorded value carries `raised_from`.
`verifies` takes its own stated requirements; `new` inherits nothing. Only
requirements are inherited, never a model or effort.

Continuation is found from the record (`dispatch.continuation_found`), never
from words, and recorded with how it was found (`relation.found`); the
delegator is told what was found and what it keeps:
- a Turn in `references`, or the Turn it REPLIES TO, names work when a result
  was returned on it, a request was recorded on it (a delegation Turn, an
  owner's request Turn; never a decision question), or it was posted as an
  answer to a request (its `turn-said` is caused by the request);
- a delegation under a parent request whose TRIGGER TURN replies to a Turn
  that names work continues that work, whether or not the delegator passed
  references;
- the existing same parent/participant/activity rule.
BOUNDED: one reply hop from each referenced Turn and from the parent's trigger
Turn; chains are never followed. The parent itself is never what its own
delegation continues. WITHIN ONE CONVERSATION (review fix): work whose request
belongs to another Conversation than the parent's (on the composer path, the
post's) is never continued automatically; a reference to it stays a reference. Met (claimed) work is continued like any other: whether
work was claimed met says nothing about what it required.

A stated `new` (or `verifies`) where the record shows a continuation is
honoured: nothing is inherited, the requirements record
`relation.detected {…, overridden: true}`, and the delegator is warned.

`implements` (must ref something the record holds) takes its own stated
requirements ONLY when a relation_ref names an owner approval the record
holds (`dispatch.owner_approval`, recorded as `relation.approval`): an owner
decision the owner answered (the `decision-answered` act or its question), the
owner's verdict accepting the result (`result-verdict` accepted, its request
or the result it names), or a Turn the owner wrote (the owner's words cited as
the approval). Otherwise -- the ref is only the design result, or someone
else's post -- it keeps the requirements of the work it names and of what the
record says it continues (raised, as for `continues`), and the delegator is
told what would make the lowering legitimate.

D4 reassessment: work that revises or continues an attempt that failed
SUBSTANTIVELY (owner rejected, review blocked, or a substantive failure class)
is refused unless the call states `solution` and `reasoning` explicitly; the
refusal shows the prior attempt's requirements, model/effort and the evidence.
AMENDED (round 2): this applies alike to a stated `revises`/`continues`, to a
continuation the record detected, and to a stated `new` overriding a detected
one, and to an `implements` that names no owner approval (it keeps the
named work's requirements, so it is reassessed like a continuation of it);
not to an owner-approved `implements` or a `verifies`. Nothing is
escalated automatically. The delegation records `reassessment: {prior,
evidence, restated}` (plus `detected: true` when the record found it). The
owner's own composer is not forced through D4 (interpretation I6, kept).

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
  soft default or light — disclosed;
  (c) AMENDED (round 2, owner; replaces interpretation I8) as an UNVERIFIED
  ATTEMPT when the need is DEMANDING (anything beyond the soft default and
  light/specified), the work is not review or authority-sensitive, no model
  with ESTABLISHED suitability for the need is available anywhere eligible
  (none established, or every established one refused, exhausted or held), and
  selection chooses the runtime. The model is explicit, never the runtime's
  default run in silence: on a runtime whose required capabilities are all
  CONFIRMED (not merely unknown), a model MARS's `modelCatalogue` lists that no
  statement speaks of at all, usable at the effort floor, not refused, not
  tools-unsupported, not held or exhausted on its own window -- the runtime's
  reported default model where it is such a candidate, else the first such in
  MARS's order. It is SENT EXPLICITLY and recorded `verdict: unknown`,
  `attempt: "unverified"` (on the candidate and on `selection`), with words
  saying no model with established suitability was available and that this
  one's suitability is not established; it is disclosed, never called
  established or suitable, and D3 never applies to it. A model a statement
  speaks of at a lower level is not taken as unverified. With no such
  candidate, the work is refused as before (the tier is not lowered).
  REVIEW FIXES: where nothing stands for any eligible model, every model is
  judged on its own (usability, its own window) BEFORE the capacity gate, so a
  held default never exhausts a runtime whose sibling is usable; with no usable
  discovered model the work is refused in words, never run on an excluded
  model or an implicit runtime default -- only a runtime that lists no model at
  all keeps its own default. A NAMED runtime with demanding work gets an
  explicit discovered model the same way (capacity disclosed, not refused), and
  is refused when it lists only excluded models (naming the model runs it).
  Critical work keeps C1 (never an unknown model automatically) -- refused
  only where some eligible runtime lists models that could be judged; where no
  eligible runtime lists any model at all, the runtime default runs as in the
  serving release (`tier_unfulfilled: no_catalogue_metadata`, said in
  `because`, the author's runtime still avoided). A named runtime, model or
  effort is never substituted.
  `insufficient` candidates are excluded with the statement cited.
- Exploratory work (D2): a newly discovered model nobody has rated is eligible
  with no statement and no manual rating; `exploratory_allowed` limits remain
  (never review, authority-sensitive, or deep work with an open solution).
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
  AMENDED (round 2): every candidate says why it was chosen or not -- verdict,
  capability gate, capacity or hold, tools-unsupported, refused, below the
  effort floor, and (new entries) a named-only runtime and a runtime dropped
  for a model/effort conflict; an established candidate deferred because of a
  reason about its runtime says it (review independence, not confirmed for
  the requirements, a less strong sufficient candidate elsewhere, capacity
  ranking/continuity). `because` ends with one summary line of the selected
  candidate and the excluded/deferred counts grouped by kind of reason.
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
