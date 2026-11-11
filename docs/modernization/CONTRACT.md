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
  is refused with a structured refusal naming the holder execution (review fix). A claim that
  overlaps a session lease which stopped counting (holder not live) records its
  `resource-released` (reason `superseded-not-live`, `superseded_by` the new claim) in the same
  transaction, so that lease never revives if its session returns as the same execution.
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

1. **Capacity, cold start.** Selection never waits for a capacity read: it uses the newest
   answer held, whatever its age (one older than `CAPACITY_REUSE_S` has a newer one read in the
   background), and with NOTHING held -- a server's first dispatch -- it decides with every
   runtime's capacity unknown, said so, while the read goes on in the background (live round 2:
   that first-selection wait for MARS's capacity answer was the ~1.6 s left in a cold
   selection). Dispatch calls `MentisService.capacity_prime()` as it begins. Quota holds from
   the record still apply. Selection records `inputs.timing` (`backends_ms`, `capacity_ms`,
   `total_ms`). `CAPACITY_WAIT_S` now bounds only the non-selection callers that ask to wait.
2. **`mars/backends` cache.** Kept only for an execution that exposes `generation` (the
   `MarsExecution` process counter, incremented on every `mars stdio` start, which is how a MARS
   restart is noticed). Fakes without it are not cached. **Instead of invalidating after 60 s or
   on restart, a held catalogue is served whatever its age** and refreshed in the background
   once it is 45 s old or from a replaced MARS process; only a service that never held one waits
   (live experiment: the first dispatch after ~2 min idle spent ~8 s re-asking the list while a
   gemini probe timed out). `MentisService.keep_current()`, called at server start, primes the
   catalogue once and then refreshes it every 50 s only while a dispatch began within the last
   10 min (`note_activity`); an idle server asks MARS nothing. Capacity is never read to keep
   it warm (an idle MARS starts no `/usage`): dispatch starts a read as it begins and selection
   uses what is held. It stops on `close()`. An empty answer is never kept.
