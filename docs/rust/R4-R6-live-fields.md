# R4-R6 live-state gate

This is the section 3.3 gate for R4-R6 at `5f5170b`. It changes neither the migration architecture nor the rule in [`contracts/live-snapshot.md`](contracts/live-snapshot.md): a Rust read uses a named field only while the snapshot is fresh, forwards while stale or when the optional field is absent, and returns the Python-unavailable answer when Python is unavailable. A snapshot is never authority and never supplies a write decision.

## Gate result

`run_marks` is invalidation only, not run status. Two richer registries affect R4-R6 answers: `MentisService._runs` through `agents_runs()` and `Conversations._executions` through `active_executions()`. Sources has a separate `_RUNS` registry.

`run_observations` remains a candidate, but its current producer is ineligible because it calls MARS before taking the service lock and races writes to observation dictionaries. `active_executions` was evaluated as a second candidate and **does not pass**: although a producer can copy `list(cv._executions.values())` without a statement or lock and then expose only `reference`, `participant`, `conversation`, `runtime`, `persona` and `for_expectation` for entries not marked ended, ended entries are never removed (`conversation/__init__.py:6853-6862`). Every 500 ms poll would scan a registry that grows for the process lifetime. That violates the bounded-cost addition made to [`contracts/live-snapshot.md`](contracts/live-snapshot.md). The code contradicts no requested member or lock assumption; lifetime cost is the refusal.

Consequently, routes whose exact answer reaches `active_executions()` wait for R7 last. In particular: Fluid conversation activity/ids, `/api/conversations`, decisions and Turn views that show `live_execution`, full Conversation/thread views using those Turn views, `/api/intake`, full `/api/brain`, brain-scope `/api/context`, `/api/activity`, `/api/working`, `/api/who`, `/fluid/api/work?ids=`, and `/api/work/<id>`. R4 is reordered so its first package is the durable needs-you/list work, without the conversation-activity performance evidence.

## Named fields

| `fields` member | State | Exact source and JSON members | Producer and reread rule |
|---|---|---|---|
| `live_now` | Existing | `st.agents.live_now()`; sorted `[instance, liveness]` pairs | Service lock only, no statement. It describes held handles, not runs. |
| `run_marks` | Existing | `st.agents.run_marks()`; sorted tuples of `run`, `performing_since`, last-event time, `ended_at`, stop-present, permission count and activity | Service lock only. Invalidation input only. |
| `run_observations` | Candidate; blocked | Map by run. Each value names `run`, `instance`, `opened_at`, `performing_since`, `last_event`, `ended_at`, `stop`, `outcome`, `consent_applied`, `tooling`, `permission`, `permissions`, `activity`, `activity_at`, and `running` (`core/service.py:1235-1280,1430-1439`). | Must snapshot explicitly named members under the service lock, without iterating a dictionary while `agents_perform` mutates it outside that lock; admission must also prove that every `tooling` value is JSON-serialisable. `running` is per instance (`instance in execution.running()`), not per run. Current code calls the MARS lock first, so it fails. Adding this field does **not** change `generation` or `live_hash`, which remain functions of `(live_now, run_marks)`; a dependent route rereads when its own polled key sees a changed `running` value (`web/__init__.py:193-225`). |
| `active_executions` | Rejected | Candidate list entries would contain only `reference`, `participant`, `conversation`, `runtime`, `persona`, `for_expectation` | A producer could copy `list(values())` and run no statements, using no lock, but the source never prunes ended entries. The unbounded lifetime scan fails the snapshot cost rule. |

Not fields: `CurrentWork`; Sources `_RUNS` and extraction registries; `agents_list`; git/deployed-commit state; stage `_FAILED`; held-file `stat`/hash results; cache statistics; runtime discovery. These either require another process/lock, statements, filesystem or git access, are unbounded data, or are memo state rather than a stable live fact. They stay with their owning Python operation until that responsibility moves.

## Transitive handler trace

“Durable” means the returned facts are record/held-file facts even when Python uses a memo. It does not mean the implementation is cheap. “Waits for R7” means the live dependency is not admitted to the snapshot.

### R4

| Route | Transitive state reached | Gate result |
|---|---|---|
| `/fluid/api/conversations?activity=1`, `?ids=` | `_live()` reaches both `agents_runs()` and `active_executions()` | Waits for R7 last. |
| `/fluid/api/home/needs-you`, `/fluid/api/needs-you/items`, `/fluid/api/needs-you` | `expectation_state()` is called, but these projections do not emit `live_execution`; `_POLLED` is a response memo | Durable output; R4.1 may own it. |
| `/fluid/api/decisions`, `/api/turns?ids=`, `/api/turns/<id>`, `/api/conversations/<id>/thread/<root>`, full `/api/conversations/<id>` | `_turn_view` -> `expectation_state()` -> `active_executions()`; `_expectation_view` exposes `live_execution` | Wait for R7 last unless a separate live overlay can be supplied then. Define the Rust `expectation_states` operation from durable facts **without** `live_execution`; the route view adds that key only from the live overlay. |
| `/fluid/api/participants` | Participant rows, owner and declared defaults | Durable. |
| `/api/participants` | `_avatar` reads avatar identity, `artifacts.describe(..., verify="cached")` and durable execution history for last runtime; no run registry. Held-file verification/stat cost is not bounded by a statement budget | Durable/held-file, not snapshot-dependent. |
| `/api/conversations` | `conversation_summaries(cv.active_executions())` | Waits for R7 last. |
| `/api/intake` | `resumable` reaches `_expectation_view` and `live_execution` | Waits for R7 last. |

### R5

