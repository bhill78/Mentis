# R4-R6 live-state gate

This is the section 3.3 gate for R4-R6 at `5f5170b`. It changes neither the migration architecture nor the rule in [`contracts/live-snapshot.md`](contracts/live-snapshot.md): a Rust read uses a named field only while the snapshot is fresh, forwards while stale or when the optional field is absent, and returns the Python-unavailable answer when Python is unavailable. A snapshot is never authority and never supplies a write decision.

## Gate result

`run_marks` is invalidation only, not run status. Two richer registries affect R4-R6 answers: `MentisService._runs` through `agents_runs()` and `Conversations._executions` through `active_executions()`. Sources has a separate `_RUNS` registry.

Both richer fields **pass the cost and lifetime gate**, subject to the producer corrections stated below. The copied Brain contains 3,611 `execution-started` acts from 2026-09-27 through 2026-11-01 UTC: 100.306 starts per calendar day, with a peak of 12 starts open at once. At that rate a 30-day process retains about 3,009 executions, 90 days about 9,028, and a year about 36,612. A real-`Execution` scan, six-member projection and JSON serialisation with eight active results measured 0.0727 ms p95 at 3,600 retained entries, 0.2042 ms at 10,000, and 2.5808 ms at 100,000 (about 997 days at the observed rate), all below the contract's 10 ms p95 field budget. Growth therefore does not reject `active_executions`.

`MentisService._runs` does **not** grow for the process lifetime. `_prune_runs()` keeps every active run and only 32 ended observations (`core/service.py:1257-1263`). The copied record's peak overlap sizes a normal registry at no more than 44 rows. The benchmark bracketed that with 40 rows at 0.2818 ms p95 and 64 at 0.5594 ms p95; even 1,032 rows measured 6.4667 ms p95. A named-member producer can therefore pass after `running` is maintained as service-owned observation state and the writes at `core/service.py:1430-1439` are put under the service lock. Today's `agents_runs()` is not that producer: it calls MARS and its observation dictionaries can mutate outside the lock.

The admitted fields restore the routes that waited only on them. Fluid conversation activity/ids and `/api/conversations` return to R4.1; live Turn, decision, thread and intake views return to R4.2; full Brain and brain-scope context use the overlay in R6.1; and working/activity plus `/fluid/api/runs` use it in R6.2. Full Conversation still waits on `CurrentWork`; `/api/who` still waits on MARS discovery and `agents_list`; work detail/ids still wait on stage/git/`_FAILED`. Those remain R7-last or subject to defect 1 for reasons unrelated to these fields.

The implementation may additionally bound `active_executions` structurally, but need not do so to pass this gate. `_executions` is otherwise read only by `end_execution` and `active_executions` (`conversation/__init__.py:6854,6860`). Removing an entry in `end_execution` makes a second end of the same reference raise `KeyError`, whereas it currently returns the same ended object again. The two dispatch calls at `web/dispatch.py:1942,1993` are mutually exclusive because the exception path returns before the normal `finally`. A separate active map is the clean alternative: pop it on end while retaining `_executions` for the existing repeat-end behaviour. Either edit is the same Python-restart class already required to add a field.

### Measurement evidence

The timing used `time.perf_counter_ns`, warmed each case once, and reports the sample p95 for the complete field operation: copying the registry, projecting the named members, filtering where applicable, and `json.dumps` of the result. The active-execution retained cases use eight active objects; the copied record's maximum durable overlap was 12. The run cases retain 32 ended observations plus the stated active count and use real `MentisService` and `RunFeed` objects.

| Field/case | Population | Repetitions | Median ms | p95 ms | Maximum ms | JSON bytes |
|---|---:|---:|---:|---:|---:|---:|
| `active_executions`, retained | 3,600 / 8 active | 2,000 | 0.0645 | 0.0727 | 0.1700 | 1,253 |
| `active_executions`, retained | 10,000 / 8 active | 500 | 0.1678 | 0.2042 | 0.3720 | 1,253 |
| `active_executions`, retained | 100,000 / 8 active | 60 | 2.1886 | 2.5808 | 3.4386 | 1,271 |
| `active_executions`, concurrent-only alternative | 1,000 / 1,000 active | 2,000 | 0.5957 | 0.6932 | 2.3118 | 148,781 |
| `run_observations` | 40 / 8 active | 5,000 | 0.1087 | 0.2818 | 0.8900 | 17,139 |
| `run_observations` | 64 / 32 active | 5,000 | 0.1671 | 0.5594 | 1.6374 | 27,267 |
| `run_observations` | 1,032 / 1,000 active | 1,000 | 2.7134 | 6.4667 | 17.5104 | 438,655 |

The synthetic values have the real classes and declared shapes, including JSON-shaped `tooling`, but admission still tests actual MARS-returned tooling because its type permits arbitrary values. The copied Brain was opened only by SQLite's read-only mode; no development server or test opened it.

## Named fields