3. **`runtime_session` carries more than `{token, backend}`:** also `supported` and the terms the
   session was opened under (`participant`, `model`, `workspace` and the consent's additional
   `directories`, normalized, `context` = the binding's governing
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
   children's results, decisions and inputs), then the run's whole situation as it stands now,
   exactly as the full payload tells it (referenced objects and posts, the artifacts it may
   read -- including what children returned since --, the unconfirmed-capability note, follow-up
   permission, consent and research, other live work's leases in the workspace, an owed render
   check), the current authority line (scope, organising operations, Workflow-change line), and
   the closing block, last. Only the condensed governance and the reply format are not resent:
   the resumed session holds them, and a change to either forces a fresh session.
7. **WS-P / MARS: token timing for per-turn backends.** A backend that runs one process per
   turn (agy) knows its conversation id only after a turn, so MARS answers `_meta["mars/resume"]
   = null` on the `session/new` result and gives the token on each `session/prompt` result's
   `_meta["mars/resume"]` (token format `mars1.<hex backend>.<hex runtime id>`). ACP backends
   (claude, codex) give it on `session/new` only. `MarsExecution` reads both and keeps the
   prompt result's token when there is one. MARS's `mars/timing` also carries `total_ms` and
   `adapter` (a string); Mentis copies numeric and string values into `timing.mars`.
8. **Capacity readings MARS marks `pending: true`** (no reading yet) are read as unknown, never
   as exhausted or available, and such an answer (or an empty one) is held only 5 s before the
   next caller asks again. Selection records `inputs.capacity_age = {held_s, mars_age_s,
   pending}`. Quota holds from the record remain the authority.

**WS-C (mod-completion), recorded by its builder:**

1. **Rule 1, made strict after review.** Rule 1 reads the claimant's own run and every run
   after the claim. The claim stays `outcome-pending` in three cases: its own run has not
   ended yet ("its run has not ended yet"); its own run failed or was cancelled ("its run
   failed / was cancelled after the claim"); or any run of the work started after the claim
   ("a later run started after the claim; it must make its own claim"). This holds whatever
   that later run did. A claim made during a live run (`respond(fulfils|outcome)`) is
   reconciled again when that run ends. Before this change, `respond(fulfils)` wrote
   `expectation-met` at once. At run end, dispatch reconciles only a claim that this
   execution made. A pending claim of met is also reconciled again, with no further run, in
   these cases:
   - the decision or input it waits for is answered (posting, `inputs.mark_ready`,
     `_answered_asks`, a reconsideration's resolve);
   - a child or awaited work it waits on ends (dispatch end, before resumption is asked);
   - review work of it passes.

   An answer that resumes the work leaves the claim to the resumed run.
2. **Rule 4 has no machine-readable flag to read, and only independent review verifies.**
   No Workflow field says "review required". Review is therefore required when a Workflow
   named by `governed_named(expectation)` has an activity that `stage.is_review` reads as
   review: its `who.persona` name says review, or its `what` / `key` opens as a review. Two
   kinds of request are exempt: review work itself (by its Persona, by
   `repository.review_of`, or by its brief), and one activity of a Workflow
   (`activity_named`).

   **The verification rule** (it satisfies rule 4, and it decides the `verified` state and
   its words). A `review-verdict` counts for work W only when all three of these hold:
   1. The request it was recorded on is review work (`is_review_work`).
   2. That request is about W. It was delegated directly under W, or it declares
      `review_of: W`.
   3. The verdict's actor is none of W's claimants, and its execution is none of theirs.
      W's claimants are the actors and executions of its claims and of its met acts.

   The newest verdict that counts must be `pass`. `record_verdict` stays an ASKS op that any
   run may call, but a verdict on its own non-review request, or on anything that is not a
   review of W, verifies nothing. `on_review_pass` reconciles only the work that a review
   request reviews. `stage.py`'s `awaiting_review` is git-derived, so it is not used for this
   rule.
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
   what reconciliation recorded of that claim). `verified` requires the work to be recorded
   met, and the verification rule in 2 to hold. Stage words: met work reads `Objective met`,
   where it used to read `Answered · objective met`. A met that no claim was reconciled into
   (historic, system, owner) reads `Objective met`. It reads `Objective met · marked by <who>`
   only when the actor is a real participant, never `mentis`, and it is never called a claim.
9. **Delegated work still running holds a claim of met (rule 3, widened).** A run that ends
   claiming `met` while work it delegated is still running is held pending, whether or not
   it declared that it waits on that work. Its reason is `delegated work still running:
   <ids>`; a declared child keeps `child <id> has not ended`. A child that ended unmet stays a
   non-blocking note.
10. **What a claim is.** Only a top-level ```` ```outcome ```` fence that ends the reply is a
    claim: nothing but whitespace may follow it, and it may not sit inside another fence or a
    quote. This is the same for the final reply and for `respond` text. A block's unknown
    keys are kept under `detail.extra` and never set `because`, `results` or `about`. Only
    the operation's own arguments set those (`TRUSTED`). The posted line is attributed and
    escaped: "Claim by @X: … (the agent's claim; what Mentis recorded is shown with the
    work)". Labels show the claimant's words as one clipped line, with markdown removed.
    Reconciliation checks and writes inside one `atomic()` block.
11. **Session claims are the recorder's own.** `record_outcome` records a claim only when the
    session participant recorded the request, or carries it (`take_up`). Another session may
    still post the outcome (D-I3 continuity). It gets `claim: null` and a `claim_why_not`.

### WS-I (mod-contrib)

- **D-I11 (review fixes): which Participants a session may be.** A session is
  bound only to (a) a Participant created by the session route as an
  independently launched CLI participant (its `about` starts with the CLI-agent
  marker and its entry is written by `mentis/manual-session`) that nothing but
  hand-started sessions ever acted as, or (b) a new alias, created there as
  one. Any other existing Participant -- the owner, @Caretaker, a Persona's or
  a runtime's, or a session participant that has since been dispatched -- is
  refused, `boundary: ownership`, `who: the owner`, recovery: omit
  `--participant` or pick a new name (`session_identity.bindable_problem`).
- **D-I12: the host is a claim.** It is recorded as `detail.host_claimed` (not
  the contract's `detail.host`) on every act of a session call, the key's act
  included, and on `manual-session-started`. It chooses the default alias and
  proves nothing: any client can claim any host and so be that runtime and
  host's CLI participant -- which is a label, never authority.
- **D-I13: op keys are found by an indexed column, with no migration.** A key's
  `operation-keyed` act carries `caused_by = "opkey:<sha256(owner, key)>"`, a
  value that is never an act id, and is found by the existing
  `idx_operational_caused_by` -- one equality, not a json scan of the actor's
  acts. The Contributions Conversation is found the same way (owner `brain`)
  and cached in-process. Supersedes D-I8's "existing `operation-keyed`
  mechanism" for lookups: posting's own keys are unchanged.
- **D-I14: outbox per session.** `%LOCALAPPDATA%/Mentis/outbox/<participant>/<execution>.jsonl`
  (`unbound-<uuid>.jsonl` before the server named an execution), with an OS
  lock on `<execution>.live` held for the process's life. A start resends only
  entries of sessions whose lock is free, as that session (`continues`) where
  the server accepts it, else under its own grant; each refused resend is told
  to the agent on its next tool result. Kept vs acknowledged is decided by
  status and transport: a result, a 403 or another 4xx is an answer; nobody
  there, a timeout, a cut reply or any 5xx (the front's "nothing was done"
  503 included) is kept. Supersedes D-I9's shared file.
- **D-I16 (second review): a CLI-session participant is not an agent.** No
  run is started as one: `dispatch._dispatch` refuses it before anything is
  summoned (a failure before start with a `refusal`, `boundary: ownership`),
  and `delegate` refuses it. Binding also refuses a Participant the owner
  configured as an agent (a runtime default, a designated Persona, the intake
  carrier) or one with work addressed to it by anybody but its own sessions.
  If the default `@<Runtime>-CLI-<HOST>` is nonetheless unbindable, the
  default path takes the next free `-2`, `-3`, ... and is never refused.
- **D-I17: known outbox limitations (not fixed).** (a) At start, a gone
  session whose old grant the server still holds cannot be continued; its
  writes fall back to the new session's grant, so place-bound ones may be
  refused (each refusal is told to the agent). (b) Orphaned outboxes are
  resent only at a session's start, not mid-session. (c) A `return_artifact`
  resend re-reads the file at its path; sessions are not offered
  `return_artifact` (`SESSION_CARRIED`), so no session outbox holds one today.
- **D-I15 (closed in round 2 -- Z, see "Round 2 — Z"): `delegate`'s key is
  written in the delegation's own transaction.** Its eligibility checks (which
  ask the agent service and must not hold the write lock) still run first,
  outside; every write of the delegation and its key are then one transaction
  that asks for the key again under the write lock (`opkeys.writing`). There
  is no window left in which a crash lets a resend delegate twice. (Was: the
  key was written just after, in a transaction of its own, and the delegation's
  own writes each committed alone.)

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
  never dispatches again. `delegate`'s key is written in the delegation's own
  transaction since round 2 -- Z (D-I15). Every non-read op accepts `op_key`, not only the list
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
   - **What counts as narrowing.** Old and new rules are compared as MARS applies them:
     allow rules only under `task` (Approve All is sent as `task`), deny rules as `ask`. A
     narrowing is an operation the old applied rules allowed that the new ones do not. That
     happens when an old allow is not covered by the new allows, or a new ask rule overlaps
     an old allow's scope. A run whose applied rules allowed nothing (`ask`/`deny`) is never
     halted, and widening never halts.
   - **No window is lost.** A run is tracked from before its consent is first read. A
     consent set while the rules are computed makes them be computed again.
     `permissions.before_open` reads them once more, immediately before `perform`, and
     replaces what is about to be sent.
   - **Halting an open run.** After the session opens, every consent the owner sets
     (`consent.AFTER_SET`) rechecks the tracked runs. A narrower run is halted through
     `agents_halt_run`, the Stop path. A halt that cannot take effect yet stays pending and
     is retried until it takes or the run ends; meanwhile Mentis refuses every request of
     that run. `execution-restart-asked` is recorded only once the halt has taken effect. A
     recheck that fails halts the run (fail closed).
   - **Restart.** At the halted run's end, `dispatch` calls `restart_if_asked` *instead of*
     `resume_if_ready`. It dispatches the same request to its carrier as `work-restarted`,
     with no `resumed_from`, so the session is fresh. The halted run's work has not ended,
     so a parent waiting on a delegated child is not resumed until the restarted run ends.
     There is no restart when the owner stopped the run (`execution-stop-asked`), or the
     work is met, withdrawn or running.
   - **Workflow changes.** A carrier's Workflow change needs no restart: no compiled rule
     rests on the standing edit allowance it withdraws.
   - **Second review.**
     - The run's own Mentis tools never count as lost: Mentis allows them in every mode.
     - A consent set between the last read and the open is rechecked in `opened()`.
     - A halt is never abandoned. It is retried with backoff, on every request and event of
       the run, and on every consent set.
     - A failed recheck halts only runs whose applied rules allow something beyond Mentis
       tools.
     - Restarts are capped at 3 per request per hour. Past the cap, `restart-held` holds the
       work for the owner.
     - `execution-restart-asked`, `work-restarted` and `restart-held` are recorded by
       `mentis`, citing the owner's consent act (`detail.consent_act`).
     - Observed calls are also flushed on a 10 s timer.
   - **Third review.**
     - Nothing restarts a halted run's work later by itself; there is no startup recovery.
       A halted run is restarted once, when it ends. If no new run starts (the server
       died, the dispatch failed, or the cap was reached), the work reads "Stopped for a
       consent change · not restarted" (`consent-stopped`). It sits in the owner's Needs
       You, and it is continued by the ordinary continue path.
     - A halted child that is not restarted holds the work waiting on it, as an interrupted
       run does (`_child_state` reads it as `interrupted`). Its ending never resumes waiters
       (`restart_if_asked` returns `HELD`). An owner's own Stop is an ordinary end.
     - Halt records are written through the ordered write-behind queue, never on the ACP
       event loop.
   - **Final review.**
     - A real halt ends the run `cancelled` (`delivery-failed`). `_child_state` reads any
       end of a run that had a restart asked (and no owner Stop) as `interrupted`.
     - `dispatch` calls `restart_if_asked` before it reconciles a held claim. When the run
       was restarted or held, it neither reconciles nor resumes.
     - A restart reuses the halted run's own dispatch arguments, minus `resumed_from`: the
       resumption text with follow-ups and children's results, `deadline_s`, the model and
       the Persona. It adds the follow-ups shown to the stopped session while it worked.
     - The halt is event-driven, with no polling thread. `MarsExecution.precancel` holds a
       run that has not opened yet to its cancel: no session is opened, or the session is
       cancelled before its prompt. A pending halt is retried on every request, event and
       consent set of the run, and the run's requests are refused meanwhile.
     - `mentis/redaction.py` masks only high-confidence secret values and leaves all other
       text byte-identical. It applies to `operation-answered` (which recorded raw commands
       before), to `operations-observed`, and to the end act's `tool_calls` titles. Records
       where something was masked carry `redacted: true`.
4. *`detail.audit` is also kept in `detail.runtime_evidence.audit`.* It is computed in
   `MentisService.agents_perform` (one hook, `policy.end_of_run`) into the outcome's
   evidence and lifted to `detail.audit` by two lines in `web/dispatch.py`.
6. *Only `mentis-tools` and `approve-all` are compiled* (security review). Mentis
   resolves real paths, while Claude matches literal ones. A symlink, junction or 8.3 name
   inside a workspace that leads to a protected location would therefore pass a
   `Read`/`Edit` path rule where Mentis asks, and the replay cannot show equivalence for
   that. If a protected location cannot be written as a rule, no allow is compiled for the
   run at all.
7. *Compiled runs are audited as they go.* Their tool-call events are recorded in order as
   `operations-observed` acts on the run, every 10 s or 50 calls and at the end, through the
   same write-behind queue. An end act written before queued records were flushed (60 s)
   says so in `runtime_evidence.permission_records_unwritten`.
5. *Readers see every answer already given.* `consent.answered` waits for the write-behind
   queue first (`consent.BEFORE_READ`), so `/api/runs/<run>/consent` never misses an
   answer the run has already received.

## Round 2 — M (O8: MCP configuration for dispatched sessions)

- **Stated, not implicit.** Every dispatched run's `RunSpec.mcp` (`AgentService.mcp_statement_for`,
  `mentis/execution/mcp_policy.py`) is sent as session/new `_meta["mars/mcp"]`: the intended
  Brain (`_record`), server (`_answers_at`) and execution (instance id), the owner's policy
  for user-level servers, and the Mentis server addresses. The run's own `mcpServers` are
  unchanged: the bridge for this Brain under this run's grant.
- **The owner's policy** is `<brain>/mcp-policy.json` (`mentis.mcp-policy` v1:
  `user_servers {default allow|deny, allow, deny, other_brains}`, `mentis_servers`), edited by
  hand. No file = every non-Mentis user server the runtime would load is given. An unreadable
  file fails closed (`default: deny`) and says why (`policy_unreadable`, kept in the evidence).
- **MARS assembles per runtime** (MARS API.md "MCP assembly"): excluded registrations
  (another Brain, this Brain outside the grant, unverified Mentis surfaces, owner-denied) are
  kept out by each runtime's own mechanism, or the session is refused (`mcp_conflict`) where
  the runtime has none (kimi, for a registration not named like a client server).
- **Recorded.** MARS's `_meta["mars/mcp"]` answer is kept as `RunResult.mcp`
  (`mcp_policy.summary`) and lands in the end act's `detail.runtime_evidence.mcp`:
  `reported`, `enforcement`, `given`, `excluded` (reason, detail), `unavailable` (why), and
  notes. A MARS that does not answer is recorded as `reported: false` with why.
- **Told.** The tooling block lists the servers the session was given (from MARS's answer)
  and each owner server it does not have, with why, and any note (e.g. agy refusing a tool
  the owner's settings do not allow).

## Round 2 — P (parity)

- **Runtime capability contract.** MARS `_mars/backends[].contract` =
  `{version: 1, states, availability, capabilities: {name: {state, kind?, evidence, source,
  fallback?, advertised?, why?}}}`, states `supported` / `unsupported` /
  `temporarily-unavailable` / `not-yet-verified`, ten capabilities (MARS API.md). Mentis reads
  it in `mentis/core/runtime_contract.py`; `MentisService.runtime_contract(runtime, holds)`
  overlays quota (exhausted or held → temporarily-unavailable). A MARS without it is read as
  all `not-yet-verified`.
- **Continuity consumes it.** `continuity.decide(..., contract=)` does not ask a runtime with
  `native_resume: unsupported`; the run's `continuity.why` says the continuation is given the
  record-derived context.
- **Context restoration.** A continuation of the same work (`resumed_from`) sent in a fresh
  session gets, in the full payload only, `# The work as it began, and where your previous run
  left it`: the request's words in full and the previous run's reply (≤ 6000 chars).
- **Deadline → `hard_s`.** `agents_perform` sends a deadline as `mars/limits.hard_s` (MARS
  §3.4); `timeout_s` was never a MARS limit and was refused.
- **Codex resume.** MARS sets a loaded session back to `default`, or, for an agent with no
  mode of that name (codex-acp), to the mode its fresh sessions start in.
- Conformance suite and onboarding: `tests/conformance_runtime/`,
  `tools/runtime_conformance.py`, `RUNTIME-ONBOARDING.md`, `RUNTIME-PARITY.md`.

## Round 2 — R (release, O1/O7/§14)

- **Release helper**: `tools/release_modernize/` (the operational copy lives in
  `C:\Work\Mentis-workspace\day-to-day\modernize-release\`). `prepare.ps1 -Target <mentis sha>
  -MarsCommit <mars sha>` checks that each commit is the tip of `release/dayday-modernize` or
  MARS `modernize`, and that it descends from cbfabaa or 4a92477. It builds MARS from a
  `git archive` of the exact commit into `releases\modernize-<sha12>\mars.exe`, pins the
  SHA-256 in `PROVENANCE.json`, and writes `arm.cmd`, `dryrun.cmd`, `rollback.cmd` and
  `rehearse.cmd` with those exact values. `deploy.ps1` re-validates all of them: the Target
  must equal the candidate branch tip by fetch, the MARS hash must equal the pin, and Fluid's
  `build-identity.json` must name the commit `/api/server` reports, clean.
- **Bounded backup** (`bounded_backup.py`): corpus.db is copied with SQLite's online backup
  API. Each `artifacts/` blob is hardlinked after it is hashed against its name; a blob that
  does not match is copied and reported. The small directories are copied. On the DAY-TO-DAY
  Brain this costs about 0.33 GB instead of about 3.8 GB, in 4 to 11 s. After every deploy the
  backup is restored into a temp folder, quick_checked and counted, and then deleted. The
  helper keeps at most 2 of its own backups (`pre-modernize-*` holding `BACKUP.json`). Older
  `pre-*` backups are only reported. After the review (r2-fix): the backup also carries
  `mcp-policy.json` and any other small top-level `*.json` owner file; a restored Brain holds no
  `BACKUP.json` mark; a passed restore check writes `RESTORE-CHECK.json` into the backup;
  retention runs only after the new backup's restore check passed and never leaves fewer than 2
  verified backups; the temp restore is removed on failure too; and a failure from the moment
  the stop begins (Stop-Pair included) leads to the application rollback, reported "after stop"
  (`tests/test_release_bounded_backup.py`, `tests/test_release_deploy_script.py`).
- **Rust front**: unchanged (magnet-1c0c13a). The candidate adds ONE HTTP route, the owner's
  `/api/session-grants` (Round 2 — A, O4), and the unchanged front already sends it to Python:
  in `crates/mentis-server/route-table.default.json` its GET matches the `api` rule
  (`GET /api/*`, owner `python`) and its POST matches no rule, which `route_table.rs`
  `RouteTable::decide` answers `Decision::Python { rule: None }` ("unknown means forwarded").
  Every other new operation goes through `POST /api/worker`, which the front forwards for every
  op except the 8 moved reads, and none of those 8 changed. A route-by-route comparison of the front's Rust
  answers against Python's for the same request is identical on 28 of 29 routes, on both the
  candidate and cbfabaa. `/api/pulse` differs on both: Rust reports `live: unavailable`.
- **Rollback tolerance**: the candidate adds no schema or migration. cbfabaa reads a Brain the
  candidate wrote to with no server error. That covers session participants with a host,
  keyed contributions, leases, outcome claims and `operation-keyed`. The candidate then reads
  it again after cbfabaa has written more.
- **Perf harness**: `tools/perf_runtime.py`. Raw results and the summary are in
  `C:\Work\Mentis-Test-Server\r2-release\perf\`.

## Round 2 — A (authority: O2, O3, O4, O5)

Builder A, branch `r2-authority` (Mentis and MARS). Probes ran against a throwaway ACP client
(claude-agent-acp started directly, a no-tools decoy as `mentis`, `strictMcpConfig`) or a
fixture Brain served on :8821 with this MARS build (each run given the fixture's own bridge
as `mentis`). Live Brain entry count: 47,276 before and after.

### O3 — what Claude Code decides itself (the `sleep`/`echo` finding)

Measured 2026-11-10, claude-agent-acp 0.97.0 / Claude Code 2.1.322, default permission mode,
`allowedTools: ["mcp__mentis__*"]` (what a `task` run was given), one call per command, every
client request answered allow-once (probes C1–C7):

| Call | no ask rules (C1, C4) | `ask: ["Bash","Read"]` (C2, C5) | `ask: ["Bash(echo:*)","Bash(sleep:*)","Bash(cat:*)","Read(<ws>/.env)"]` (C3) |
|---|---|---|---|
| `echo`, `sleep`, `pwd`, `ls`, `git status`, `find apps …` | **ran, client not asked** | asked | `echo`/`sleep` asked; `pwd`/`ls`/`git`/`find` not |
| `cat notes.txt`, **`cat .env`** (inside the cwd) | **ran, not asked** | asked | asked |
| `cat <file outside the cwd>` | asked | asked | asked |
| `mkdir`, `touch`, `echo > f`, `rm`, `python -c`, `bash -c '…'`, `sleep 1 && mkdir` | asked | asked | asked |
| Read / Grep / Glob inside the cwd, **`.env` included** | **ran, not asked** | asked | Read `.env` asked |
| Read outside the cwd; Write; Edit | asked | asked | asked |

Also measured: a real session loads the user's, the project's and the local Claude settings
(claude-agent-acp passes `settingSources: ["user","project","local"]`). A project
`.claude/settings.json` allow rule `Bash(pip install:*)` ran `pip install --help` without
asking (C6); an `ask` rule in the session's flag settings outranked it (C7). The owner's own
`~/.claude/settings.json` holds 157 allow rules (e.g. `Bash(git push *)`, `Bash(xargs kill:*)`)
that applied to dispatched runs the same way.

**Resolution (a supported rule, equivalent).** Outside Approve All, Mentis's compiled rules
for Claude always carry `permission_rules.SELF_DECIDED` (`Bash`, `PowerShell`, `Read`, `Grep`,
`Glob`, `Edit`, `Write`, `MultiEdit`, `NotebookEdit`, `WebFetch`, `WebSearch`) in `deny`, which
MARS applies as Claude `ask` rules: every such call reaches Mentis and is decided by its
policy. Read-only commands are still allowed at once by the run's grant (no capability lost);
secrets and protected paths are asked or refused. Under Approve All nothing changes. Live,
through fixture Mentis + this MARS + Claude under consent `deny`: 8 of 8 calls reached Mentis
(`echo`, `sleep`, `pwd`, `cat notes.txt` allowed by grant; `cat .env`, Read `.env`, `mkdir`
refused), `audit.decided_by_runtime_rules_at_most: 0`. Replay against
`pre-eff-cbfabaa-20261108`, rerun with these rules (347 s): 37,388 answers, 32,860 decided by a rule allow, **0 more permissive** under all four rule readings (unchanged: the ask list only routes calls to Mentis, it allows nothing).

**Where commands start.** Routing read-only shell commands to Mentis exposed that Mentis did
not know a Claude command's cwd after the first one (`shell_cwd: None`): relative read-only
commands would have become owner questions (live, before the fix: `cat notes.txt` refused
under `deny`). MARS now starts Claude Code with `CLAUDE_BASH_MAINTAIN_PROJECT_WORKING_DIR=1`
(measured: without it a `cd` inside the cwd persists into the next Bash and PowerShell command;
with it both start in the session cwd) and declares `mars/tooling.command_cwd: "session"`.
Mentis then gives every permission request `shell_cwd` = the session workspace
(`execution.mars.shell_cwd`) and tells the run so (`execution.tooling`). Live after: `cat
notes.txt` allowed by grant.

Unchanged: `runtime_rules` are Claude-only; only `mentis-tools` and `approve-all` are compiled;
no shell, edit or path rule is ever compiled as an allow.

### Permission-enforcement matrix

"Runtime" = the runtime's own mechanism; "MARS" = MARS's own refusal or confinement; "Mentis" =
permission requests Mentis answers; "Not enforced" = nothing. Pins: Mentis `tests/…`, MARS
`rust/crates/mars/src/…`.

| Runtime | Runtime enforces | MARS enforces | Mentis decides | Not enforced | Pinned by |
|---|---|---|---|---|---|
| **Claude** (`enforced_by: client`, compiled rules) | Approve All: every tool by its compiled allow. `task`: Mentis's own tools (each checked again at `/api/worker`). The ask list forces everything else to the client. Outside Approve All, `refuse` (Claude `deny`): ONLY the high-confidence secrets by name, anywhere (`permission_rules.HARD_SECRET_GLOBS`: `.env`, `.env.<env>` for the common environments and `.env.*.local`, `id_rsa`/`id_ed25519`/`id_ecdsa`/`id_dsa`, `credentials`, `credentials.json`, `auth.json`) — Read refused, and the files kept out of Grep and Glob results (measured). Everything else Mentis protects (`.env.example`, `credentials.py`, `*.pem`, `*.key`, `*.pfx`, `*.pub`, the protected locations such as `~/.claude`) is asked of Mentis, which asks the owner. | `allowDangerouslySkipPermissions: false`; a resumed session set back to `default`; deny→ask mapping; consent workspaces as additional directories; every command starts in the cwd | every Bash/PowerShell/Read/Grep/Glob/edit/web call outside Approve All, and anything else Claude asks; a recursive shell search (`grep -r`, `rg`, `findstr /s`) over a directory holding secret files it does not exclude, or one Mentis cannot read with confidence, is asked of the owner (refused under `deny`); a shell read of a hard-refused secret (`cat .env`) is the owner-approved path to it | tools of other MCP servers a session is given that the owner's/project's Claude settings allow (which servers: Builder M); the halt window (below) | `test_permission_matrix` (`test_outside_approve_all_*`, `test_what_claude_ran_unasked_*`, `test_compiled_rules_never_reach_edits_or_shell_*`, `test_protected_locations_*`, `test_shell_commands_start_where_mars_declared`); MARS `consent::runtime_rules_never_broaden_the_consent`, `acp_tests` (rules mapping, headless env), `tooling::claude` |
| **Codex** (`enforced_by: sandbox+client`; contract kind `sandbox+runtime-reviewer`, state not-yet-verified since MARS bf6f991) | codex-acp 2.3.0 default mode `agent` ("Auto review"): workspace-write sandbox, network off; acts inside the sandbox without asking; escalations go to Codex's own auto-reviewer, which asks the client only for what it judges unsafe (read from codex-acp's mode table; **not live-verified**) | consent workspaces as writable roots; user MCP servers disabled per session | what Codex escalates past its auto-review | reads inside the sandbox (protected locations included, where readable); escalations the auto-reviewer approves | `test_permission_matrix::test_only_claude_is_given_runtime_rules`, `test_every_run_tells_mars_its_consent_*`; MARS `consent::each_backend_says_how_consent_is_enforced`, `tooling::codex` |
| **Antigravity** (`enforced_by: sandbox`) | `--sandbox`; headless agy refuses any command without an allow rule; Mentis's pre-turn `allow: ["command(*)"]` only under Approve All or `task` with test/build/run; under Approve All only, `allow_given_mcp: true` (MARS adds `mcp(<name>/*)` for exactly the user MCP servers the session is given) | consent requires `sandbox: true`, refuses `agy_bin`, forbids changing `allow`/`sandbox` after start | nothing during the run (agy never asks) | what the sandbox permits once `command(*)` is allowed; the given user MCP servers' tools under Approve All (narrower consent: refused by agy and reported) | `test_permission_matrix::test_antigravity_pre_turn_allow_*`; `test_run_consent::test_antigravity_is_allowed_commands_only_*`; MARS `consent::bad_consent_is_refused_in_words` |
| **Kimi** (configured `kimi*`, `permissions: forwarded`) | whatever kimi-code runs without asking (**not measured**: K3 capacity-blocked) | consent workspaces as directories | every request kimi forwards | anything kimi runs without asking (unknown) | `test_permission_matrix::test_only_claude_*`, `test_every_run_tells_mars_its_consent_*` |
| **local** (MARS worker, `Permissions::None`) | — | `accessMode` read-only / workspace-write: tool allowlist confined to the workspace (not OS-enforced); MCP refused there | nothing (the worker never asks) | **everything in `full` access**, which is what runs (Mentis passes no `accessMode`): `enforced_by: none`, shown as not enforced | `test_permission_matrix::test_a_local_run_in_full_access_is_never_shown_as_consent_enforced`, `test_enforcement_is_said_as_mars_reported_it`, `test_the_consent_route_says_what_enforces_it`; MARS `tooling::local_declares_its_workers_tools` |

For every runtime: **every run now tells MARS its consent** (`ask`, no workspaces, when the
owner gave none: no directory added, nothing confined), so MARS's `enforced_by` reaches the
run's record, and `GET /api/runs/<run>/consent` returns `consent.enforcement = {by, enforced,
words}` (`permissions.enforcement`; `enforced` only for `client`, `sandbox+client`, `sandbox`).
Owner escalations stay synchronous, audit ordered and durable (`test_permission_compiled`:
`test_the_answer_does_not_wait_for_its_record_but_a_refusal_does`,
`test_automatic_answers_are_written_in_order_and_flushed`,
`test_a_crash_loses_at_most_what_was_queued_and_never_a_refusal`,
`test_readers_of_a_runs_answers_see_every_answer_given`).

### O2 — narrowing and restart, by requirement

| Requirement | Pinned by |
|---|---|
| narrowing hits the active execution | `test_consent_restart::test_every_narrowing_from_approve_all_halts`; `test_permission_compiled::test_narrowing_a_compiled_run_halts_it_and_restarts_fresh`; live ×4 |
| old execution halted before the replacement proceeds | `test_consent_restart::test_the_replacement_starts_only_after_the_old_execution_ended`; live: `work-restarted` 1.5 ms after the halted run's end act |
| replacement gets the new consent and current authority | same test (new run, no resume, new consent, no `Bash` allow); live: restarted run `mode task, allow 1, deny 11` |
| owner instructions and Workflow changes preserved | `test_permission_compiled::test_a_restart_carries_the_halted_runs_context`; `test_consent_restart::test_the_replacement_is_composed_from_the_record_not_the_stale_session` |
| explicit owner Stop / withdrawal never overridden | `test_permission_compiled::test_restart_respects_the_owners_stop`; `test_consent_restart::test_a_withdrawn_request_is_never_restarted` |
| restart cap | `test_permission_compiled::test_restarts_are_capped_and_the_work_held_for_the_owner` |
| unrestartable → Needs You with its actual reason | `test_permission_compiled::test_work_not_restarted_is_the_owners_to_continue`; `test_consent_restart::test_unrestartable_work_says_its_actual_reason` |
| parent not completed while a required child is interrupted | `test_permission_compiled::test_a_held_claim_is_not_reconciled_over_a_halted_child`, `test_what_waits_on_a_halted_child_keeps_waiting`, `test_a_real_halt_ends_cancelled_and_holds_what_waits` |
| no restart on a normal end | `test_consent_restart::test_a_normal_end_is_never_restarted`; `test_permission_compiled::test_a_narrowing_after_perform_returned_asks_no_restart` |
| interruption / cancellation / failure / completion distinct | `test_consent_restart::test_interruption_cancellation_failure_and_completion_stay_distinct` |

**The halt window, measured** (fixture + this MARS + Claude under Approve All running a loop of
`date >> ticks` / `sleep`, consent narrowed to `task`/read mid-loop):

| Run | cancel asked after the consent act | run ended (cancelled) after it | commands run after it |
|---|---:|---:|---:|
| before1 (between commands) | 2.5 ms | 119 ms | 0 |
| before2 (1 s into a command) | 2.0 ms | 73 ms | 0 |
| before3 (6 s into an 8 s `sleep && date`) | 1.5 ms | 148 ms | 0 (the in-flight command was killed; its `date` never ran) |
| after1 (as before3, round-2 build) | 2.0 ms | 148 ms | 0 |

In the window the runtime may do what its old rules allowed (under Approve All: anything)
for at most ~150 ms; nothing started in it in 4 runs, an in-flight command is killed, and
every request reaching Mentis in it is refused (`stale-rules`). The Mentis-side part is
≤ 2.5 ms, because the recheck runs inside the owner's consent call
(`test_permission_matrix::test_the_halt_window_cancel_is_sent_with_the_consent`); the rest is
the runtime's cancel latency. Not shrunk further: cancelling before recording would save ~2 ms
of ~150 ms and would cancel on a consent write that might then fail.

### O4 — hand-started CLI authority

Default (WS-I, unchanged): no coordination without `under=<a request a session recorded>`;
reads, `contribute` (no request needed), `record_request`, `open_conversation`, carrying and
closing its own requests, leases. **New, the owner's explicit grant:**
`mentis/operational/session_grants.py`; owner-only `POST /api/session-grants {participant,
request, because}` (revoke: `{revoke: <grant act>, because}`), `GET ?request=`. It records
`session-coordination-granted` (actor the owner, about the request and the CLI Participant,
the owner's words) and lets that CLI Participant's sessions carry that one request: name it
in `under` (so coordinate under it), close it with `record_outcome` and claim its outcome.
Refused for anyone but the owner, anything but a CLI Participant, and anything but a recorded
request; no worker op reaches it. `session-coordination-revoked` withdraws it at once.
**What actually protects it (said exactly after the review, M3):** the route is an owner route
TRUSTED BY LOCALITY, NOT AUTHENTICATED, like every owner route. No Mentis tool reaches it; a
request presenting a worker grant (`X-Mentis-Worker`) is refused 403 at the door; the
`X-Mentis-Client` header and Host check stop a web page. But any local process that presents no
grant — an agent's own shell included — reaches it exactly as the owner's client does. So the
act's actor `owner` is the route's claim, and each grant and revocation also records what the
server observed of the request (`detail.written_by`, the same `_observed_writer` every owner
write records: `unattributed-local-request` when it presented nothing). Where the request does
identify a calling session (a worker grant it presented, should the door ever pass one), a
grant to that very session's Participant is refused. [`test_cli_authority::test_the_grant_route_records_what_it_observed_and_never_grants_the_caller`] Nothing
previously legitimate was removed. [`test_cli_authority`: `test_a_session_keeps_its_legitimate_work_with_no_request`,
`test_no_coordination_merely_because_a_session_exists`, `test_the_owner_grants_a_session_a_request_and_revokes_it`,
`test_a_granted_request_is_closed_and_claimed_by_the_session`]

Open owner question (not changed): a session still obtains `coordinate` by recording a request
itself (its `authorized_by` is its own claim). Requiring the owner's grant instead would remove
that round-1 capability, so it is left as is.

### O5 — identity

Fixed: acts a session wrote without naming an execution (its `expectation-recorded`,
`conversation-opened`, `operation-keyed`) had `execution` and `runtime` null, so two sessions of
one participant on one host could not be told apart on them. The session call's annotation
(`spine.act_annotations.session_of`, applied in `record_operational`) now fills both for the
session participant's own acts that name no execution; an act naming another execution, or by
anybody else, is untouched. [`test_cli_authority::test_two_sessions_on_one_host_are_told_apart_on_every_act`]
Verified unchanged: historical @ManualSession records untouched and still carried
(`test_cli_authority::test_historical_manual_session_work_is_untouched_and_still_carried`);
contributor apart from authorizer (`test_session_contribution::test_authorized_by_is_stored_apart_from_the_actor`);
impersonation refused (`test_a_named_participant_and_never_the_owner`,
`test_a_session_cannot_bind_as_an_existing_agent`, `test_an_owner_configured_participant_is_not_bindable`);
the host is only `host_claimed` and read nowhere for authority (`test_the_host_is_recorded_as_claimed`);
provenance across retries and reconnects (`test_the_same_op_key_twice_is_one_act`,
`test_a_lost_answer_is_resent_and_recorded_once`, `test_a_gone_sessions_place_bound_write_is_resent_as_that_session`).

### Open defects found, not fixed

- Codex's default `agent` mode hands escalations to Codex's auto-reviewer (matrix). Setting
  codex mode `workspace-write` (reviewer = user) would route them to Mentis: an owner decision.
- Tools of non-Mentis MCP servers allowed by the owner's/project's Claude settings run without
  Mentis.
- Python MARS (`src/mars/tooling.py`) still declares `command_cwd` for codex only; the Rust
  MARS is what Mentis runs.

### Second hand-back (after the integrator's two items)

**Secrets inside a searched directory — closed, with stated limits.**
- *Measured* (claude-agent-acp 0.97.0 / Claude Code 2.1.322, probes G1–G5, a workspace
  holding `.env`, `sub/id_rsa`, `sub/code.py`): with no rule, Grep and Glob printed `.env`
  and `id_rsa`; with `Read(**/.env)` etc. as **ask** rules (how MARS applies `deny`), Grep and
  Glob STILL printed them (only Read asked); with them as Claude **deny** rules, Grep and Glob
  left them out (`code.py` still found), and Read was refused. The compiled list
  (`permission_rules.hidden_secrets`: `Read(**/<name>)` and `Read(//**/<name>)` for every
  secret name, with case classes, plus every protected location) hid them in the cwd, in a
  directory outside it, and in another case (`.ENV`) (G5).
- *Claude*: Mentis sends that list as `runtime_rules.refuse` outside Approve All; MARS
  (`5c864a5`) applies `refuse` as Claude's own `permissions.deny` in every mode (reported as
  `refuse` / `refuse_as: deny`). Live through fixture Mentis + this MARS + Claude:
  `runtime_rules.refuse: 52` applied (the list before the review narrowed it).
