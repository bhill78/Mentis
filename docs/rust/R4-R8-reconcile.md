# R4-R8 reconciliation and package order

This reconciles the remaining Python backend traced originally at `5f5170b`, and rechecked against merged main `c994047`, with R1-R3. It is a correction to package ownership, not a new architecture. [`P1.0-inventory.md`](P1.0-inventory.md) remains the detailed inventory; [`R4-R6-live-fields.md`](R4-R6-live-fields.md) is the live-state gate.

## Boundary after R3

| Responsibility | Rust owns now | Python still owns, and earliest removal |
|---|---|---|
| Front, static, pulse, topics/names | R1 public port, routing, static and durable pulse half | Private backend, sole writer, live snapshot producer; R8 except accepted earlier retirements |
| Post window/extraction | R2 window operations and extraction pool | `fluid/objects.py`, QuickJS/render check and write-side callers; R7 after transitive caller closure |
| Agent read door | R3 grant check and six read families | Quick Ask, stale/unknown grants, unowned cases, all writes; last R7 write family |
| R4 lists/views | Reusable record ops from R1-R3; admitted `active_executions` and `run_observations` overlays | Python produces the two optional fields until R7 owns their registries |
| R5 held/source reads | R2 extraction and R3 resolve/Turn/standing foundations | Extraction scheduling, Sources `_RUNS`, machine bindings, For You and all `derived/` writers; R7 at earliest |
| R6 composition/work | R3 composition primitives and the admitted live overlays | `CurrentWork`, stage/git and machine discovery; split movable composition/work in R6, unresolved parts R7 last |
| Agent execution | Snapshot consumer only; no execution ownership | MARS ACP, feeds, permissions, dispatch, results, grants; R7 last and together |
| Writes | None | Python sole Brain writer; W0 and owner-approved recovery remain prerequisites |
| Durable files outside SQLite | Read-only use where a package names it | Python owns `artifacts/`, `presentation/`, `instances/`, bindings and `derived/` writers until their write family moves |

For You and its rebuild thread remain on Python until the owner rules on Rust `derived/` writes. R5 writes nothing under `derived/`. P1.0 rows B2, B3, C4, D2, D3, E20 and E21 now say that explicitly.

## One retirement check

Every package uses the same check before retiring a Python handler, helper, memo, route or module:

1. Start at the public or worker handler and enumerate its transitive callees.
2. Search callers and dynamic route/op references across `mentis/`, `tools/`, `tests/` and `apps/`, not only direct imports.
3. Count the forward path as a caller: stale/absent optional live fields, `NotOwned`, unknown/stale grants, Quick Ask and compatibility forwarding keep the Python path alive even when text search finds no Rust caller.
4. Record every remaining caller and why it remains. Delete only when the closure is empty on the accepted DAY-TO-DAY release; Python deletion follows owner acceptance.

This catches `_read.conversations` reached through `fluid/commands.py`, and covers `_conversation_rows`, `conversation_summaries`, `asking_owner`, `_ask_rows`, `decisions_read`, `_turn_view`, `_expectation_view`, `_live`, `live_by_conversation`, `expectation_state`, `_POLLED`, source/search helpers and all package-specific names. It also governs the proposed deletion of `/api/conversations/<id>/work` and `/api/context-cache`.

## Ordered packages

R4.1 restores the approved order. Fluid conversation activity/ids cost 1,047-1,475 statements in the census and now have both fields their `_live()` branch needs. The gate measurement shows the added producer cost is below 1 ms p95 at the copied record's realistic 40-64-row run registry and 0.0727 ms p95 at a 3,600-entry execution registry; the route's record work, not the live overlay, remains the bottleneck.

R4.1 first builds the seam R4.2 consumes: both Python snapshot producers, `ActiveExecution` and `RunObservation`, a new full-width durable `expectation_states` operation (not reuse of the narrower `forms.rs:5` decision-form read), the raw durable/overlay merge using the exact/fallback rule at `conversation/__init__.py:3732-3738`, and the poll-position/read-position coherence marker. Once the seam emits both fields from real Python and is verified, the rest of R4.1 and R4.2 can run in parallel. A fresh overlay is still unusable when it changes the answer but its poll marker predates the durable position used by the read, or has no marker; those cases forward.