| Route or op | Transitive state reached | Gate result |
|---|---|---|
| `/api/references`; worker `find` | `Surface.find` uses record reads, Turn-line/object resolution and held artifact descriptions; no agent registry | Durable/held-file. Cases that schedule extraction stay Python. |
| `/fluid/api/object-refs`, `/fluid/api/document` | `objectref`/`fluid.objects` reach held bytes, extractor/QuickJS results and file descriptions; no agent registry | No live field. Completed reads may move; engine/write-side callers stay Python. |
| `/fluid/api/home/for-you` | `fluid/status.py` reads and may catch up `derived/status.db`, uses rebuild thread, status locks and `_places` | Stays Python through R7 pending an owner ruling on Rust `derived/` writes. Rust writes nothing under `derived/` in R5. |
| Sources overview, folders, compare and `/<collection>/run` | Binding/machine state, Sources `_RUNS`, progress and extraction registries | Stay Python with Sources jobs/acquisition. |
| Sources search and worker `search_sources` | `sources.search.search` reads held-file `stat`, hashes and extraction availability; missing extraction may schedule a `derived/` write | R5 owns one shared search operation only for completed held/extracted inputs. Scheduling/pending cases forward. This operation belongs to R5.2 only. |
| Sources provenance/page/cite/rendered/record/object/history/links/page and worker sources/history/links/read | `reading.py` uses record plus held/extracted files. `/api/sources/cite` can schedule missing extraction | Pure reads may move in R5.2; scheduling forwards. No agent live field. |
| Worker `check_rendering` | `render_check` loads/hashes the process-local JS bundle and runs the engine; timer `about=` validation is record-only | No agent live field. Keep the engine on Python through its R7 write-side callers. |

### R6 work and composition

| Route or op | Transitive state reached | Gate result |
|---|---|---|
| `/fluid/api/home/activity` | Record acts only (`home.py:722-746`) | Durable. This is split from `/fluid/api/runs`. |
| `/fluid/api/runs` | `agents_runs()` observation only in the traced handler | Candidate for `run_observations` if that field later passes. |
| `/api/working` | `_row` -> `_delegated` -> `waiting_on` -> `_child_state` -> `live_execution`; full form also uses `agents_runs()` | `?count=1` is durable. Full form waits for R7 last; `run_observations` alone is insufficient. |
| `/api/who/<id>` | `agents_runs()`, `agents_list()` liveness filtering, and `runtime_names()` from MARS | Stays with R7 machine/live reads. `live_now` is not an `agents_list` replacement. |
| `/api/activity` | `agents_runs()` and `active_executions()` | Waits for R7 last. |
| `/fluid/api/work?ids=`, `/api/work/<id>` | `project` -> `trunk_status` -> `active_executions()`; `stage_of` also reaches git/deployed commit and the 600 s `_FAILED` memo | Wait for R7 last. A statement budget does not cover git or remembered failure state. |
| Work/owed collections, Home work and worker `work_overview` | `CurrentWork`, `SharedAnswers`, run observations, stage and git | Open defect 1; no snapshot of the model. |
| `/api/conversations/<id>/work` | Recomputes work with runtime observation | Delete only after the universal caller check proves no external/forward caller; otherwise follows defect 1. |
| `/fluid/api/home/briefing` | Returned-work and Turn record data | Durable; assigned to R6.2. |
| `/api/context` | Conversation scope is durable composition. Brain scope calls `brain.orientation()` and renders active executions | Conversation scope may move in R6.1. Brain scope waits for R7 last. |
| `/api/brain` | `?identity=1` reads the manifest. Full orientation calls `active_executions()` and renders `RUNNING` lines | Identity is durable; full route waits for R7 last. |
| Worker `orient` | Its Brain implementation lists durable conversations/participants/governance and caller grant; it does not call `brain.orientation()` | Durable composition; caller policy remains at the door. |
| Worker `recall` | Brain composition computes a brain-orientation component, but `recall` returns only governing/adopted/experience tiers, so the live component is not exposed; Conversation recall is durable | Rust must omit the unused live component rather than require a snapshot. |
| Worker `brief` | Conversation composition is durable, but `orientation.outstanding` reads `CurrentWork` | Split: foundation/agent composition in R6.1, outstanding block in R6.2. |
| `owner_of`, `asked_with` | `owner_of` reads the durable baseline owner; `asked_with` reads request lineage, Persona assignment, Task Gravity and consent from the record | Durable; neither reaches a live registry. |

### R6.3 long tail

The previously unopened handlers were read, including their callees. Governance, operational history/provenance/gravity, ladder, anchor GETs, `/api/resurrect`, `/api/entries/<id>`, `/api/space`, `/api/space/said` and `/api/neighborhood` use the record (and, for some ladder/media shapes, held artifact descriptions). Presentation/layout reads use `presentation/` files and file locks. None reaches `_executions`, `active_executions`, `agents_list`, `agents_runs`, stage/git/`_FAILED`, or CurrentWork.

Timer GETs (`timer_state` and `time_spent`) are record-only. `conversation/timers.py:311` calls `expectation_state`, but only from `_directed`, the POST mark-authority path; it is not in either R6 GET path. It therefore does not make the timer GET rows live. Held artifact/file-stat work is named as non-statement cost for ladder/media/presentation packages and is not called a live snapshot.

## Stalled-Python acceptance

Every admitted field and dependent route tests: optional-field omission forwards; fresh parity; stale (>2 s) forwards without rendering held state; unavailable (>10 s or process loss) returns the Python-unavailable answer while durable siblings continue; changed boot/lower generation/unknown schema discards held fields; recovery adopts only a good poll; and resume-after-idle forwards until a good poll. `run_observations` additionally tests per-instance `running`, the explicit member list, concurrent end/consent/tooling mutation, and the fact that its changes do not move the envelope generation/hash.

The tests use fixture Brains and the existing proxy stand-ins. No live Brain, benchmark or implementation is part of this gate.