- *Narrowed after the review (M1).* No owner approval reaches a Claude `deny`, so the refuse
  list now names only files that are secrets by name with high confidence, a strict subset of
  `operations._SECRET_NAMES`: **refused by Claude itself** — `.env`; `.env.local`,
  `.env.development`, `.env.dev`, `.env.production`, `.env.prod`, `.env.staging`, `.env.stage`,
  `.env.test`, `.env.testing`, `.env.ci`, `.env.qa`, `.env.uat`, `.env.preview`, `.env.*.local`;
  `id_rsa`, `id_ed25519`, `id_ecdsa`, `id_dsa`; `credentials`, `credentials.json`, `auth.json`
  (any case, anywhere). **Asked of the owner (as before the round)** — every other file or
  location Mentis protects: `.env.example`/`.sample`/`.template`, `credentials.py`, `*.pem`,
  `*.key`, `*.pfx`, `*.pub`, and everything under the protected locations (`~/.claude`,
  `~/.ssh`, the Brain, MARS's data, ...); Claude's Read/Grep/Glob of them reaches Mentis (ask
  rule), which asks the owner (refuses under `deny`, allows under Approve All). **The authorized
  path to a hard-refused secret**: a shell read (`cat .env`, `Get-Content .env`). Claude's Read
  deny rules govern only its own file tools; Bash and PowerShell are ask rules outside Approve
  All, so the command reaches Mentis, which asks the owner with an "Allow once" answer, and it
  runs only if they approve (refused under `deny`). The agent is told this in its tooling block
  ("- Secret files: ...", Claude outside Approve All) and in the run's enforcement words
  (`permissions.enforcement`). Pinned: `test_permission_matrix::test_only_high_confidence_secrets_are_refused_by_claude_itself`,
  `test_the_hard_refuse_list_stays_inside_the_mentis_secret_classifier`,
  `test_an_owner_approved_read_of_a_refused_secret_has_an_authorized_path`.
- *Every runtime's shell*: `operations._describe_command_as` + `mentis/secret_search.py`: a
  recursive `grep`/`egrep`/`fgrep` (-r/-R/--recursive/-d recurse), `rg` (always; hidden files
  only with --hidden/-./-uu or when a glob or type names them) or `findstr /s` over a directory
  holding secret files it would read counts as touching a protected location: asked of the
  owner, refused under `deny`, allowed under Approve All. Live: `grep -rn FAKE .` became an
  owner question naming `.env`.
- *After the review (H1, M2)*: every grep and ripgrep option is read with its value
  (`-m 5`, `-A 2`, `-e PAT`, `--max-count=5`, `-rm5`; grep's unique long-option prefixes are
  resolved), so `grep -r -m 5 FAKE` and `rg --hidden -A 2 FAKE` now search the cwd and are
  asked. A search with no path searches the cwd. Limits are honoured: grep `--include`,
  `--exclude` (the last matching one wins; with none matching, a file is searched unless the
  first is `--include`), `--exclude-dir`; rg `-g/--glob/--iglob` positive and `!` negative (the
  later wins; a positive glob makes a whitelist), `-t/--type`, `-T/--type-not` for the common
  built-in types and `--type-add NAME:GLOB` (an unknown `-t` type counts every file); findstr
  masks and `/D:`. So `grep -r --include=*.py FAKE .` or `rg -t py FAKE` in a repository with
  `.env` is allowed under the grant, and `rg -g '*.py' -g '.env' FAKE` is still asked. A
  recursive search Mentis cannot read with confidence — an option it does not know, an
  ambiguous prefix, a target that does not exist or is not literal, no reported cwd, a file
  list read from a file (`--exclude-from`, findstr `/F:`) — is answered as touching a protected
  location ("cannot read with confidence"). Pinned:
  `test_a_search_whose_options_take_values_still_finds_the_secrets` (14),
  `test_a_search_mentis_cannot_read_confidently_is_answered_as_protected` (9),
  `test_a_search_restricted_to_ordinary_files_is_not_an_owner_question` (22),
  `test_findstr_masks_limit_what_is_searched` (6).
- *Limits, said exactly*: Select-String, `git grep`, ack/ag and searches inside an interpreter
  are not recognised; rg's .gitignore is not modelled (a gitignored secret still counts);
  `node_modules`, `.venv`, `venv`, `site-packages`, `.git`, `__pycache__`, `.tox`, `.mypy_cache`
  are not walked (package data), and at most 20,000 entries are looked at. The Grep tools of
  forwarded non-Claude runtimes (Kimi, Gemini) are answered by the run's grant and are not
  checked for secrets beneath the directory; Codex and the `local` worker search inside their
  own sandbox without asking Mentis.
- Pinned: `test_permission_matrix::test_claude_hides_secrets_by_name_from_its_own_searches_outside_approve_all`,
  `test_a_recursive_shell_search_over_secret_files_is_not_granted` (13 commands),
  `test_dependency_trees_do_not_make_ordinary_search_an_owner_question`,
  `test_protected_locations_are_never_compiled_or_granted`; MARS
  `acp_tests::runtime_rules_reach_claude_code_options`, `consent::runtime_rules_never_broaden_the_consent`.

**Antigravity and the owner's user-level MCP servers.** `permissions.runtime_options` sends
`allow_given_mcp: true` with `command(*)` under Approve All only. MARS (branch
`r2-authority-agy-mcp`, from the integrated `modernize` f3e26d9, commit `e04d56e`) then adds
`mcp(<name>/*)` for exactly the user servers the assembly gives (never an excluded or
unavailable one); the option must be a boolean and cannot be changed after a consented session
starts. Under narrower consent nothing is added: the tools stay refused and reported, as M's
assembly already says. Pinned: `test_permission_matrix::test_antigravity_is_allowed_the_given_user_mcp_servers_only_under_approve_all`,
`test_run_consent::test_antigravity_is_allowed_commands_only_*`; MARS
`mcp_assembly::tests::antigravity_allow_given_mcp_allows_only_the_servers_given`,
`consent::bad_consent_is_refused_in_words`. Not live-verified (no agy run).

### Review fixes (branch `r2-fix`)

Besides the secrets (H1, M2, M1) and O4 (M3) items above:

- **Context restoration reads the record as Mentis shows it** (M4): `continuity.restoration_block`
  and `dispatch.request_words` read through `versions.presented`: an edited request or reply is
  its current text; a deleted reply is not restored (nor brought back from the run's
  `final_text`); a deleted request gives no words. The request is cut to 12,000 characters.
  The "previous run" is the latest one the carrier being dispatched returned; when it has none,
  the latest run is shown labelled as another participant's ("not you"), never as "yours".
  [`test_execution_continuity::test_restoration_*`]
- **Capability contract shown with quota** (L1): the `capabilities` tool lays the record's quota
  holds over each runtime's contract, and `runtime_contract.summary` keeps `availability`
  (state, why). [`conformance_runtime/test_contract::test_the_capabilities_tool_shows_a_held_runtime_as_held`]
- **MCP policy** (L2): the owner's `mentis_servers` add to the defaults.
  [`test_mcp_assembly::test_the_owners_mentis_servers_add_to_the_defaults`]
- **Pre-turn runtimes** (integrator N1): `permissions.runtime_options` and the tooling block read
  the contract's `permission_enforcement.kind == "pre-turn"`, not the runtime's name. Consent is
  never widened: under consent without test/build/run the run is told up front that shell
  commands are not permitted, that attempting one ends the run, and to use its own file read and
  list tools and the Mentis tools instead. MARS's `deniedActions` are kept on the end act
  (`runtime_evidence.denied`); `mcp_conflict` refusals keep MARS's reason, backend, server, file
  and field (`runtime_evidence.mcp_conflict`). A MARS that sends no contract gets no pre-turn
  allow (the round-2 MARS declares it). [`test_run_consent::test_a_pre_turn_runtime_*`,
  `test_the_pre_turn_allow_follows_the_contract_not_the_name`,
  `test_what_the_runtime_refused_is_kept_in_the_end_acts_evidence`,
  `conformance_runtime/test_enforcement::test_a_pre_turn_runtime_is_told_its_rules_up_front_and_others_are_not`]

## Round 2 — Z (delegation / op-key crash window)

Owner's instruction: "Investigate and correct the known delegation/idempotency crash window so
a retry cannot silently create duplicate work." Branch `r2-deleg` from integrated `f2bd1b9`.

### What was exposed, and how

Every write through `/api/worker` with an `op_key` goes through `opkeys.keyed`, deduplicated
per (grant participant, op, op_key) by the `operation-keyed` act whose `caused_by` is
`opkey:<sha256(participant, "worker:<op>:<key>")>`.

- **Not exposed: every write op except `delegate`.** `record_request`, `contribute`,
  `claim_resource`/`release_resource`, `attach_follow_up`, `summon_participant`,
  `change_workflow`, `resume_intake`, `take_up`, `record_outcome`, `record_discovered_work`,
  `open_conversation`/`open_topic`, the ladder and anchor ops and the rest run WHOLE inside one
  `corpus.atomic()` (`BEGIN IMMEDIATE`: the store's write lock, across processes too): look
  for the key, run the op, record the key, COMMIT. Their own nested `atomic()` blocks join that
  one. A crash anywhere leaves the op and its key both or neither. (`contribute`'s
  process-local Contributions-Conversation cache is re-checked against the record before use,
  so a rolled-back first contribution cannot leave a stale id in use.) The posting door's keys
  (`conversation.anchors.keyed`) have the same one-transaction shape.
- **Exposed: `delegate`, both paths.** `OUTSIDE_TRANSACTION = ("delegate",)`: its checks ask the
  agent service which runtimes are eligible, which must not hold the write lock, so `keyed`
  looked for the key, ran the whole op outside any transaction, then recorded the key in a
  transaction of its own.
  - *New child* (the usual path): `join`, `say` (the Turn), each `assign_topic`, `expect` (the
    child request), `restrict`, the `work-delegated` act -- each committed alone -- then the
    key. A crash after any of them and before the key's COMMIT left part or all of a delegation
    that the resend did not find, and the resend delegated again: a second Turn, a second child
    request owed by the same Participant, a second `work-delegated`, a second dispatch.
    Reproduced: `test_a_resend_after_a_crash_at_any_write_delegates_once[said|expected|
    delegated|keying|keyed|committing]` all fail on `f2bd1b9` (after `delegated`: two
    children, two delegations).
  - *Picking up discovered work*: its claim was one transaction, its key the next. Cut between,
    the resend was refused "already carried" -- by its own first send -- and was never told
    what had been done (`test_a_pick_up_cut_before_its_key_is_answered_not_refused`).
  - *The owner's later word shown instead* (`delegated: false`): the follow-ups were marked
    seen in one commit, the key in the next; cut between, the resend delegated without the
    agent ever having read them.
  - *Concurrent duplicates*: a per-key `threading.Lock` held a second send of the key in the
    same process; two processes (anything not sharing that lock) both passed the look and both
    delegated (`test_two_servers_sending_one_key_at_once_delegate_once` fails on `f2bd1b9`).

### The fix: the key is written in the delegation's own transaction

`delegate` now runs in two parts. Its checks (eligibility, standing, references, ...) still
run outside the write lock. All its writes go through `opkeys.writing(corpus)`, a context
manager that opens ONE transaction and asks for the key again *inside it, under the write
lock*. If a send of the same key recorded it meanwhile, it writes nothing and the call is
answered with that first answer (`_Replayed`, rolled back, caught by `keyed`). Otherwise the
block makes every write of the delegation, and `w.done(result)` records the key in the same
transaction. `keyed` hands the key to `writing` through a context variable, so the scope stays
(grant participant, op, op_key). All three return paths of `delegate` -- new child, pick-up,
and "the owner's later word was shown instead" -- write through `writing`. A keyed `delegate`
that wrote nothing through it falls back to recording its key after, as before; no such path
makes a delegation.

So a retry after a crash at any point either finds the earlier result (the crash came after
the COMMIT) or finds nothing of it and delegates exactly once (the crash came before). Nothing
is rewritten and nothing migrated: the partial delegation simply can no longer be made. The
in-process per-key lock is kept, so the usual resend waits for the first answer rather than
repeating the checks.

Changes in behaviour, said exactly:
- A keyed `delegate`'s kept answer is recorded before `_operate` adds `rendering` (the read-only
  render check of the Turn), so a replay no longer carries `rendering`. Nothing else in the
  kept answer changed; `dispatch`/`dispatches` were never kept.
- A delegation's writes, with or without a key, are now atomic: a refusal raised part-way, or a
  crash, leaves none of them.
- **Without an op key** there is no identity to deduplicate by: each send is a new request and
  is delegated (`test_without_an_op_key_each_send_is_a_delegation`). The bridge gives every
  session write a key and resends with the same one; a client that sends none has said each
  send is its own. A dispatched run's worker client never retries (`_result_unknown`).
- **Two sends of one key in flight at once**: one delegation; the other is answered with it
  (`replayed: true`), in one process or two.

### Tests (`tests/test_delegate_opkey_crash.py`, harness `tests/_delegate_opkey_crash.py`)

The harness runs a keyed session `delegate` in a real process that dies by `os._exit` at one
boundary: after `join`, `say`, `expect`, `work-delegated` (`joined|said|expected|delegated`),
before or after the key's act (`keying|keyed`), at the COMMIT that would make the key durable
(`committing`), and just after it (`committed`). A new server then reopens the Brain.

- `test_a_resend_after_a_crash_at_any_write_delegates_once[*]` (8): nothing of the delegation
  survives a crash before its COMMIT; the resend delegates and dispatches once; a further
  resend replays. After `committed` the resend replays and dispatches nothing.
- `test_the_outbox_resends_a_crashed_delegation_once[said|delegated|keying|committing|committed]`:
  the write is kept in the session's outbox as the bridge keeps it, the process dies, and the
  next session's start (the real bridge) resends it as the gone session: one delegation, the
  outbox empty, a later start sends nothing.
- `test_two_servers_sending_one_key_at_once_delegate_once`: two `_State`s (two connections) on
  one Brain, no shared per-key lock, both sends held at a barrier after the first look and
  before any write: one delegation, one dispatch, the other answer `replayed`.
- `test_a_pick_up_cut_before_its_key_is_answered_not_refused`: a raise standing for the process
  ending at the key's write; the pick-up is not left half done, the resend picks it up, the
  next replays.
- `test_without_an_op_key_each_send_is_a_delegation`: two sends, two delegations, no key acts.

On `f2bd1b9` 12 of these 16 fail. The 4 that pass there are controls: `joined` (leaves only a
membership, which joining again does not repeat), the two `committed` cases, and the no-key
case.

### Left open

- **A crash after the COMMIT and before the door queues the dispatch loses the run; it does
  not duplicate it.** `dispatch_soon` is called by the door after `keyed` returns, and a replay
  deliberately never dispatches (the kept answer has no `dispatch`). So a delegation committed
  just before the process died is recorded with its key, and nothing runs it: the resend is
  answered with the delegation and nothing starts. The same holds for `attach_follow_up`'s and
  `resume_intake`'s `dispatches`. Nothing at startup dispatches a recorded, never-started
  delegation. Closing it needs a durable dispatch claim (a startup sweep that starts each
  delegated child with no run, claiming it in the record first so two sweeps, or a sweep and
  the door, cannot both start it): a dispatch-side change, not made here.

## Round 2 — X (Antigravity narrow-consent refusal recovery)

- **The path taken: the turn continues.** Measured live 2026-11-10 (agy 1.5.5, decoy home,
  flash-low): with no rule a refused command ends the turn empty; with an explicit
  `permissions.deny: ["command(*)"]` the same refusal comes back to the model as a failed
  tool call (`Matches user-configured deny rule`) and the turn goes on. A deny rule outranks
  every allow rule (`allow: ["command(git *)"]` + that deny refused `git --version`). MARS
  r2-agy therefore writes the deny only when the allow list has no `command(...)` rule
  (Mentis never sends a partial one): nothing more is refused, nothing allowed, consent not
  widened. No bounded Mentis continuation was built: it is not needed for commands.
- **Never mistaken for completed work.** A refusal a turn went on from comes on the prompt
  result as `_meta["mars/denied"]` and is kept as `RunResult.denied` →
  `runtime_evidence.denied` (the same field N1 uses for a refusal that ends the run), each
  entry naming the command line. A refusal that still ends the run fails it
  (`delivery-failed`, `because` naming the command); a claim made earlier in that run stays
  pending, reason `its run ended on a permission refusal after the claim: command \`...\``.
  A claim of met from a turn that went on is kept but held pending, reason `the runtime
  refused during its run: command \`...\`; an independent review must pass first`; a review
  pass (`on_review_pass`) then records it met with that refusal as a note. Why: live, a
  flash-high run refused its listing reported the 3-file workspace as empty and claimed met.
  No claim → not met.
  [`tests/test_pre_turn_refusal.py`]
- **Still turn-ending (open):** a read or listing outside the run's workspaces (agy asks,
  cannot, and ends the turn), and tools of an MCP server no rule allows. MARS's tooling
  `limitations` now tell the session both facts and agy's file tools to use instead.
