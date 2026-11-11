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
- **D-I15: `delegate`'s key is still written just after it,** not in its
  transaction: delegating asks the agent service which runtimes are eligible
  and that must not hold the write lock. A per-key lock in-process makes a
  concurrent resend wait; a crash between the two commits remains a window
  for one repeated delegation.

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
| **Claude** (`enforced_by: client`, compiled rules) | Approve All: every tool by its compiled allow. `task`: Mentis's own tools (each checked again at `/api/worker`). The ask list forces everything else to the client. Outside Approve All, `refuse` (Claude `deny`): secrets by name anywhere and the protected locations — Read refused, and the files kept out of Grep and Glob results (measured). | `allowDangerouslySkipPermissions: false`; a resumed session set back to `default`; deny→ask mapping; consent workspaces as additional directories; every command starts in the cwd | every Bash/PowerShell/Read/Grep/Glob/edit/web call outside Approve All, and anything else Claude asks; a recursive shell search (`grep -r`, `rg`, `findstr /s`) over a directory holding secret files it does not exclude is asked of the owner (refused under `deny`) | tools of other MCP servers a session is given that the owner's/project's Claude settings allow (which servers: Builder M); the halt window (below) | `test_permission_matrix` (`test_outside_approve_all_*`, `test_what_claude_ran_unasked_*`, `test_compiled_rules_never_reach_edits_or_shell_*`, `test_protected_locations_*`, `test_shell_commands_start_where_mars_declared`); MARS `consent::runtime_rules_never_broaden_the_consent`, `acp_tests` (rules mapping, headless env), `tooling::claude` |
| **Codex** (`enforced_by: sandbox+client`) | codex-acp 2.3.0 default mode `agent` ("Auto review"): workspace-write sandbox, network off; acts inside the sandbox without asking; escalations go to Codex's own auto-reviewer, which asks the client only for what it judges unsafe (read from codex-acp's mode table; **not live-verified**) | consent workspaces as writable roots; user MCP servers disabled per session | what Codex escalates past its auto-review | reads inside the sandbox (protected locations included, where readable); escalations the auto-reviewer approves | `test_permission_matrix::test_only_claude_is_given_runtime_rules`, `test_every_run_tells_mars_its_consent_*`; MARS `consent::each_backend_says_how_consent_is_enforced`, `tooling::codex` |
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
request; no worker op reaches it. `session-coordination-revoked` withdraws it at once. Nothing
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
  `runtime_rules.refuse: 52` applied. Consequence (stricter than Mentis): outside Approve All a
  Claude run can never read a secret file by name, even with the owner's approval; the owner
  uses Approve All for that.
- *Every runtime's shell*: `operations._describe_command_as` + `mentis/secret_search.py`: a
  recursive `grep`/`egrep`/`fgrep` (-r/-R/--recursive/-d recurse), `rg` (always; hidden files
  only with --hidden/-uu) or `findstr /s` over a directory holding secret files it does not
  exclude (`--exclude`, `--exclude-dir`, `rg -g '!…'`) counts as touching a protected location:
  asked of the owner, refused under `deny`, allowed under Approve All. Live: `grep -rn FAKE .`
  became an owner question naming `.env`.
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
