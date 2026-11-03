# R4-R6 live-state gate

This is the section 3.3 gate for R4-R6. It traces the handlers at `5f5170b`; it does not redesign the releases. The governing rule remains [`contracts/live-snapshot.md`](contracts/live-snapshot.md): a Rust read may consume a named `fields` member only while the snapshot is fresh, must forward while it is stale, and must return the Python-unavailable answer when it is unavailable. A snapshot is never authority and never supplies a write decision.

## Result

The existing fields are sufficient only for pulse invalidation. `run_marks` is explicitly “not a status” (`core/service.py:1312-1321`), and no R4-R6 adapter may derive one from it. The live R4 and R6 answers use two richer Python registries: `MentisService._runs` through `agents_runs()` and `Conversations._executions` through `active_executions()`. R5 also exposes the unrelated Sources `_RUNS` registry. None is in the snapshot today.

Only `run_observations` is a candidate addition to schema 1. It is not admitted until Python can produce it under the service lock alone: today's `agents_runs()` also takes the MARS execution lock to call `execution.running()`. `active_executions`, Sources progress, `CurrentWork`, cache state, and runtime discovery are not admitted. Therefore every row below which needs one of those stays on Python unless its package first removes that dependency or satisfies this gate and review.

## Fields

| `fields` name | State | Exact Python source at `5f5170b` | JSON type and meaning | Producer cost and lock rule |
|---|---|---|---|---|
| `live_now` | Existing | `st.agents.live_now()`, `core/service.py:1306-1310`, from `MentisService._live` | `[[instance: string, liveness: string], ...]`, sorted | Cheap in-memory copy under `MentisService._lock`; no statement. It describes handles, not runs. |
| `run_marks` | Existing | `st.agents.run_marks()`, `core/service.py:1312-1321`, from `_runs` and each `RunFeed.activity` | `[[run: string, performing_since: number|null, last_event_at: number|null, ended_at: number|null, stop: boolean, permission_count: number, activity: string|null], ...]`, sorted | Cheap in-memory marker under `MentisService._lock`; no statement. It is invalidation input only. |
| `run_observations` | Candidate addition, blocked on producer seam | The answer of `st.agents.agents_runs()`, `core/service.py:1265-1280`, from `MentisService._runs`, `RunFeed`, permissions, and whether the instance is in `execution.running()` | `{[run: string]: {instance: string, opened_at: number|null, performing_since: number|null, last_event: object|null, ended_at: number|null, stop: object|null, outcome: object|string|null, permission: object|null, permissions: object[], activity: string|null, activity_at: number|null, running: boolean}}` | The copy is bounded by held/32 ended runs and permissions, and runs no statement. It is **not eligible as written**: `execution.running()` first takes `execution.mars._lock`, then `agents_runs()` takes the service lock. The snapshot route is allowed only the service lock. R4/R6 may add this name only after `running` is maintained in the service-owned observation, or an equivalent reviewed service-only source exists. |

The following are deliberately **not** fields:

| State requested by a handler | Python source | Why it is not snapshot material |
|---|---|---|
| Active execution handles | `cv.active_executions()`, `conversation/__init__.py:6859-6862`, backed by `Conversations._executions` | It is a second process-local registry outside `MentisService._lock`. It is needed before a durable run start exists, so neither `live_now` nor `run_observations` is equivalent. Routes that expose it stay on Python unless the release moves ownership of the registry. |
| Current work model | `operational/current_work.py:_MODELS`, maintained every 5 s by the `current-work` thread | It is a derived projection that runs record statements, time/git/reconcile work, and consumes both live registries. Sending the model would turn `/private/live` into an unbounded data route and violate the no-statement rule. R6 must decide defect 1 in `P1.0-inventory.md`. |
| Sources run/progress | `sources/runs.py:_RUNS` under its own `_LOCK`; extraction pending/cache registries | A different lock and potentially large `result`/progress objects. They belong to the Sources execution boundary, not agent-run liveness. The affected reads stay on Python through R7 Sources unless R5 owns a separate source-run interface. |
| Cache and memo state | `_POLLED`, `ContextCache`, `SharedAnswers`, stage/status/extraction caches | These affect cost, not the semantic answer. Rust operations must be correct cold and do not reproduce Python cache state. |
| Runtime names or machine discovery | `st.agents.runtime_names()` -> MARS `execution.backends()` | A MARS call, not a cheap service-lock read. `/api/who/<id>` keeps this part on Python with the other machine-bound reads. |