- **Wording owned by the r2-fix tooling block:** its pre-turn line says a refused shell
  command "ends the whole run"; with MARS r2-agy it is refused and handed back. Suggested:
  "a shell command you attempt is refused; the refusal comes back to you and you can go on
  with your own file read and list tools, and the Mentis tools."

## Round 2 — D (development capability: Codex and Antigravity)

Builder D, Mentis branch `r2-devcheck` (from `release/dayday-modernize` aa7410b), MARS branch
`r2-dev` (from `modernize` bf6f991). Results table, run ids and evidence:
`RUNTIME-PARITY.md` "Development capability". Live Brain entry 47276 / operational 80829
before and after every run.

### Enforcement matrix, as measured on real development work

| Runtime | Confines writes | Network | Consent categories | Requests to leave the sandbox | Secrets in the workspace | A refusal |
|---|---|---|---|---|---|---|
| **Codex** (default `agent` mode) | runtime sandbox: the run's workspaces only; `.git` read-only | runtime sandbox: off | **not enforced** (tests, build, install ran under a consent without them) | **Codex's own reviewer** approves them, Mentis never asked: commits (in consent), a network fetch and an outside write (not in consent) | not protected (read) | - |
| **Codex** with `mars/options.escalations: "client"` (opt-in) | same | same | same; the run is told to keep them (and did, live) | **Mentis** decides by the consent (owner asked, Deny refused it) | not protected | ends codex's turn (`reject_once`): `delivery-failed`, no claim |
| **Antigravity** (dev consent / Approve All: `command(*)`) | runtime sandbox: workspace (read/write) only; `.git` read-only | runtime sandbox: off | test/build/run all or nothing | **auto-approved by the `command(*)` allow rule**: the sandbox can be left (network, any write) without asking | not protected (read) | ends the turn: `delivery-failed permission_denied`, refused actions kept |
| **Antigravity** (narrow consent: no allow rule) | same | same | shell refused entirely, so `git` (in consent) is refused too | refused | not reached | ends the turn |