| Order / package | Scope and shared interface | Done evidence and Python that stays | Review |
|---|---|---|---|
| 1. **R4.1 conversation, expectation and participant lists** | First build the shared seam above, including both real Python producers. Then build Fluid conversation activity/ids, `/api/conversations`, Home needs-you, needs-you items/detail, both participant lists, and the six unplaced durable Fluid reads: collections stream/selection, latest, changes, anchors and response sets. Reuse `conversation_rows`, participant and existing R2 collection ops. | Exact live/durable parity, the 1,047-1,475-statement route evidence, per-field/total timing and byte caps, atomic-copy proof, forward rate under load, stalled/absent/incoherent-field forwarding and universal retirement closure. Coherence fixtures cover an end landing while a poll is in flight, a moved record whose overlay changes nothing, and the correcting reread after the `end_execution`/durable-end window. Shorten `_POLLED`, but keep R6 callers. **Adding both fields and shortening `_POLLED` requires a Python restart.** | Independent review: high-fan-out shared list and live shapes. |
| 2. **R4.2 Turn and expectation views** | After R4.1's real Python producers and shared seam, `/api/turns/<id>`, batched Turns, thread view, decisions, `/api/personas`, `/api/intake`, and the durable `fields=` forms of `/api/conversations/<id>` can build in parallel with the remaining R4.1 work; the raw state unions durable `instance_id` refs and overlay boundary refs, while `_expectation_view` emits `bool(union)`. Decisions are here, not R4.1, because `decisions?post=` uses `_turn_view` and `decisions?ids=` shares `_expectation_view`. | Exact route boolean parity; the two running-dispatch refs are asserted only in raw `owed` rows and the POST `expect` answer. Also test intake's liveness branch, held-avatar cost and absent/stale/incoherent overlay forwarding. A durably open run whose overlay adds only its second ref leaves the boolean unchanged and need not forward. Full Conversation is not claimed: its `owed` block still reaches `CurrentWork`. | Independent review: shared Turn/provenance/deletion shape. |
| 3. **R5.1 references and object reads** | `/api/references`, worker `find` identity/text preparation, `/fluid/api/search`, object refs and document, plus worker `check_rendering`; reusable identity/text and object/engine interfaces. | Completed held inputs match ordering/ambiguity/bytes. Conversation search reports cost as Conversation size grows. `find` content hits depend on R5.2's source scan or forward. Extraction scheduling and render engine write-side callers forward/stay Python. | Independent review: held bytes and engine boundary. |
| 4. **R5.2 source reads and search** | Sole owner of the shared source scan used by `sources.search.search`, HTTP `/api/sources/search`, worker `search_sources`, and `find` content hits; also `/api/sources/cite`, provenance/page/rendered/record/object/history/links/page and worker sources/history/links/read. Shared source-read/search result types. | Citation/continuation/provenance parity. Until the scan is present, `find` content-hit cases forward. Missing extraction, pending/scheduling and every `derived/` write forward. Overview, run, folders and compare stay Python because they expose Sources job/machine state. | Independent review: citations, reach and extraction provenance. |
| 5. **R5.3 deferred For You** | No Rust route in R5. `/fluid/api/home/for-you`, status database, rebuild thread and status places remain one Python responsibility. | Explicit forward tests and corrected inventory. It moves only after an owner ruling and the later owning package; nobody writes `derived/` from Rust in R5. | Review when ownership is actually proposed. |
| 6. **R6.1 composition** | Conversation- and brain-scope `/api/context`, both `/api/brain` forms, Conversation governs/origin/orientation/media, and worker orient/recall; one composition interface over R3 ops, adding `active_executions` where Python renders it, with caller policy at each door. R6.1 may build `brief`'s composition foundation, but the operation keeps forwarding until R6.2 owns its outstanding block, or R7 if defect 1 keeps `CurrentWork`. | Components/tiers/withheld/door parity. Brain orientation applies the coherence rule before rendering `RUNNING`. Python worker recall computes but does not return its untiered live orientation component; Rust may skip that computation only while preserving its durable withheld row. `/api/context-cache` deletes only after universal closure. | Independent review: governance/dispatch foundation. |
| 7. **R6.2 work decision and movable work surfaces** | Defect-1 boundary; home activity, home briefing, brief outstanding block, work/owed/home-work/work-overview, `/fluid/api/runs`, full `/api/working` and `/api/activity`. | Home activity/briefing move durably; runs/working/activity use the two admitted fields and merged expectation state. Work detail/ids, full Conversation, CurrentWork surfaces and conversation-work remain Python unless defect 1 and stage/git dependencies are owned. Remove `_POLLED` only after closure; **that removal requires a Python restart**. | Review before build: process boundary and live work truth. |
| 8. **R6.3 durable long tail** | Operational/history/provenance/gravity, governance, ladder, anchor and timer GETs, `/api/resurrect`, `/api/entries/<id>`, integrity, space/said/neighborhood, `/fluid/api/settings`, layouts/arrangements and presentation/scenes reads. Group by record or file interface. | Route contract and cost evidence, including held-file stat/hash and presentation locks. Timer GETs are durable; the `expectation_state` call is POST-only authority. Settings and presentation readers remain while their write families remain. | Review shared governance/record primitives; thin adapters need contract verification only. |
| 9. **R7 last live/machine group** | Full Conversation and every defect-1 `CurrentWork` surface still retained; `/api/who`; work detail/ids/stage; MARS, git/deployed-commit and stage `_FAILED`; and the R7 execution families. | Own `CurrentWork` if deferred, run/MARS, `agents_list`, stage/git and machine truth together, then apply universal retirement closure. The two snapshot registries are consumed earlier but ownership transfers here. | Independent review: foundational execution/live transfer. |