## Handler trace

“Durable” below includes held/derived files when named. “No snapshot” means the route can be owned without a live field. A grouped row lists every path in the corresponding row of [`routes.md`](routes.md).

### R4

| Route | Handler at `5f5170b` | What it actually reads outside the record | Gate result |
|---|---|---|---|
| `GET /fluid/api/conversations?activity=1` and `?ids=` | `fluid/__init__.py:63-72` -> `fluid/read.py:416-485` | `_live()` combines `agents_runs()` with `cv.active_executions()`; the rest is durable conversation rows and expectation state | Cannot be exact from the snapshot. `run_observations` is insufficient without `active_executions`; stays Python until that registry moves or is removed from the answer. |
| `GET /fluid/api/home/needs-you` | `fluid/home.py:351` | Durable expectation/carrier state and the owner; no live registry | No snapshot. |
| `GET /fluid/api/needs-you/items`, `/fluid/api/needs-you` | `fluid/home.py:427,610,634` | Durable expectation/form state; `_POLLED` is only a Python response cache | No snapshot. R4 shortens `_POLLED`, but cannot remove it because R6 paths remain. |
| `GET /fluid/api/decisions`, `GET /api/turns?ids=` | `fluid/__init__.py:221-231`, `web/__init__.py:898-945,1845-1905` | Durable Turns, expectation state, forms, deliveries; `_POLLED` only caches the decision answer | No snapshot. |
| `GET /api/turns/<id>` | `web/__init__.py:1773-1824,4030-4035` | Durable Turn versions, filings, standing, deliveries and inspector data | No snapshot. |
| `GET /fluid/api/participants` | `fluid/read.py:512-542` | Durable Participants, owner and optional declared runtime defaults | No snapshot. |
| `GET /api/participants` | `web/__init__.py:2202-2242` | Durable Participants, conversations, runtime defaults, intake carrier and avatar artifacts | No snapshot. The census `I` classification is confirmed durable. |
| `GET /api/conversations` | `web/__init__.py:3355-3360` -> `conversation_summaries(cv.active_executions())` | `Conversations._executions` supplies the live count | Cannot be exact from schema 1; stays Python. |
| `GET /api/conversations/<id>/thread/<root>` | `web/__init__.py:3684-3729` | Durable Turns, reply links and Turn views | No snapshot. The census `no` row is confirmed durable. |

### R5