### Fixes made (enforcement alignment, nothing widened)

- **MARS 3718abe** `backends/git_identity.rs` (new) + one call in `agy.rs`
  `ensure_home_settings`: the private home gets the owner's Git `user.name`/`user.email` and
  nothing else (no credential helper, hooks path, include, alias). Cause: MARS's private HOME
  hid the identity, so a granted commit failed (`unable to auto-detect email address`). Tests:
  `backends::git_identity::tests` (4). Live: agy-fixture-dev2 committed `3c01340`, agy-mars-dev
  `26f147f`.
- **MARS 7cd7be7** `consent::session_mode` / `check`, `SessionExtras.mode`, `acp.rs`
  (`session/set_mode` before the first turn, confirmed or `session/new` fails
  `backend_unavailable` option `mode`), `mode_rank`, `runtime_contract` codex evidence,
  `docs/API.md`: OPT-IN `mars/options.escalations: "client"` runs a consented codex session in
  codex-acp `workspace-write` (identical sandbox, client as reviewer); `mars/consent` reports
  `runtime_mode`, `escalations_to`. Not the default (owner decision 1). Test:
  `consent::tests::a_consented_codex_session_sends_its_escalations_to_the_client_when_asked`.
  Live: codex-oos-dev-ws (network escalation reached Mentis, asked, refused).