| `fields` member | State | Exact source and JSON members | Producer and reread rule |
|---|---|---|---|
| `live_now` | Existing | `st.agents.live_now()`; sorted `[instance, liveness]` pairs | Service lock only, no statement. It describes held handles, not runs. |
| `run_marks` | Existing | `st.agents.run_marks()`; sorted tuples of `run`, `performing_since`, last-event time, `ended_at`, stop-present, permission count and activity | Service lock only. Invalidation input only. |
| `run_observations` | Admitted design; producer correction required in R4.1 | Map by run. Each value names `run`, `instance`, `opened_at`, `performing_since`, `last_event`, `ended_at`, `stop`, `outcome`, `consent_applied`, `tooling`, `permission`, `permissions`, `activity`, `activity_at`, and `running` (`core/service.py:1235-1280,1430-1439`). | Copy explicitly named members under the service lock; put every mutation under that lock and maintain per-instance `running` there rather than calling MARS from the snapshot. Admission tests JSON-serialise actual `tooling` values. Bounded to active + 32 ended; 64 rows measured 0.5594 ms p95 and 1,032 measured 6.4667 ms. Changes do **not** move `generation` or `live_hash`, which remain functions of `(live_now, run_marks)`; a dependent route rereads when its polled key changes (`web/__init__.py:193-225`). |
| `active_executions` | Admitted | List entries contain only `reference`, `participant`, `conversation`, `runtime`, `persona`, `for_expectation` | Copy `list(values())`, filter ended entries, project named members and serialise, with no lock or statement. At 100,000 retained entries/eight active it measured 2.5808 ms p95, below the 10 ms budget; remeasure if a process exceeds 100,000. |

Not fields: `CurrentWork`; Sources `_RUNS` and extraction registries; `agents_list`; git/deployed-commit state; stage `_FAILED`; held-file `stat`/hash results; cache statistics; runtime discovery. These either require another process/lock, statements, filesystem or git access, are unbounded data, or are memo state rather than a stable live fact. They stay with their owning Python operation until that responsibility moves.

## Transitive handler trace

“Durable” means the returned facts are record/held-file facts even when Python uses a memo. It does not mean the implementation is cheap. “Waits for R7” means the live dependency is not admitted to the snapshot.

### R4

| Route | Transitive state reached | Gate result |
|---|---|---|
| `/fluid/api/conversations?activity=1`, `?ids=` | `_live()` reaches both `agents_runs()` and `active_executions()` | R4.1 with both admitted fields. The 1,047-1,475-statement evidence applies again. |
| `/fluid/api/home/needs-you`, `/fluid/api/needs-you/items`, `/fluid/api/needs-you` | `asking_owner` calls `expectations`, and `_ask_rows` calls `_expectation_states`; both compute `live_execution` | Durable output. Presence uses `expected_of` and `response_present`; item grouping/wording uses recorded expectation/form fields, answers, withdrawals and lapses. No branch and no emitted member reads `live_execution`, so an active handle changes neither which needs-you item is present nor its wording. `_POLLED` is only a response memo. |
| `/fluid/api/decisions`, `/api/turns?ids=`, `/api/turns/<id>`, `/api/conversations/<id>/thread/<root>` | `_turn_view` -> `expectation_state()` -> `active_executions()`; `_expectation_view` exposes `live_execution` | R4.2: compute the durable subset and union the admitted active overlay before emitting Python's `live_execution`. |
| `/fluid/api/participants` | Participant rows, owner and declared defaults | Durable. |
| `/api/participants` | `_avatar` reads avatar identity, `artifacts.describe(..., verify="cached")` and durable execution history for last runtime; no run registry. Held-file verification/stat cost is not bounded by a statement budget | Durable/held-file, not snapshot-dependent. |
| `/api/conversations` | `conversation_summaries(cv.active_executions())` | R4.1 with `active_executions`. |
| `/api/intake` | `resumable` reaches `_expectation_view` and branches on `live_execution` | R4.2 with the merged durable/live expectation state. |
| Full `/api/conversations/<id>` | Turn views use `live_execution`, but the `owed` block also reads `CurrentWork` through `read_model` | The live part is covered, but the route still waits on defect 1/R7 for `CurrentWork`. |

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
| `/fluid/api/runs` | `agents_runs()` observation only in the traced handler | R6.2 with `run_observations`. |
| `/api/working` | `_row` -> `_delegated` -> `waiting_on` -> `_child_state` branches on `live_execution`; full form also uses `agents_runs()` | `?count=1` is durable. Full form moves in R6.2 with both fields and the merged expectation state. |
| `/api/who/<id>` | `agents_runs()`, `agents_list()` liveness filtering, and `runtime_names()` from MARS | Stays with R7 machine/live reads. `live_now` is not an `agents_list` replacement. |
| `/api/activity` | `agents_runs()` and `active_executions()` | R6.2 with both fields. |
| `/fluid/api/work?ids=`, `/api/work/<id>` | `project` -> `trunk_status` -> `active_executions()`; `stage_of` also reaches git/deployed commit and the 600 s `_FAILED` memo | Wait for R7 last. A statement budget does not cover git or remembered failure state. |
| Work/owed collections, Home work and worker `work_overview` | `CurrentWork`, `SharedAnswers`, run observations, stage and git | Open defect 1; no snapshot of the model. |
| `/api/conversations/<id>/work` | Recomputes work with runtime observation | Delete only after the universal caller check proves no external/forward caller; otherwise follows defect 1. |
| `/fluid/api/home/briefing` | Returned-work and Turn record data | Durable; assigned to R6.2. |
| `/api/context` | Conversation scope is durable composition. Brain scope calls `brain.orientation()` and renders active executions | Both move in R6.1; brain scope adds `active_executions`. |
| `/api/brain` | `?identity=1` reads the manifest. Full orientation calls `active_executions()` and renders `RUNNING` lines | Both move in R6.1; full orientation adds `active_executions`. |
| Worker `orient` | Its Brain implementation lists durable conversations/participants/governance and caller grant; it does not call `brain.orientation()` | Durable composition; caller policy remains at the door. |
| Worker `recall` | Brain `recall` calls `brain.compose`, so Python **does compute** the live brain-orientation component. `recall` then keeps only components whose tier is governing/adopted/experience, so that untiered component is not returned; `comp.withheld` still contributes the durable “conversations are named” row | Rust may avoid computing the live component without changing the wire answer only if it preserves that withheld row and every tier/omission. Saying Python itself omits the computation would be false. Conversation recall is durable. |
| Worker `brief` | Conversation composition is durable, but `orientation.outstanding` reads `CurrentWork` | Split: foundation/agent composition in R6.1, outstanding block in R6.2. |
| `owner_of`, `asked_with` | `owner_of` reads the durable baseline owner; `asked_with` reads request lineage, Persona assignment, Task Gravity and consent from the record | Durable; neither reaches a live registry. |