| Route or worker read | Handler at `5f5170b` | What it actually reads outside the record | Gate result |
|---|---|---|---|
| `GET /api/references`; worker `find` | web references branch -> `Surface.find`, `worker.py:1800`; R3 `Resolve`/`turn_line` seams | Held/extracted source text and render engine; search may schedule missing extraction | No agent-run snapshot. Own through the shared text-scan op and the R2 extractor; a case requiring Python extraction scheduling forwards. |
| `GET /fluid/api/object-refs` | `fluid/__init__.py:129-143` -> `conversation/objectref.py` | R2 object extraction/held artifacts; no live registry | No snapshot. Python `fluid/objects.py` remains for its write-side and other callers through R7. |
| `GET /fluid/api/home/for-you` | `fluid/home.py:816` -> `fluid/status.py` | `derived/status.db`; may start `fluid-status-build` and reads status locks/places | Not a snapshot field. R5 must own the derived-status lifecycle or forward; it must not smuggle build state through `/private/live`. |
| `GET /fluid/api/document` | `fluid/__init__.py:145-148` -> `objects.document_text` | Held artifact bytes and extractor | No snapshot. |
| `GET /api/sources` and `GET /api/sources/<collection>` | `web/sources.py:199-206,256-258` -> `_row` | Binding state, `sources.runs._RUNS`, and extraction progress in addition to durable declarations/held files | Not snapshotable under the live contract; overview rows stay Python unless R5 defines a separate Sources progress boundary. |
| `GET /api/sources/<collection>/run` | `web/sources.py:253-254` | `sources.runs._RUNS` including progress, result, failure and cancel flag | Stays Python through R7 Sources; this is source-job live state, not `fields` material. |
| `GET /api/sources/folders`, `/compare` | `web/sources.py:208-213` | Bound machine folders/files | Machine read, not snapshotable; stays Python with Sources acquisition. |
| `GET /api/sources/search`, `/provenance`, `/page`, `/cite`, `/rendered`, `/record`, `/<c>/objects`, `/<c>/history`, `/<c>/links`, `/<c>/page` | `web/sources.py:215-251,260-276` | Record plus held/extracted files. `/cite` can schedule extraction; search uses extraction pending/cache state | No agent-run snapshot. Pure held reads can move; pending/scheduling cases forward unless R5 owns extraction lifecycle. |
| Worker `sources`, `source_history`, `source_links`, `read_source` | `worker.py:2046-2073` -> `sources.reading` | Record and held/extracted files only | No snapshot. Reuse the same source-read ops as the HTTP adapters. |
| Worker `search_sources` | `worker.py:2075-2081` -> `sources.search.search` | Held/extracted text plus extraction availability/pending state; can schedule extraction as P1.0 D2 records | No agent-run snapshot. Same scheduling rule as HTTP search. |
| Worker `check_rendering` | `worker.py:4169-4185` -> `conversation.render_check` | Process-local JS engine and bundle; a supplied timer `about=` is checked against the record | No snapshot. Reuse R2 `extract`; forward engine failures exactly as R2 does. |

### R6