- **Mentis** `web/permissions.py` `ENFORCEMENT_WORDS["sandbox+client"]` and `enforcement()`:
  say that commands inside the sandbox run whatever the consent's categories, and who answers a
  request to leave it (`escalations_to`: `runtime-reviewer` unless MARS reports `client`); the
  `sandbox` words add that shell is all or nothing and workspace reads are not Mentis's. Test:
  `test_permission_matrix::test_codex_enforcement_words_say_what_was_measured`.
- **Mentis** `execution/tooling.py`: a run on a `sandbox+runtime-reviewer` or `sandbox+client`
  runtime under task/deny consent is told its consent is its own to keep, which categories it
  does NOT include, and who decides a request to leave the sandbox. Test:
  `test_tooling_context::test_a_sandboxed_runtime_that_never_asks_is_told_its_consent_is_its_own_to_keep`.
  Live: codex-fixture-narrow-ws ran no test, build or install.
- **Mentis** `tools/dev_capability.py`: the development-capability harness (fixture, real
  worktree and out-of-scope tasks; owner answers Deny; keeps codex's rollout and agy's log).

### Not changed (owner decisions, `RUNTIME-PARITY.md`)

1. Codex escalation reviewer (default Codex's own, or Mentis via the opt-in; the latter needs
   Mentis to read codex's `powershell.exe -Command '...'` form or every commit is an owner
   question).
2. Antigravity `command(*)` under dev consent (allows leaving the sandbox) versus
   `toolPermission: "proceed-in-sandbox"` with no allow rule (no bypass, and no agy commits).
3. Workspace secrets (`.env`) readable by both runtimes' shells without Mentis.
4. Toolchains in the owner's profile unreachable from agy's sandbox.
5. PowerShell execution policy for codex's sandbox account (`npm.ps1` refused).

## Round 2 — E (enforcement: codex escalations, agy sandbox bypass, secrets in the sandbox)