### R6.3 long tail

The previously unopened handlers were read, including their callees. Governance, operational history/provenance/gravity, ladder, anchor GETs, `/api/resurrect`, `/api/entries/<id>`, `/api/space`, `/api/space/said` and `/api/neighborhood` use the record (and, for some ladder/media shapes, held artifact descriptions). Presentation/layout reads use `presentation/` files and file locks. None reaches `_executions`, `active_executions`, `agents_list`, `agents_runs`, stage/git/`_FAILED`, or CurrentWork.

Timer GETs (`timer_state` and `time_spent`) are record-only. `conversation/timers.py:311` calls `expectation_state`, but only from `_directed`, the POST mark-authority path; it is not in either R6 GET path. It therefore does not make the timer GET rows live. Held artifact/file-stat work is named as non-statement cost for ladder/media/presentation packages and is not called a live snapshot.

### Durable expectation-state branch audit

Python's `live_execution` is already a union. `expectation_state` first derives a durable set from this expectation's `execution-started` acts not closed by `result-returned`, `result-recovered` or `delivery-failed` (`conversation/__init__.py:3723-3731`), then adds exact/fallback machine-local handles (`:3732-3738`). A Rust `expectation_states` operation can answer the durable set by itself; it must not pretend that set is the whole Python value. The active overlay adds executions begun without a durable start (fixtures and `--demo-activity`) and the fallback handle that names no expectation but matches carrier plus Conversation. Normal dispatch records its start before beginning the handle, so the durable subset usually already names that run and, intentionally, survives a Python restart until a durable end is written.

The merged route view therefore emits `live_execution = durable_open_refs ∪ overlaid_active_refs`. Durable consumers may keep only the durable fields they actually branch on:

- Needs You branches on carrier, `response_present`, withdrawal/lapse/answer and recorded form/input fields; it neither tests nor words from `live_execution`.
- Decision-form openness and R6.1 foundation owner decisions branch on `response_present`, not liveness.
- Full working/delegation state and intake resumption **do** branch on `live_execution`; they require the merged value, not merely omission from their JSON.
- Timer GETs never enter the expectation-state caller; the one timer call is on the POST authority path.

## Stalled-Python acceptance

Every admitted field and dependent route tests: optional-field omission forwards; fresh parity; stale (>2 s) forwards without rendering held state; unavailable (>10 s or process loss) returns the Python-unavailable answer while durable siblings continue; changed boot/lower generation/unknown schema discards held fields; recovery adopts only a good poll; and resume-after-idle forwards until a good poll. `run_observations` additionally tests per-instance `running`, the explicit member list, JSON serialisation of actual tooling, concurrent end/consent/tooling mutation, and the fact that its changes do not move the envelope generation/hash. `active_executions` tests the durable/live union, unrecorded fixtures, ended filtering, repeat-end semantics and the 100,000-entry cost point.

The parity tests use fixture Brains and the existing proxy stand-ins. The sizing query used the approved Brain copy, read-only; the timing script constructed real classes and no Brain.
