# Execution, Accountability and Coordination Modernization — shared contract

Source: the 2026-11-10 investigation ("Mentis Execution Independence & Authority
Boundaries", sections 1–11). The owner has authorized the three priorities below. This file
fixes the **interfaces between workstreams** so they can be built in parallel and merged onto
the `modernize` branches of Mentis and MARS. If a builder finds that the contract cannot hold,
it records the deviation under "Deviations" at the end of this file, in its own commit, and says
so in its report. It does not silently change a shared interface.

Ground rules for every workstream:
- Never touch DAY-TO-DAY (:8760/:18760, `C:\Work\Mentis-dayday`, `C:\Work\MARS-dayday`,
  the live Brain), the Quiet Chat Mark 2 dev environment (:8790, :5190,
  `C:\Work\Mentis-wt\quiet-mark-2`, branch `quiet-mark-2`), or `apps/fluid-web/src/quiet*`.
- No new persistent Brains, Brain copies or servers. Tests build their own fixtures in the
  default temp folder. Do not set a custom TMP or `--basetemp`, and do not set PYTHONPATH,
  MENTIS_SERVER or CLAUDE*/CODEX* variables while testing.
- Run focused tests only (`.venv` python: `C:\Work\Mentis\.venv\Scripts\python.exe -m pytest
  tests/<files> -q -p no:cacheprovider`). Run no full suite. That gate runs once, on the
  integrated candidate.
- Do not change existing authority rules except where this contract says so. Never widen.
- An execution ending never completes work by itself.

## WS-C — Completion and accountability (Priority 1)

**States.** These are four distinct facts, and none implies another:

| Fact | Recorded as | Who writes it |
|---|---|---|
| Execution ended | `result-returned` / `result-recovered` / failure acts (exist) | Mentis dispatch, from MARS facts |
| Agent claimed an outcome | **new act `outcome-claimed`** | The agent, via its final reply (or `respond`, `record_outcome`) |
| Objective recorded met | `expectation-met` (exists), now with `detail.reconciled_from` = the claim act | Mentis reconciliation |
| Independently verified | `review-verdict` with verdict `pass` (exists, `operational/stage.py`) | A reviewer |

**Structured outcome in the final reply.** No extra call is needed. Every dispatched run, in
any scope (worker, organising, intake, delegated child), may end its final reply with a fenced
block:

    ```outcome
    result: met            # met | partly | not-met
    summary: one line saying what was done or not done
    evidence:
    - commit 1a2b3c4 on branch x
    - tests: tests/test_y.py 12 passed
    - ent-… / opr-… / path / URL
    ```

- Parse it leniently: the key order is free, `evidence` is optional, and unknown keys are kept.
  The block is removed from the posted reply text, and a one-line rendering is added instead.
- `respond` gains an optional `outcome` argument with the same shape (`{result, summary,
  evidence[]}`). `fulfils: true` keeps working and means `result: met`.
- `record_outcome` for sessions maps `done` → `met`, `partial` → `partly`,
  `blocked`/`failed` → `not-met`, and keeps its existing behaviour otherwise.
- A claim can be made **only about the claimant's own assigned expectation** (the run's
  `expectation` or the session's `under`). Making it requires no organising or `coordinate`
  authority. It confers nothing, launches nothing and establishes nothing.

`outcome-claimed` detail: `{result, summary, evidence[], claimed_by: <execution>, runtime,
participant, via: "reply"|"respond"|"record_outcome", reply_turn}`. `about` = [expectation].

**Reconciliation** (new module `mentis/operational/completion.py`, function
`reconcile(cv, expectation, claim_act) -> {"recorded": "met"|"pending"|"not-met"|"partly",
"reasons": [..]}`). It runs when a run ends (dispatch) and after a `respond`/`record_outcome`
claim. A claim of `met` becomes `expectation-met` (`detail.reconciled_from=<claim>`,
`detail.claimed_by`) only when:
1. the latest execution under the expectation ended normally (no failure or cancel after the claim);
2. no decision or input the work asked for is open (the existing `fulfils` refusal rule);
3. no delegated child the work declared it waits on (`return_to_me`/`await_work`) is still
   unended. Children that ended unmet are listed as reasons (`child <id> not met`). They do
   not block automatically unless the parent declared that it waits on them;
4. the work's Workflow does not require review before completion. If it does, the claim
   stays `pending` with reason `review required`, and a later `review-verdict pass` reconciles it.

Otherwise reconciliation writes **`outcome-pending`** (detail `{claim, reasons[]}`). A
`partly`/`not-met` claim is recorded as it stands and never becomes met. Reconciliation is
idempotent: a second run over the same claim writes nothing new.

**Parent and child.** A child expectation is met by its own reconciled claim. A parent is
never met because its children are, and its children are never met because it is. Work
overview shows a child as "Returned to <parent carrier>" when it ended unclaimed.

**Work-overview states** (`operational/work.py`, `work_overview.py`, `stage.py`, `runs.py`):

| Value | Words (exactly) |
|---|---|
| `claimed-met` (existing value, now only reconciled) | `Objective met · claimed by <who>` |
| `verified` | `Verified · <reviewer>` |
| `claim-pending` | `Claimed met · pending: <first reason>` |
| `claimed-partly` | `Partly done · <summary>` |
| `claimed-not-met` | `Not done · <summary>` |
| `returned` (no claim) | `Ended · no outcome claimed` |

A run ended by `result-returned` is the run state `ended` (words `ended · <time>`). It is not
`completed`. The stage word for ended, unmet work is not "Answered". Fluid CSS inks
`--ok` only for `claimed-met`/`verified` work. Run badges for ended runs are neutral.
Quiet Chat is not changed: interface changes are documented in
`docs/modernization/QUIET-CHAT-INTERFACE.md`.

**Linking later findings.** `record_material`, `record_discovered_work`, `contribute` (WS-I)
and `challenge` accept an optional `regarding: [ids]` (expectation, claim act or Turn).
Mentis writes a link of kind **`regards`** from the new record to each id. It is neutral:
nothing is reopened or blamed. Work overview exposes `later_findings: [{id, kind, at}]` per
work item. The original claim, evidence and later findings are never rewritten.

## WS-P — Execution performance and session continuity (Priority 2)

**Timing spans.** Mentis writes `detail.timing` on the `execution-started` and
`result-returned` acts: `{triggered_at, selection_started, selection_done, started_recorded,
perform_called, session_opened, prompt_sent, first_event, last_event, ended}`. All values are
epoch seconds. MARS returns `_meta["mars/timing"]` on the `session/new` result: `{spawn_ms,
initialize_ms, new_session_ms, load_ms, resolve_ms}`. Mentis copies it into `detail.timing.mars`.

**Capacity off the critical path.** Selection uses the newest capacity view already held and
never waits for a fresh one on the dispatch thread (`CAPACITY_WAIT_S` wait removed from the
path). A background refresh keeps the view current. Quota semantics stay as they are: holds
from the record, and defaults yield. Mentis caches `mars/backends` and invalidates the cache
on MARS restart or after 60 s.

**Adapter spawn.** MARS resolves the ACP adapter command once, to an installed binary or
script, and spawns it directly instead of `npx --yes` on every session. It falls back to npx
when resolution fails.

**Session continuity.** The protocol between Mentis and MARS:
- The `session/new` result `_meta["mars/resume"] = {"token": "<opaque>", "supported": bool}`.
  The token identifies the runtime's own session (for example the Claude Code session id) plus
  the backend id.
- Mentis records `detail.runtime_session = {token, backend}` on the run's end act.
- On a continuation (`resume_if_ready` → resumed dispatch) of the **same expectation, same
  participant, same backend**, Mentis sends `session/new` with
  `_meta["mars/resume"] = {"token": ...}`. MARS tries to load that runtime session (ACP
  `session/load` where the agent advertises `loadSession`, otherwise the runtime's resume
  mechanism; for agy, its `--conversation` id). It answers `_meta["mars/resumed"] = {"resumed":
  bool, "why": str}`. MARS keeps no extra processes alive between runs.
- If resumed, Mentis sends a **continuation prompt**, not the full composition. It holds the
  resume notice, everything new since the previous run (owner follow-ups, children's
  results, decisions answered), **and always** the current authority line, consent summary and
  the closing block. Follow-ups that the owner added after the run began are shown exactly as
  today (`follow_ups_unseen`). If not resumed, Mentis sends the full composition, as today.
- A changed Workflow, a revoked or narrowed grant or consent, a withdrawn request, or a
  different runtime, model or participant forces a fresh session.

## WS-A — Permission enforcement (Priority 2)

1. **Replay (experiment E3).** `tools/permission_replay.py` reads a Brain **read-only**
   (sqlite `mode=ro`), reconstructs each recorded `operation-answered` request with its
   run's consent, and evaluates it both with the current policy (pure functions: `operations.
   describe`, consent, `standing_answer`) and with the compiled runtime rules. It reports
   agreement, disagreements by direction, and per-category counts. The backup to use is
   `C:\Work\Mentis-brains\pre-eff-cbfabaa-20261108\corpus.db`.
2. **Compiled scope.** Mentis computes `_meta["mars/consent"]["runtime_rules"] = {"allow":
   [...], "deny": [...]}` in the runtime's own rule syntax (for Claude: permission rule strings
   such as `Read(//c/Work/x/**)`, `Edit(...)`, `Bash(git status:*)`, `mcp__mentis__*`). MARS
   applies them only for runtimes listed as supporting it, through the runtime's own
   enforcement. A rule is emitted only for an operation class where the replay shows the
   compiled verdict equals Mentis's verdict. Anything else still reaches Mentis as today.
   Enabled per runtime by `mentis/web/permissions.py COMPILED_SCOPE_RUNTIMES` (default: the
   runtimes for which the replay passes; empty if none passes).
3. **Audit off the critical path.** The `operation-answered` record for an automatic answer
   (grant/all/task) is written through a background, ordered write-behind queue, flushed at run
   end. Owner answers and refusals stay synchronous. Operations allowed by compiled rules are
   audited from the MARS event stream at run end (`detail.audit` on the end act: counts and
   the tool calls by kind).
4. Never broaden: a compiled rule set must be a subset of what the current policy allows
   without asking.

## WS-I — Independent contribution, identity and refusals (Priority 3)

- **Identity.** A hand-started session is bound to a participant of its own, not the shared
  @ManualSession. The bridge passes `--participant <alias or ent->` (optional) and a host label.
  Default: one participant per runtime and host (alias `<Runtime> CLI · <HOST>`), created on
  first use as an ordinary participant described as "an independently launched CLI agent".
  Acts record `written_by` as today, plus `detail.host`.
- **Authorization source, recorded separately.** Every session write may carry
  `authorized_by` = `{"source": "owner-in-chat"|"request"|"none", "note": str, "request":
  id|null}`, stored as `detail.authorized_by` and distinct from the actor (the executor).
  `record_request` stores it as well, so a session's request records "authorized by the
  owner in chat; executed by <session participant>".
- **Default authority.** A session without a carried request holds READS, SOURCE_READS, the
  contribution ops (`record_material`, `propose_material`, `challenge`, `contribute`),
  `open_conversation`, `record_request` and its own claim ops. `coordinate` and the
  coordination ops (`delegate`, `summon_participant`, `attach_follow_up`, `change_workflow`,
  `resume_intake`) require `under=<request the session recorded>`. This narrows authority and
  never widens it.
- **New op `contribute`** (any session, no request needed): `{kind: "finding"|"problem"|
  "observation"|"proposed-work", text, evidence[], regarding[], authorized_by}`. It records an
  attributed, `stands: False` contribution in the owner's **Contributions** conversation
  (created once per Brain). `proposed-work` additionally records an **unassigned,
  owner-addressed** expectation with no parent. Nothing is dispatched or established. Owner
  adoption stays the only path to standing.
- **Explainable refusals.** `NotPermitted` gains structured fields: `op`, `boundary`
  (`lineage`|`scope`|`coordination`|`governance`|`place`|`ownership`|`validation`|`resource`),
  `why`, `recovery` (a list of supported next calls), `who` (who can lift it). The worker and
  bridge render all of them. At least every refusal in the investigation's table (section 5)
  is converted, and the incident's refusal names `contribute` and `record_request` → `under`.
- **Durable reporting.**
  - Every write op accepts `op_key` (a client-generated id). The server deduplicates per
    (grant participant, op, op_key) and returns the original result on repeat.
  - The bridge generates op keys for write ops and keeps an **outbox** (JSONL under
    `%LOCALAPPDATA%\Mentis\outbox\<participant>.jsonl`). A write whose answer was lost is
    resent on the next call or start. Entries are removed once acknowledged.
  - The dispatch-side final-reply claim (WS-C) is server-side and needs no outbox.

## WS-L — Shared-resource coordination (Priority 3)

- New module `mentis/operational/leases.py` and ops `claim_resource`, `release_resource`,
  `resources`.
  - Arguments: `kind` is `worktree`|`path`|`port`|`service`. `name` is a normalized path,
    port number or service name. Also `mode` (`exclusive`|`shared`), `ttl_s` (default 1800,
    max 14400) and `purpose`.
  - Acts: `resource-claimed`, `resource-released`. A lease belongs to (participant, execution).
- A conflicting exclusive claim is refused with a structured refusal (`boundary: resource`)
  naming the holder, its purpose, since when, its expiry and the recovery (wait, ask the
  holder, use another worktree or port). Shared claims coexist. Nested paths conflict with a
  containing exclusive claim.
- Leases end at the holder's run end (dispatch end hook) or at TTL expiry. Sessions renew
  by claiming again. An expired or ended lease never blocks.
- Dispatch tells each run, in its prompt, which **other live** runs hold leases inside its
  workspace. It does not refuse the run. Unrelated work is never serialized: claims check only
  overlapping resources.
- These ops are in every dispatched scope and the session scope. Claiming confers no other
  authority.

## Deviations

### WS-L (branch `mod-leases`)

- **WS-L, refusal shape (interim).** WS-I's structured `NotPermitted` is not on `mod-leases`.
  A conflicting claim raises the existing `worker.NotPermitted` whose message states holder,
  purpose, since, expiry and recovery, with the fields in a dict attribute `refusal`
  (`op`, `boundary: "resource"`, `why`, `recovery[]`, `who`, plus `holder`, `lease`,
  `resource`, `mode`, `purpose`, `since`, `expires`) and `op/boundary/why/recovery/who` also
  set as attributes. The integrator maps `refusal` onto WS-I's fields; the HTTP door does not
  serialize it yet.
- **WS-L, lease end.** Besides `resource-released` and TTL, a lease taken in a dispatched run
  (its `detail.run` is the run's `execution-started` act) also stops holding once that run has
  an end act (`run_end`), so a lease whose end hook never ran (server stopped) never blocks.
  A session lease (`detail.session`) ends when its session ends (`/api/session/end` releases
  it, reason `session-ended`), and stops holding once `manual-session-ended` is recorded for
  its execution or no live session grant names it (grants are in memory, so after a restart it
  holds again only if the session continues as the same execution). Only the holder --
  same participant AND same execution -- releases; a sibling session of the same participant
  is refused with a structured refusal naming the holder execution (review fix).
- **WS-L, `name` normalization.** Paths must be absolute; Git Bash `/c/...` equals `C:\...`.
  `\\?\` and `\\.\` prefixes and trailing dots/spaces per component are dropped; on Windows
  `os.path.realpath` resolves junctions, symlinks, subst and 8.3 names for the part of the path
  that exists (not for UNC paths); the rest is compared lexically.
  `worktree` and `path` share one namespace, so a path inside a claimed worktree conflicts.
  `resources` is in `READ_ONLY` and accepts optional `kind`/`name` filters.
- **WS-L, shared lists touched.** Adding the three ops changed `permitted` (Python and the
  Rust mirror `crates/mentis-rules/src/permitted.rs`), regenerated
  `tests/front/permission_matrix.json`, and the agent-write list in
  `docs/rust-front-restart.md` / `tests/front/test_restart.py` (28 → 30 writes; both new
  writes listed as guarded). WS-I's `contribute` touches the same lists: regenerate the
  matrix after merging both.

### WS-P (Mentis side, branch `mod-perf`)

1. **Capacity, cold start.** Selection never waits once any capacity answer is held, whatever
   its age; an answer older than `CAPACITY_REUSE_S` has a newer one read in the background. A
   process's *first* selection, with nothing held, still waits up to `CAPACITY_WAIT_S` (there is
   no view to use). Dispatch calls `MentisService.capacity_prime()` as it begins, so that read
   overlaps the record reads before selection.
2. **`mars/backends` cache.** Kept only for an execution that exposes `generation` (the
   `MarsExecution` process counter, incremented on every `mars stdio` start, which is how a MARS
   restart is noticed). Fakes without it are not cached. **Instead of invalidating after 60 s or
   on restart, a held catalogue is served whatever its age** and refreshed in the background
   once it is 45 s old or from a replaced MARS process; only a service that never held one waits
   (live experiment: the first dispatch after ~2 min idle spent ~8 s re-asking the list while a
   gemini probe timed out). `MentisService.keep_current()`, called at server start, primes the
   catalogue and capacity and keeps them current while idle (catalogue every 50 s, capacity
   every 5 min); it stops on `close()`. An empty answer is never kept.
3. **`runtime_session` carries more than `{token, backend}`:** also `supported` and the terms the
   session was opened under (`participant`, `model`, `context` = the binding's governing
   fingerprint, and tags of the authority, consent and Workflow-change line). A continuation
   asks for the token only when all of them are unchanged, so besides the contract's list a
   change of governing material also forces a fresh session, and *any* change of authority or
   consent does (widening included), not only narrowing or revocation. Only a previous run
   that ended `result-returned` is resumable.
4. **Continuity outcome** is recorded on the end act as `detail.continuity = {asked, resumed,
   why, decided}` (continuations only). A resumed run's delivery record uses mechanism
   `resumed-session` instead of `dispatch`.
5. **Timing** additionally holds `dispatch_began`, `steps` (each step before selection and
   between the start and the perform), and the boundary's `loop_entered` and `connected`.
6. **Continuation prompt** = resume notice, the resume text as the task (owner follow-ups,
   children's results, decisions and inputs), the render-check note when one is owed, the
   current authority line (scope, organising operations, Workflow-change line), the consent and
   research lines, and the closing block, last. It does not resend the condensed governance,
   reply format, artifact offer or referenced posts, which the resumed session already holds.
7. **WS-P / MARS: token timing for per-turn backends.** A backend that runs one process per
   turn (agy) knows its conversation id only after a turn, so MARS answers `_meta["mars/resume"]
   = null` on the `session/new` result and gives the token on each `session/prompt` result's
   `_meta["mars/resume"]` (token format `mars1.<hex backend>.<hex runtime id>`). ACP backends
   (claude, codex) give it on `session/new` only. `MarsExecution` reads both and keeps the
   prompt result's token when there is one. MARS's `mars/timing` also carries `total_ms` and
   `adapter` (a string); Mentis copies numeric and string values into `timing.mars`.

**WS-C (mod-completion), recorded by its builder:**

1. **Rule 1 while the run is still going.** A claim made while its run is still in progress
   (`respond(fulfils|outcome)` during the run) is recorded `outcome-pending`, with the reason
   `its run has not ended yet`. Dispatch reconciles it again when that run ends. Before this
   change, `respond(fulfils)` wrote `expectation-met` at once. When the run ends, dispatch
   reconciles only the newest claim, and only if this execution made it. A newer run that
   ends without claiming never turns an older claim into met.
2. **Rule 4 has no machine-readable flag to read.** No Workflow field says "review required".
   Review is therefore required when a Workflow named by `governed_named(expectation)` has an
   activity that `stage.is_review` reads as review: its `who.persona` name says review, or its
   `what` / `key` opens as a review. Two kinds of request are exempt: review work itself (by
   its Persona, by `repository.review_of`, or by its brief), and a request that is itself one
   activity of a Workflow (`activity_named`). The rule is satisfied when the newest
   `review-verdict` is `pass`. That verdict may sit under the work, or on a request declared
   `review_of` it. `record_verdict` with `pass` calls `completion.on_review_pass`, which
   reconciles the claims up the reviewer's lineage and its `review_of` target. `stage.py`'s
   `awaiting_review` is git-derived, so it is not used for this rule.
3. **What `reconcile` returns.** It returns `{"recorded", "reasons", "notes", "act"}` and, on a
   no-op, `"already": True`. `notes` holds the non-blocking `child <id> not met` entries.
   These are also written on the met / pending act's `detail.notes`.
4. **Who the met act is attributed to.** The reconciled `expectation-met` is attributed to the
   claimant, with `detail.reconciled_by: "mentis"`. Existing readers ("met by its carrier",
   imported-spine rules) keep working. `outcome-pending` is attributed to `mentis`.
5. **`record_outcome` accepts more results.** It now also accepts `blocked` and `failed`
   (→ `not-met`). `abandoned` → `not-met`. Behaviour is otherwise unchanged, except that
   `fulfilled_by` is now the reconciled met act, or null while the claim is pending.
6. **A failed run's block is not a claim.** An outcome block in the final text of a run that did
   not end `reported_done` is not recorded as a claim. Rule 1 would refuse it anyway, and
   failed runs post no reply.
7. **The `regards` relation is defined lazily.** It is defined on first use in
   `completion.link_regarding`, not added to the conversation vocabulary list. The ids are
   checked: each must be an expectation, an `outcome-claimed` act, or an existing entry such
   as a Turn. At most 20 are allowed. A refusal writes nothing.
8. **Extra fields beyond the contract.** Work items also carry `claim` (the newest claim and
   what was recorded of it). `verified` requires the work to be recorded met, with the newest
   review verdict under it a `pass`. Stage words: met work reads `Objective met`, where it
   used to read `Answered · objective met`.

### WS-I (mod-contrib)

- **D-I1: Default alias.** Participant aliases are limited to ASCII letters, digits, `-` and
  `_` (opr-938e0fa58007). `<Runtime> CLI · <HOST>` cannot be an alias, so the default is
  `@<Runtime>-CLI-<HOST>` (for example `@Claude-CLI-WORKSTATION`). The readable form is kept
  in the Participant's `about`, together with "an independently launched CLI agent". A session
  may not be bound to the owner's Participant. The session route takes `participant` and
  `host` in its body, and the bridge sends them (`--participant`, `--host`).
- **D-I2: How the narrowed default is enforced.** The coordination ops (`delegate`,
  `summon_participant`, `attach_follow_up`, `change_workflow`, `resume_intake`) stay *listed*
  in `permitted(SESSION_SCOPE)`. Without `under` they are refused at the operation
  (`boundary: coordination`). They are not removed from the list, because `under` is a
  per-call fact and `permitted` is per grant. This also keeps tools/list and the Rust parity
  matrix unchanged. Kept in the session scope as before: `open_topic`, `deep_dive`,
  `anchor`, `react` (they act only in Conversations the session opened, coordinate nobody and
  confer nothing), `request_adoption`, `withdraw_challenge`, and `record_discovered_work`,
  `take_up` and `record_outcome` (these already need carried work). `contribute` joins
  `SESSION_ACTS`. `crates/mentis-rules/src/permitted.rs` and
  `tests/front/permission_matrix.json` are updated to match.
- **D-I3: Continuity across session identities.** Before WS-I every session was
  @ManualSession, so any later session could carry, continue and close a request that an
  earlier session recorded. To keep that, a request recorded by *any* session participant is
  carryable (`under`, `record_outcome`, `change_workflow`, `parent`) by any session
  participant (`worker._session_side`). It is not carryable by anybody else. This is exactly
  the old reach, with nothing added.
- **D-I4: `contribute` is a session op.** Dispatched runs are not given it. They have
  `record_discovered_work` and the ladder.
- **D-I5: An `observation` writes the contribution Turn only.** No seeded Kind fits: `note`
  is "not an observation", and `source-material` is a connector's. `finding` and `problem`
  also record ladder material of that Kind.
- **D-I6: `regarding` before WS-C.** `contribute` stores `regarding` in the contribution act's
  `detail`. It calls `mentis.operational.completion.link_regarding` when that module exists
  (marked `TODO(WS-C integration)` in `operational/contribution.py`). The other ops' `regarding`
  is WS-C's.
- **D-I7: Where `authorized_by` and `host` are written.** They are written on *every* act of a
  session call, by a context-scoped annotation that `spine.seam.record_operational` merges
  into `detail` (`mentis/spine/act_annotations.py`). Only acts by the session's own
  Participant are annotated, and keys the writer set itself win. `record_request` also states
  the authorization in its Turn and in the expectation's detail. With no `authorized_by` and an
  `under`, the source defaults to `{"source": "request", "request": under}`.
- **D-I8: How op keys are stored and scoped.** Op keys use the existing `operation-keyed` act,
  named `worker:<op>:<op_key>`, per grant participant. A key reused for a different write is
  refused (`validation`). The kept answer leaves out `dispatch`/`dispatches`, so a replay
  never dispatches again. `delegate`'s key is written right after it, not inside its
  transaction (see `refusals.md` gaps). Every non-read op accepts `op_key`, not only the list
  in this contract.
- **D-I9: Outbox format.** The outbox is append-only: `put` lines and `ack` lines. "Removed
  once acknowledged" happens through compaction: the file is rewritten to the pending entries
  once it reaches 200 lines, and deleted when nothing is pending. Two sessions of one
  participant on one host share the file under a lock file. Writes are resent before every
  next call (reads included) and at start. A resent entry that is refused is acknowledged and
  reported on stderr.
- **D-I10: Refusal body.** The door's 403 for a structured refusal is
  `{error, kind, refusal}`. The legacy `{error, kind}` handler, and the Rust front's
  `refused_body`, are unchanged.

**WS-A (permission enforcement), builder of `mod-perm`:**

1. *`mars/consent` is now sent for a Claude run without owner consent.* When
   `COMPILED_SCOPE_RUNTIMES` holds `claude`, a run with no owner consent still gets
   compiled rules (its own Mentis tools, reads in its workspace), so MARS receives
   `{"mode": "ask", "workspaces": [], "runtime_rules": {...}}` where it used to receive
   nothing. `ask` with no workspaces adds no directory and confines nothing in MARS.
2. *A `deny` rule means "never by the runtime's own allow", not "refuse".* The protected
   locations, secrets by name, and guarded files inside an edit workspace are in `deny`.
   MARS may apply them as Claude `ask` rules, which escalate the request to Mentis as
   today, where the runtime supports that, or as `deny`, which refuses it. Either way
   nothing is broader than Mentis. The compiler and the replay depend on neither reading:
   the replay counts a deny as a refusal, the stricter case. Under Approve All no deny rule
   is emitted.
3. *A narrowing stops a compiled run and restarts the work fresh* (`web/compiled_runs.py`).
   Rules are handed over when the session opens. When the owner then sets consent
   (`consent.AFTER_SET`: Approve All or task consent narrowed, `deny` set, a tool revoked),
   every live compiled run's rules are compiled again. If they are now narrower, the run is
   halted through `agents_halt_run` (the Stop path), and `execution-restart-asked` records
   why. When the run has ended, `dispatch` sends the same request to its carrier again as
   `work-restarted`, with no `resumed_from`, so continuity opens a fresh session with rules
   compiled from the new consent. Widening restarts nothing. A carrier's Workflow change
   needs no restart, because no compiled rule rests on the standing edit allowance it
   withdraws. Under `ask` no Edit rule is compiled; under routine work, `decide` allows the
   edit by the owner's consent. Between the narrowing being recorded and the runtime
   stopping, the runtime may still act on its old rules; everything that reaches Mentis is
   answered under the new consent.
4. *`detail.audit` is also kept in `detail.runtime_evidence.audit`.* It is computed in
   `MentisService.agents_perform` (one hook, `policy.end_of_run`) into the outcome's
   evidence and lifted to `detail.audit` by two lines in `web/dispatch.py`.
5. *Readers see every answer already given.* `consent.answered` waits for the write-behind
   queue first (`consent.BEFORE_READ`), so `/api/runs/<run>/consent` never misses an
   answer the run has already received.