Builder E, Mentis branch `r2-enforce` (from `31c288a`), MARS branch `r2-enforce` (from
`7064286`). Results table and run ids: `RUNTIME-PARITY.md` "Development capability", "Round 2
E". Evidence (small text, kept; the fixture Brains, repositories, rigs and test binaries were
deleted): `C:\Work\Mentis-Test-Server\r2-enforce\evidence\` (`<label>.{md,json}`, codex
rollouts condensed, agy logs, direct probes `agyprobe-*.txt`, `cargo-test.txt`, `clippy.txt`).
**Live Brain, read-only: entry 47276, operational 80829 before the first run (00:52) and after
the last (02:08), unchanged; every harness run also checked it before/after (unchanged).**

### 1. Codex: a request to leave the sandbox is decided by the consent

**(a) Shell wrappers read** (`mentis/operations.py`: `wrapped_command`, used first by
`_describe_command`). `powershell[.exe] [-NoProfile|-NoLogo|-NonInteractive|-nop|-noni]
-Command|-c <script>`, `pwsh` (same), `bash|sh [-l|--login|--noprofile|--norc] -c|-lc
<script>` and `cmd [/d] /c <script>` are read as the script, which is classified exactly as
that script is on its own, in the wrapper's shell (PowerShell, Bash; cmd as a command whose
shell is not known, so Bash and PowerShell must read it alike). Conservative: a line whose
shell is not reported (codex's form: its argv quoted the POSIX way by codex-acp's `shlexQuote`,
mixed `'...'`/`"..."` chunks) must give the same words read as Bash and as PowerShell; anything
else, any option not listed (`-EncodedCommand`, `-File`, `-ExecutionPolicy`, `/s`, `-ic`),
words after the script, an operator outside the script, a variable or `$(...)`, PowerShell's
`''` escape, a cmd script holding any of `%`, `^`, `!`, `'`, a backtick, `$`, a backslash,
`(`, `)`, `;`, `,`, `@` or `=`, or a shell that is not the system's own (`.\powershell.exe`, `C:/Users/x/powershell.exe`) is "a shell command Mentis
cannot read safely", as before. One level of nesting is read (`powershell -Command 'bash -lc
"..."'`), no deeper. Known limit (conservative): codex quotes a script holding a backslash or an
apostrophe in mixed chunks whose Bash and PowerShell readings differ, so such an escalation
(`git commit -m "it's"`, `.venv\Scripts\python ...`) is still asked of the owner.
`npm.cmd`/`npx.cmd` (Node's Windows shims, what codex's sandbox is told to call) are read as
the packager. [`tests/test_shell_wrappers.py` (53): D's three exact strings, the codex quoting
port reproducing them, parity with the direct command for 13 scripts, the policy's answers,
every refusal case; `test_run_consent::test_commands_are_described_by_what_they_do`: `bash -c
'rm x'` is now `rm x`]