| Route or worker read | Handler at `5f5170b` | What it actually reads outside the record | Gate result |
|---|---|---|---|
| `GET /api/work`, `/api/work/<id>`, `/api/owed` | `web/__init__.py:2106-2200` | Owner reads use `CurrentWork`; detail/non-owner reads use `_runtime_observation()` (`agents_runs` + `live_now`) and `SharedAnswers` | `run_observations` would cover runtime observation only. `CurrentWork` is not a field; R6 defect 1 decides ownership. Until then these stay Python. |
| `GET /fluid/api/home/work`, `/fluid/api/work` | `fluid/home.py:205-320` | Home collection reads `CurrentWork`; id reads `_runtime_observation()` | Same R6 decision; id reads may move after `run_observations` passes, collection cannot move by snapshotting the model. |
| `GET /fluid/api/home/activity`, `/fluid/api/runs` | `fluid/home.py:655-754` | Durable open/end acts plus `agents_runs()`; no `Conversations._executions` | Eligible only after `run_observations` passes. |
| `GET /fluid/api/home/briefing` | `fluid/home.py:756` | Durable returned work and Turn data | No snapshot. |
| `GET /api/working` | `web/__init__.py:3227-3272` -> `operational/runs.working` | Full form needs `agents_runs()`; `?count=1` is durable `cv.open_runs()` only | Count needs no field. Full form needs admitted `run_observations`. |
| `GET /api/activity` | `web/__init__.py:2750-2809` | `agents_runs()` plus `cv.active_executions()` and durable participant history | Cannot be exact from `run_observations` alone; stays Python while `Conversations._executions` is Python-owned. |
| `GET /api/conversations/<id>/work` | `web/__init__.py:3392-3404` | Recomputes work with `_runtime_observation()`; census measured 6,102 statements and found no Fluid caller | Do not add a field. Confirm no external caller, then delete rather than move; otherwise it awaits the R6 work-model decision. |
| `GET /api/context` | `web/__init__.py:4523-4592` | Composition from record and supplied inputs; context caches affect cost only | No snapshot. Reuse R3 ops/rules and R6 composition op. |
| `GET /api/conversations/<id>` (`?fields=`, full, and `?batch=0`) | `web/__init__.py:1358-1388,3731-3891` | `?fields=` is durable. Full view reads `CurrentWork` obligations; no direct run observation | Fields adapter needs no snapshot. Full view waits on the R6 work-model decision. `batch=0` must be characterized because the census did not. |
| `GET /api/conversations/<id>/governs`, `/origin`, `/orientation`, `/media` | `web/__init__.py:3409-3417,3575-3682` | Durable composition, held artifact descriptions and record data | No snapshot. |
| `GET /api/brain`, `?identity=1` | `web/__init__.py:2076-2086` | Identity reads manifest; full answer is durable orientation/composition | No snapshot. |
| `GET /api/personas`, `/api/intake` | `web/__init__.py:2462-2471,2512-2536` | Durable record only | No snapshot. |
| `GET /api/who/<id>` | `web/__init__.py:3161-3225` | `agents_runs()` for open runs and `st.agents.runtime_names()` from MARS backends | `run_observations` cannot cover runtime discovery. Keep the whole route on Python with R7 machine reads, or split only under an explicitly reviewed contract. |
| Governance library: `/api/kinds`, `/api/governance/authoring`, `/subjects`, `/api/governed`, `/fluid/api/governed`, `/fluid/api/governance/authoring`, plus `/history`, `/standing`, `/execution`, `/applies`, `/conditions`, `/deliveries`, `/questions`, `/since`, `/disputes` | `web/__init__.py:2560-2603,4359-4520`; `fluid/__init__.py:168-175` | Durable record; R3 already supplies shared `Kinds`, `Governed`, standing and act seams | No snapshot. Adapters must call shared ops rather than translate handlers. |
| `/api/operational`, `/api/entries/<id>`, `/api/history`, `/api/provenance`, `/api/gravity`, `/api/resurrect`, `/api/integrity`, `/api/space`, `/api/space/said`, `/api/neighborhood` | branches in `web/__init__.py` | Durable record; integrity verifies the chain; no run registry | No snapshot. |
| Ladder, anchor and timer GET families in `routes.md` | `web/ladder.py`; `web/__init__.py` anchor/timer branches | Durable record and held artifacts where returned | No snapshot. |
| `/fluid/api/layouts`, `/fluid/api/arrangements/<key>`, `/api/presentation`, `/api/presentation/scenes` | Fluid arrangements and presentation branches | Durable `presentation/` files and file locks | No snapshot; these files remain Python-owned until their write family moves. |
| `GET /api/context-cache` | `web/__init__.py:4347-4349` | Process-local `ContextCache.stats()` | Delete with `ContextCache` after its caller check; never snapshot cache statistics. |
| Worker `orient`, `recall`, `brief` | `worker.py:776-959,2143` | Caller policy (`permits`, participant/read scope) plus `ContextCache`; `brief`/orientation reads `CurrentWork` for outstanding work | Policy stays in the Rust door. Cache is optional. Composition can move, but outstanding work waits on the R6 decision. |
| Worker `work_overview` | `worker.py:961-1015` | `current_work._MODELS`, its maintainer thread and standing calculation | Not snapshotable. It moves only with the chosen R6 CurrentWork boundary. |

## Stalled-Python acceptance for a named field

For every field admitted later, the package adds the same cases to the live-freshness suite and to each dependent route's contract test:

1. A fresh snapshot containing the field gives the same status/body facts as Python; omission of the optional field is `NotOwned` and forwards, never an empty value.
2. Hold `/private/live` after a known field change. At age `>2 s` the dependent read forwards and never renders the held field. If Python cannot answer, the forwarded call fails as Python's call fails; Rust does not fall back to last known state.
3. Continue the hold past 10 s. The dependent read is 503/unavailable, while a durable-only sibling still answers. Recovery adopts the new field and causes one reread.
4. Kill Python, restart it with a new `boot_id`, send a lower generation, and send an unknown schema. Each discards the field exactly as the envelope contract says; no previous run state is shown as current.
5. Resume polling after idle. The first dependent read is stale/forwarded, not unavailable and not snapshot-served; only a good poll makes it fresh.

The tests use the existing proxy/stand-in technique from row K; they open a fixture Brain or copy only, never the live Brain. No new benchmark is part of this gate.