`/api/sources`, `/<collection>` overview, `/<collection>/run`, folders and compare stay on Python through the R7 Sources family because they expose Sources `_RUNS`, acquisition or machine bindings. `/api/who/<id>` stays in R7 because it uses `agents_list`, `agents_runs` and MARS runtime discovery. `/api/server` stays until R8.

The Magnet conversation POST reaches `_conversation_projection`, `_read.conversations`, `_live` and `live_by_conversation`. Those two live helpers cannot retire before that POST's Fluid-command write family moves. `workspace_manifest.py` adds no HTTP route. At R8, when Python no longer exists to receive `magnet_read`'s no-definition forward, Rust answers the same 404 directly so the client continues to use its store path.

## Restarts and owner qualifications

“No new owner decision” is true only for beginning packages whose completion does not cross these boundaries:

1. Any snapshot-field or `_POLLED` edit restarts Python and therefore returns to the owner under the standing front-only deployment authorisation. **R4.1** adds both fields and shortens `_POLLED`; **R6.2** eventually removes `_POLLED`. Those are the R4-R6 package done criteria that include a Python restart. The other packages consume the fields from Rust and do not add a restart merely by doing so.
2. Both fields pass the measured gate, so the earlier R4 package order is restored and there is no departure-from-plan qualification to confirm.
3. Any Rust write to `derived/` needs an owner ruling. Keeping For You, extraction scheduling and rebuilds on Python avoids making that choice here; the ruling remains open.
4. Python deletions occur only after owner acceptance of the corresponding DAY-TO-DAY release, as P1.0 already requires.

Defect 1 remains open: whether Rust owns a single `CurrentWork` projection while Python still owns runs/writes, or whether the thread and every dependent route remain Python until R7 last. Snapshotting `CurrentWork` is not an option. Existing W0 write/recovery decisions also remain reserved; this correction does not choose them.

## Findings F1-F9

| Finding | Correction |
|---|---|
| F1 | Replaced “drop `live_execution`” with its actual two-source raw-state rule: Rust computes durable open-run refs and unions the active overlay. `_expectation_view` routes emit `bool(union)`; only owed rows and the POST `expect` answer expose the reference list. Audited needs-you and other durable branches rather than relying on omitted JSON keys. |
| F2 | Full Brain and brain-scope context are live-dependent; identity and Conversation-scope variants remain durable. |
| F3 | Kept home activity durable; restored runs/working/activity when both measured fields suffice; left who, work detail/ids and full Conversation behind their independent MARS, `CurrentWork`, stage/git and `_FAILED` blockers. |
| F4 | Re-evaluated `active_executions` from the copied Brain and real-class JSON timing. It passes the 10 ms p95 budget through 100,000 retained entries; the R4 order and 1,047-1,475-statement evidence are restored. Documented removal versus a separate active map and repeat-end behavior. |
| F5 | Assigned every dropped route/op, including `/api/conversations/<id>?fields=`, cite, briefing, personas/intake, context-cache, check-rendering and the six earlier Fluid reads; machine/job routes explicitly stay Python. |
| F6 | Moved decisions to R4.2, gave the shared source scan to R5.2 with `find` content hits depending on it or forwarding, and kept `brief` forwarding until its outstanding block moves in R6.2 or R7. |
| F7 | Kept For You and rebuild/extraction `derived/` writers on Python; corrected P1.0 B2, B3, C4, D2, D3, E20 and E21; placed the new Fluid search/settings reads and Magnet/settings writes; and recorded the Magnet helper retirement and R8 404 rules. |
| F8 | Confirmed `_runs` is structurally active + 32 ended, corrected named-member JSON evidence (0.98 ms/about 73 KB at 64 rows; 9.95 ms/about 685 KB at the 1,032-row limit), copied named members instead of locking every mutation, and read MARS's local `running()` directly. Kept agents-list, stage/git/`_FAILED` and held-file gaps separate. |
| F9 | Replaced package-specific one-level searches with one transitive closure across `mentis/`, `tools/`, `tests/`, `apps/`, counting forwarding as a caller. |

## Trace completion

The correction opened the R6.3 long-tail handlers and the cited R5, `_avatar`, `owner_of` and `asked_with` callees. Every remaining “No snapshot” row was rechecked for `_executions`, `active_executions`, `agents_list`, `agents_runs`, stage git/deployed commit, `_FAILED`, and held-file stats. It then traced branches at every durable `expectation_state` caller: needs-you and decision openness ignore liveness; intake and work delegation do not. No row remains marked durable merely because its JSON omits the live key. File-stat/hash and process-local engine costs are called out separately rather than mislabeled as live state.