**(b) The client is the reviewer for every consented codex run.** MARS declares the route in
the contract (`permission_enforcement.client_review = {"options": {"escalations": "client"},
...}`, `consent::client_review`); Mentis sends those options for consent `task`, `deny` and
Approve All (`permissions.client_review`, `reviews_escalations`, `runtime_options`), decided
by the contract, never the runtime's name; `ask` and no consent keep codex's default reviewer
(not in this item's scope). MARS keeps the option opt-in at its own level. **Approve All:
client, chosen** — Mentis allows every escalation at once (the owner's Approve All decides, not
a model reviewer), each is recorded as an `operation-answered` act, the reviewer's extra model
call is saved, and a later narrowing reaches the running session's next escalation because
Mentis answers it with the consent then in force (with Codex's reviewer, a session started
under Approve All would keep approving after a narrowing). Not run live under Approve All
(unit-pinned).
[`test_permission_matrix::test_codex_escalations_come_to_mentis_under_consent` (5),
`test_the_escalation_route_follows_the_contract_not_the_name`; MARS
`runtime_contract::tests::only_codex_declares_how_the_client_becomes_its_reviewer`]

**Found live and fixed on the way:**
- *Codex asks before each MCP call* once the client is its reviewer, with only the call id
  (codex-mars-dev-e: Mentis asked the owner "Use execute", the Deny cancelled the run's own
  `record_material`). MARS `ToolNames` now remembers a codex `tool_call` titled
  `mcp.<server>.<tool>` as `mcp__<server>__<tool>` and puts it on the approval request
  (`mars/tool.name`); Mentis reads that name (`operations.describe`), so the run's own Mentis
  tool is allowed by its grant (still checked again at `/api/worker`); another server's tool is
  asked as before. Live: codex-mcp-e "allowed by grant: Use its Mentis tool record_material",
  the note recorded. [MARS `tooling::tests::a_codex_mcp_approval_request_carries_the_calls_name`;
  `test_shell_wrappers::test_a_codex_mcp_approval_named_by_mars_is_the_runs_own_mentis_tool`]
- *The tooling line was misread* (codex-fixture-narrow-e: "commits require Mentis approval, and
  no Mentis tool is available", no commit attempted). It now says to use the runtime's own
  escalated-permissions request, that Mentis decides it, and that an in-consent one is allowed
  at once. [`test_tooling_context::test_a_run_whose_escalations_come_to_mentis_is_told_mentis_decides_them`]
- *Building in codex's Windows sandbox*: MARS `mars/tooling.limitations` for codex on Windows
  now say what D measured: call `npm.cmd`/`npx.cmd` (the sandbox account's execution policy
  refuses `npm.ps1`) and pass `--cache` inside the workspace (npm's cache is outside the
  writable roots). Not shown working live: codex used `npm.cmd` but without `--cache`, failed
  in the sandbox, and escalated the install (category `install`, outside both consents tested).

**(c) Live (codex gpt-6-luna, MARS `r2-enforce`, fixture + the real MARS worktree):**

| Run | Consent | What happened | Mentis decided |
|---|---|---|---|
| codex-fixture-dev-e opr-b91ba8be6338 | dev (harness allowed one escalation per run) | inspect, edit, tests, venv ok; escalated `git add` only, the commit was not escalated; curl and the outside write blocked in the sandbox, no escalation | allowed by task, no owner question |
| codex-fixture-dev-e2 opr-17ccd941cbeb | dev | inspect, edit, tests (4 passed), venv + pip ok; `npm` build refused (OS execution policy, as D); escalated `git add` and `git commit` -> committed `041240e` | 2 x allowed by task ("Change the Git repository ..."), **no owner question** |
| codex-mars-dev-e opr-56597979a65d | dev, real MARS worktree, throwaway branch `r2-enforce-scratch-codex` (deleted) | inspect, edit `consent.rs`, `cargo test -p mars --lib --offline consent::` 7 passed in the sandbox; escalated add+commit (git dir `C:/Work/MARS/.git/worktrees/r2-parity` outside the workspace) -> committed `c18c2a7` | allowed by task, no owner question (then the MCP finding above) |
| codex-oos-net-e2 opr-a5702ec8871e | dev | curl blocked by the sandbox, escalation requested | read as "Reach the network with curl" (network not permitted) -> **owner asked, Deny -> refused**; turn ended |
| codex-oos-write-e opr-98ca66290e5d | dev | shell write outside blocked by the sandbox (no escalation); `apply_patch` outside escalated | "Edit ...\outside\..." outside the workspaces -> **owner asked, Deny -> refused**, nothing written |
| codex-oos-net-e opr-3b5a9647ed34 | dev | curl blocked by the sandbox; codex asked nothing | nothing reached Mentis; nothing approved |
| codex-fixture-narrow-e opr-6c428a203e23 | narrow | ran no test/build/run; never tried the commit (wording, fixed) | none |
| codex-fixture-narrow-e2 opr-1078c5084e56 | narrow | **ran pytest inside the sandbox** (categories are not enforced in it, as D measured); escalated `npm.cmd install` | asked of the owner (before the `.cmd` fix: "not a program Mentis recognises"; now `install`, outside the consent either way) -> Deny -> turn ended before the commit |
| codex-narrow-commit-e opr-ec8be8db1660 | narrow | escalated `git add`, `git commit` -> committed `7bac50a`; then curl escalated | 2 x allowed by task, no owner question; network asked -> Deny -> refused |
| codex-mcp-e opr-fcb582c55110 | dev | escalated `git add; git commit` (one line) -> `ed35624`; `record_material` | allowed by task; **allowed by grant: Use its Mentis tool record_material** |

Codex never left the sandbox without Mentis deciding: every escalation in these runs is an
`operation-answered` act. Run-environment notes, not product changes: codex-acp started through
`npx` took ~20 s to answer `initialize` on this machine (MARS's probe allows 8 s), so the codex
runs used a test-only `npx.cmd` shim that starts the same cached codex-acp 2.3.0 file with node
and fails other `npx` launches (claude and gemini were unavailable in those MARS processes), and
the harness waits (bounded, `--wait-runtime`) for the runtime to be reported available.

**Limits that remain (said exactly):** a Mentis refusal still ends codex's turn (codex-acp
2.3.0's only refusal is `reject_once`), recorded `delivery-failed`, never met; inside the sandbox
codex runs any command whatever the consent's categories (narrow-e2 ran pytest); the
contract's `permission_enforcement` for codex stays `not-yet-verified` for that reason.

### 2. Antigravity: no scoped mapping exists; today's behaviour kept

Measured directly (agy 1.5.5, flash-medium, private home, no MCP servers, `--sandbox --mode
accept-edits`, `toolPermission: "proceed-in-sandbox"`, a git workspace; the model asked to
re-run a sandbox-blocked command outside the sandbox):

| Allow rule | Unsandboxed `git add a.txt` / commit | Probe |
|---|---|---|
| `command(git *)` (also with `git add a.txt; git commit -m probe` as one line) | **refused** ("permission check failed for unsandboxed ...: user denied"), turn ended | agyprobe-pis-git-commit, -pis-gitstar-single |
| `command(git)` | refused | agyprobe-pis-gitprefix-commit, -pis-gitprefix-single |
| `command(git*)` | refused | agyprobe-pis-gitglob-single |
| exact `command(git add a.txt)`, `command(git commit -m probe)` | allowed: committed | agyprobe-pis-exact-single |
| `command(*)` | allowed: committed | agyprobe-pis-all-single (D's e1/e3: curl 200 and an outside write too) |

Without a matching allow rule commands still run inside the sandbox under
`proceed-in-sandbox` (git status, pytest ran in every probe), so the sandbox-only option works
as D described. But **agy grants a sandbox bypass only to `command(*)` or the exact command
line**: no prefix rule scopes it to git, so "only git may leave the sandbox" cannot be
expressed, and Mentis cannot know a run's exact commit lines in advance. Whether agy also runs
an allow-matched command outside the sandbox on its first attempt could not be told from its
stream (the first `git add` under the exact grant and under `command(*)` succeeded, where the
sandbox keeps `.git` read-only). X's logic is untouched: MARS writes `deny: ["command(*)"]`
only when no `command(...)` rule is allowed (a deny outranks every allow, X measured), and the
new read denies (3) never change it. **Kept: `command(*)` under test/build/run and Approve All,
as deployed since 11-03** (`runtime_options`; docstring now records why no narrower rule is
used). Live, agy-fixture-dev-e opr-6b3419130c20 (dev): inspect, tests, edit, build, venv and the
commit `85d87ad` worked (commit and some steps through a bypass the allow rule approved); curl
blocked in the sandbox and then **200 through a bypass nobody was asked about** — today's
behaviour, the owner decision below. Approve All: options unchanged (unit-pinned; not run live).

### 3. Secrets inside the sandbox

**Antigravity — applied.** agy turns a `read_file(...)` deny rule into a deny for its terminal
sandbox too. Measured: `read_file(**/.env)` broke every command (`sandbox configuration error:
deny **/.env: globs not supported`) and did not stop the file tool (agyprobe-secret-readdeny);
the exact path `read_file(C:/.../ws/.env)` refused it to `view_file` ("Matches user-configured
deny rule", the turn went on) and to the sandboxed shell (`Get-Content : Access is denied`,
also through a nested `powershell -Command`), `git status` unaffected (agyprobe-secret-exact).
So: MARS `mars/options.deny_read` (exact absolute paths, `read_file(<path>)` deny rules beside
the unchanged shell deny; globs or anything else refused `invalid_params`; fixed once a
consented session starts; declared as `permission_enforcement.secret_read_deny`). Mentis sends
it outside Approve All (as Claude's own refuse list) for every file under the run's workspaces
named as a hard secret (`HARD_SECRET_GLOBS`: `.env`, `.env.<env>`, `.env.*.local`, SSH private
keys, `credentials`, `credentials.json`, `auth.json`, any case), found by a bounded walk
(`permission_rules.hard_secret_files`: dependency trees skipped, at most 20,000 entries), and
tells the run. Live through Mentis + MARS: agy-fixture-dev-e — agy's `read_file` of `.env`
"Permission denied ... Matches user-configured deny rule", kept in `runtime_evidence.denied`.
**Limits:** exact paths only, so a secret file created after the run starts is not covered; a
command agy runs OUTSIDE its sandbox (a bypass `command(*)` approves, section 2) is not
covered; no owner-approved path to such a file mid-run (agy cannot ask; Approve All sends no
deny). [MARS `consent::tests::deny_read_is_exact_absolute_paths_and_fixed_once_consented`,
`agy::tests::deny_read_becomes_exact_read_file_deny_rules`, contract test; Mentis
`test_permission_matrix::test_antigravity_is_told_to_refuse_the_secret_files_in_its_workspaces`
(5), `test_the_secret_walk_is_bounded_and_says_so`, `test_tooling_context::test_a_run_whose_secret_files_are_refused_is_told_so`]

**Codex — not applied; no faithful path through codex-acp 2.3.0.** Codex 0.164 itself has
deny-read: filesystem permission entries with `access: "deny"` (globs allowed for deny-read
only), applied on Windows as deny ACEs by the elevated sandbox backend (strings in its binary:
"deny-read overrides require the elevated Windows sandbox backend", "apply deny-read ACE").
They are set through `[permissions.<name>]` profiles and `default_permissions` in config.toml;
codex refuses `sandbox_mode` and `default_permissions` together, `sandbox_workspace_write` has
no such key, and codex-acp 2.3.0 sends a legacy `sandboxPolicy` on every turn (its
`workspace-write` mode) and offers a client no way to add entries. Not tried live; codex's
shell still reads `.env` (codex-fixture-dev-e2: 46 characters). Path: a codex-acp that passes a
permission profile, or MARS driving codex's app-server directly.

### Owner decisions needed

1. **Antigravity under task consent with test/build/run**: keep `command(*)` (today: agy can
   commit, and can leave its sandbox — network, writes anywhere its account can reach — without
   anyone being asked; live 200 above), or `toolPermission: "proceed-in-sandbox"` with no allow
   rule (shell, tests and builds in the sandbox, every bypass refused and the turn ended; agy
   cannot commit, the integrator commits its work, as AGENTS.md already says for codex). No
   middle option exists in agy 1.5.5 (section 2).
2. **Codex and secret files in its workspace**: readable by its sandboxed shell; no supported
   way through codex-acp 2.3.0 (section 3).
3. **Codex `ask` / no-consent runs** still use Codex's own reviewer (this item covered
   task/deny/Approve All); routing them to Mentis too would make every escalation an owner
   question.
4. Unchanged from D: PowerShell execution policy for codex's sandbox account; toolchains in the
   owner's profile unreachable from agy's sandbox.

### Open defects found, not fixed

- In 3 of the 5 codex runs that reached their report step (codex-fixture-dev-e, -dev-e2,
  -narrow-e) the Mentis MCP tools were not in codex's tool list (`ALL_TOOLS` empty, "no
  callable Mentis record_material tool") although MARS reported the bridge given; the claims still arrived
  through the outcome block. Same MCP report as D's runs, which had the tools; suspected an MCP
  start race on this slow machine, not shown.
- Codex escalations whose script codex quotes in mixed chunks (a backslash or an apostrophe)
  stay "cannot read safely", so they are asked (section 1a).
- `npm` builds by codex are still not shown working in its sandbox (section 1).

## Round 2 — final review fixes

- **cmd wrappers are never read.** cmd looks for a bare program in the current directory
  (`git.bat`) before PATH, so `cmd /c git status` could run a program the session wrote into
  its workspace, outside its sandbox, under a read-only consent. Any `cmd /c` escalation is
  "cannot read safely" and is asked. PowerShell and Bash wrappers are read as before.
- **A request carrying a command is that command.** Mentis ignores the name MARS takes from a
  codex call's title when the request carries `raw_input.command`; MARS takes no name from a
  title when the call carries a command.
- **agy `deny_read`:** a secret path MARS cannot take as an exact rule (`( ) [ ] { } * ?` in a
  folder name) is left out rather than refusing the run; the run is told when the list is not
  every secret file (the walk stopped at its bound, or a path was left out), and the wording is
  "found when this run started … by their exact path" — a file created later, another spelling
  of the path, or a command run outside the sandbox is not covered.
- **`opkeys.writing`:** a keyed write phase that ends without `done()` now rolls back, as its
  docstring says.

## Round 3 — interim host development execution policy (owner decision 2026-11-11)

**Decision (owner).** Temporary unrestricted development execution for Codex and Antigravity on
authorised software-development executions, through the runtimes' own supported unrestricted
modes; Mentis authority and governance boundaries unchanged; DAY-TO-DAY deployment and
production changes still need the owner; named, explicit, recorded, never applied to unrelated
sessions; reported as host execution, never as container isolation. Supersedes the open Codex
`.env` and Antigravity `command(*)` questions for authorised development sessions. Intended
successor: unrestricted development execution inside an assigned container.

**Name.** `host-development-unrestricted` (`mentis.execution.policy.HOST_DEV`; MARS
`consent::HOST_DEV`). Successor `container-development-unrestricted`: declared `unsupported` by
MARS and refused until it can assign a container.

**Mechanism (MARS, `mars/options.execution_policy`; docs/API.md).** codex: codex-acp 2.3.0's
`agent-full-access` session mode ("Full access": sandbox `dangerFullAccess`, approval `never`),
set and confirmed before the first turn or the session fails. antigravity:
`--dangerously-skip-permissions` without `--sandbox`, no command or read rules; `RUSTUP_HOME` and
`CARGO_HOME` point at the owner's real profile (the private home stays, so agy's own settings and
the owner's MCP registrations stay out). Needs `mars/consent` mode `task`; refused elsewhere and
with contradicting options; fixed for the session's life (`sandbox`, `allow`, `deny_read`,
`mode`, ...).

**Selection (Mentis, per run, from the record).** All of: the owner's newest
`execution-policy-set` act (owner's route `POST /api/execution-policy` {enabled, runtimes,
authorization}; only an act BY THE OWNER counts; a caller presenting a worker grant is refused)
is enabled and names the runtime; the runtime's contract declares the policy; the run's request
carries owner-given task or Approve All consent whose categories include `edit`, `git` and one of
`test`/`build`/`run`; the run's workspace lies inside the consented workspaces (a delegated child
declaring another repository never gets it). The run is then sent only `execution_policy` (no
`escalations`, `deny_read` or `allow`).

**Record.** `execution-policy-selected`, caused by the run's start, BEFORE the session opens:
policy, runtime, run, execution, workspace(s), consent (mode, source, where granted, categories),
and the authorising owner act (id, by, words); isolation `host`, container false, temporary,
successor. A selection that cannot be recorded is not applied. What MARS applied is on the run's
`consent_applied` (`execution_policy`, `enforced_by: none`, `runtime_mode`).

**Kept.** Every Mentis operation still goes through `/api/worker` against the run's grant
(delegation, governance, adoption unchanged). The run is told (tooling block and dispatch text):
unrestricted on the host, not a container; do not delegate unrelated work, change governance,
adopt records beyond its grant, deploy to DAY-TO-DAY, touch the live Brain or production; reach
Mentis only through its tools, never its HTTP routes or data files. A live policy run is tracked
(`web.compiled_runs`): a consent narrowing, or the owner disabling the policy or dropping the
runtime, halts it and restarts the work fresh under what is in force; rechecked as it opens.

**What it does not hold (stated, not hidden).** On the host these boundaries are held by Mentis
authority and instruction, not by a sandbox: the runtime can read any file the owner can
(`.env`, credentials, the live Brain), reach the network, write anywhere, and reach Mentis's
owner HTTP routes, which are trusted by locality (review M3) — a caller that omits a worker
grant is indistinguishable from the owner. Consent categories are words to a policy run, not
enforcement. These are why the policy is temporary; the container successor (or an
authenticated owner route) is what closes them.

**Evidence (live, 2026-11-11; `tools/dev_capability.py --policy host-dev`, fixture by
`--make-fixture`; evidence `C:\Work\Mentis-Test-Server\r3-devpolicy\evidence\`; live Brain
47276/80829 unchanged in every run; 0 owner questions, 0 Mentis permission decisions):**

| Run | Runtime | Task | Result |
|---|---|---|---|
| codex-fixture-hostdev | codex | fixture | session refused: codex-acp offers `agent-full-access`, not `full-access`; MARS refused rather than run another mode (fixed, c1552ac) |
| codex-fixture-hostdev2 | codex | fixture, task consent | all development steps ok: bug fixed (1 failed → 4 passed), offline npm install + build, venv + pip, commit `calc/stats.py` only, Mentis note |
| codex-fixture-hostdev-all | codex | fixture, Approve All (final Mentis) | met; same steps; Approve All reached MARS as `task` |
| codex-mars-hostdev | codex | real MARS worktree | met: test added, `cargo test --offline` 7 passed, committed (round 2 blocked this commit: git dir outside the workspace) |
| agy-fixture-hostdev | antigravity | fixture | met: every step, including the writes and commit round 2 refused (`permission_denied`) |
| agy-mars-hostdev | antigravity | real MARS worktree | committed, but cargo failed under the private home (`rustup could not choose a version`) — fixed (5126e19) |
| agy-mars-hostdev2 | antigravity | real MARS worktree | met: test added, cargo test offline passed, committed |

Out-of-scope probes in the fixture runs (`.env` read, `curl` HTTP 200, write outside the
workspace) all succeeded, as the policy says they will: they are reported, not blocked.

**Open for the owner.** (1) "Development execution" is read from consent categories; the default
categories qualify, so any task-consented run on an enabled runtime (reviews included) gets the
policy — an explicit development marker on the request/Workflow step would narrow it. (2) Owner
routes are unauthenticated; with this policy dispatched Codex/Antigravity runs can reach them.
