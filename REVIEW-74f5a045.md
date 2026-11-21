# Independent review — Python Ask Mentis permission intake, commit 74f5a045

Reviewer runtime: claude 0.97.0, model claude-opus-5, unrestricted host, Windows 11.
Builder runtime: codex/24d51c7f (read from the Turn ent-7294c663dbae, `written_by`).
Reviewed against approved scope ent-89b5beaf5e39 and proposal ent-84bcc33c26bb
(part "Generic intake"), with design review ent-4a7b44c21acb read.

**Verdict: pass. No blocking findings. Six nonblocking findings.**
Recorded as opr-85b7785baf96.

## How this review was set up (where it is and is not independent)

- **Independent:** a different runtime and model from the builder's; a clone of my own
  (`C:\Work\Mentis-workspace\day-to-day\permission-presets-intake-review`, claim
  opr-fbcc095fa0e8) checked out at 74f5a045; the diff re-derived from the baseline
  rather than taken from the report; the builder's suite re-run from scratch; and
  17 probes of my own, written before reading any of the builder's assertions on the
  points they test.
- **Not independent:** the same machine, the same operating-system user, and the same
  repository virtual environment (`C:\Work\Mentis\.venv`) the builder used. The fixture
  Brain is built by the repository's own `mentis.web.fixture`, which is the code under
  review's own test rig, not an outside oracle. I read the builder's hand-off report
  (`.pytest_tmp/verification-report.txt`) and its Turn.
- I changed nothing in the builder's workspace. `git status --porcelain=v1` there is
  empty and HEAD is still 74f5a045. No leased path was entered (composer,
  needs-decision-creation, decision-read-parity, needs-decision-ui). No live Brain, no
  TEST, no Magnet, no deployment, and no unrelated defect was touched or repaired.

## What the change is

Two files beyond the baseline 71b06470, 381 insertions:

| File | Change |
|---|---|
| `mentis/conversation/posting.py` | +68/-7: a validated optional `body.ask_mentis`, its values recorded on the intake expectation, and the authority grant at assignment derived from the recorded `coordinate` |
| `tests/test_ask_mentis_permissions.py` | +320: 47 new tests |

Three commits: aa944a1c (implementation), 0b7d0c7b and 74f5a045 (test-harness
corrections only — I confirmed from the per-commit diffs that neither touches
`mentis/`).

## Test runs I performed (all foreground, all finished in this run)

From `C:\Work\Mentis-workspace\day-to-day\permission-presets-intake-review` at
74f5a045, with `C:\Work\Mentis\.venv\Scripts\python.exe`:

1. `-m pytest tests/test_ask_mentis_permissions.py -q --basetemp .pytest_tmp/review-1`
   → **47 passed, 0 failed, 0 skipped, 0 errors** (11.26 s).
2. `-m pytest tests/test_ask_mentis_permissions.py tests/test_posting_characterization.py tests/test_run_consent.py tests/test_delegate_coordinate.py tests/test_work_continuation.py tests/test_follow_up_attach.py tests/test_worker_boundary.py tests/test_execution_mars.py -q --basetemp .pytest_tmp/review-2`
   → **309 passed, 0 failed, 24 skipped, 0 errors** (69.85 s). Exactly reproduces the
   builder's claimed counts.
3. `-m pytest tests/test_review_probes_types.py tests/test_review_probes_ask_mentis.py -q --basetemp .pytest_tmp/probe-4`
   → **17 passed, 0 failed, 0 skipped, 0 errors** (3.92 s). My own probes, committed
   at f47ecbea on branch `review-probes-74f5a045` in the review clone.

Skips, both unchanged by this commit: 23 through-a-Rust-front worker cases need
`MENTIS_R3_FRONT`; `tests/test_execution_mars.py` is skipped at collection and needs
`MENTIS_TEST_MARS`. Neither was supplied and neither is claimed. Nothing was left
running.

## What I challenged, and what the evidence showed

### Owner-only validation — holds
`posting.py:118-131` refuses a non-None `ask_mentis` unless `action == "ask-mentis"`,
then resolves the owner with the same `_owner(cv)` / `body["author"]` comparison the
existing execution-mode gate uses (`posting.py:286-292`), then validates. All of it
sits **before** `written_by()` is first called at `posting.py:409`, so a refusal does
not even observe the writer. The builder's `test_domain_rejects_non_owner_settings`
and `test_owner_doors_refuse_worker_grants_and_missing_owner_session` cover the domain
call and all three HTTP doors (`/api/conversations/{cid}/turns`, `/fluid/api/posts`,
`/fluid/api/requests`): worker grant → 403, invalid owner bearer → 401, record counts
unchanged. My probe adds the no-declared-owner case: selections are refused while plain
Ask Mentis still works (fail closed).

Its strength, stated plainly: with an owner credential configured, `_owner_refused`
(`web/__init__.py:7368-7386`) requires a live owner session for these POSTs. In
trusted-local mode (no credential) a headerless local POST naming the owner as author
is accepted — `tests/_loop.py`'s `post` sends only `Content-Type`, and the whole suite
passes through it. That is pre-existing and documented (`owner_auth.py:9-15`;
`worker.py:227-241`), and this path is **stricter** than the existing named-request
path, which applies no owner check to `consent` at all (`posting.py:265-276`). See
finding N6.

### `body.ask_mentis` contract — holds
`ask_mentis_permissions` (`posting.py:959-988`) rejects a non-dict, rejects unknown
top-level keys, rejects unknown nested keys in `consent` and `follow_up`, requires
`coordinate` to be a real bool (`1` and `"false"` refuse), and delegates value
validation to the existing `consent_value` and `follow_up_value`. My probes add list,
bool, int and float-depth shapes and a trailing unknown field alongside valid values:
all refuse, with record counts unchanged.

### No unintended authority escalation — holds
`cv.grant_authority` has exactly two call sites in the whole package — intake
(`posting.py:1098`) and named requests (`posting.py:1465`) — and `carry_unaddressed`
exactly two callers (`post` and `resume_intake`). `coordinate` is a new expectation-detail
key nothing else in the package reads. `operations: []` produces one `authority-granted`
act, so `authority_of` returns the single-act answer, not `unresolved`
(`conversation/__init__.py:4842-4875`), and `authority_for` maps it to
`scope: "worker"` with no organising operations (`dispatch.py:643-644`) — the same
grant shape every delegated specialist already receives, so no new shape reaches the
one door or the Rust read-parity matrix. No Rust crate mentions `ask_mentis`, and the
Rust route table owns no POST turns route (only `GET /api/turns`, `GET /api/turns/{}`),
so the transport is entirely Python's, as AGENTS.md requires.

### Absent / on / off coordination — holds
Absent omits the key entirely and keeps today's `AUTHORITY`; `true` grants the same
set; `false` records one act with `operations: []` and its own `because`. Verified at
the record (detail keys, act counts, `authority_of`) and at the **minted grant**: the
builder's `observed` fixture reads the grant the run actually holds, and
`may_coordinate` is false only for explicit `false`.

### Consent and side-work propagation to Work and the execution grant — holds
The recorded keys are the same ones named requests use (`consent`, `follow_up`,
`posting.py:1393-1400`), so the existing readers find them: `consent.of_request` walks
the expectation lineage, `consent.of_run` reports the submitted mode, workspaces and
categories, and `make_policy` answers real operation requests from the run accordingly
— `"once"` for task/all, and for `deny` a refusal recorded as `("deny", "refused")`.
`follow_up_of` and `runs.asked_with` report the Task Gravity. A delegated child cannot
widen (child asking `all` under a `task` parent reads back `task`), coordination is not
inherited by the child, and a return-triggered resume reuses the first grant's
operations with still exactly one `authority-granted` act. The `spec.consent["mode"]`
cap to `task` for MARS is pre-existing code this commit does not touch.

### Late intake — holds
`resume_intake` reads `coordinate` out of the recorded expectation through the shared
`carry_unaddressed` (`posting.py:1097`), never from a submission, so a browser default
changed in between cannot replace it — the builder's test mutates the settings object
between submission and resume to prove it. A second resume is refused and writes
nothing. My probe adds `resume_intake("all")` with two requests left unassigned under
opposite selections (`deny`/off and `all`/on): each keeps its own authority and its own
run consent.

### Duplicates and retries — holds
`ask_mentis` was **already** in the operation-key digest at the baseline
(`git show 71b06470:mentis/conversation/posting.py`, line 94), so proposal item 5 was
satisfied without a change. An unchanged retry replays the first answer and dispatches
nothing; changing `coordinate`, `consent` or `follow_up` under the same key is refused,
on all three doors, with nothing written. My probe adds the case the builder's suite
omits: a submission **refused** for an invalid value does not consume its key — the
owner corrects the value, sends again under the same key, and it is accepted.

### Record-only — holds
`record-only` owes nothing and dispatches nothing, and carrying selections on it is
refused outright. See finding N4 for where that refusal now comes from.

### Unsupported inputs — holds, with one tolerance (N3)
Protected paths, relative paths, missing directories, a whole drive, unknown consent
modes, unknown categories and bad depths all refuse before any write. The one shape
accepted rather than refused is a workspace list with non-string entries — finding N3.

### Continuation and backward compatibility — holds
A post with no `ask_mentis`, or with an explicit JSON `null`, records no permission
detail at all (the expectation's `detail` is unchanged, `{...} or None`) and keeps
today's authority — so every Turn already in the record means what it meant. The 262
pre-existing seam and boundary tests in run 2 pass unchanged. Ask Mentis never
continues earlier work, so the named path's "follow-up permission belongs to the
original request" refusal does not apply and is not needed here.

## Findings

All nonblocking. None loses or corrupts data, breaks navigation, prevents normal use
or a working build, breaches authority or security, or leaves out something the
request requires.

**N1 — the integration seam: an absent `coordinate` still grants the full organising
set.** On Ask Mentis, `absent` means legacy behaviour (full `AUTHORITY`) and only an
explicit `false` grants nothing; on the named-request path, `coordinate: false` and
absent are the same thing (`posting.py:1498`). A composer that serialises the preset
only when coordination is on — the natural implementation, and what the named path
would let it get away with — would give every Ask Mentis the full organising set with
"May Coordinate This Work" unticked. The Python side implements the approved contract
correctly (proposal item 3: "unspecified retains today's generic behavior"); the
asymmetry belongs to the seam, and is the single highest-value thing for the frontend
and integration review to check. Evidence: `posting.py:1097-1104`; probe
`test_untouched_intake_records_no_permission_detail`.

**N2 — what `coordinate: false` costs the carrier, measured.** Scope drops to `worker`
and the carrier loses exactly `{respond, open_topic, open_conversation,
summon_participant, propose_material, deep_dive, resume_intake}`. It keeps `delegate`,
`request_decision`, `request_input`, `record_discovered_work`, `await_work`,
`arm_detached`, every read, the resource claims, `return_artifact` and
`change_workflow`, and it still answers the owner because a dispatched run's exit text
becomes its answer post (`dispatch.py:3654`) — so Ask Mentis still works. But it cannot
post an interim reply mid-run, open a Topic or a Conversation, summon anyone or record
material. This is "off grants none" exactly as approved; it is here so the owner knows
what the toggle costs rather than discovering it. Evidence: `worker.py:242-243, 315`;
`dispatch.py:643-644`; probe
`test_coordination_off_carrier_keeps_what_carrying_needs`, whose assertion on the lost
set is exact.

**N3 — malformed workspace entries are silently dropped and `mode: all` survives.**
`{"consent": {"mode": "all", "workspaces": [null, 7, "  "]}}` is accepted and records
`{"mode": "all", "workspaces": [], "categories": [...]}` rather than refusing, because
`consent._workspaces` skips a non-string entry (`consent.py:234-236`). Not an
escalation — the mode is what the owner asked for and nothing is widened — but it is
the one place a partially malformed selection is accepted, and the proposal asked that
malformed saved data "never become an Allow All default". It is the shared validator's
behaviour, identical on the named-request path (my probe characterises both), and the
proposal lists "empty-list narrowing behavior" among the incidental defects it
explicitly does not fix. The composer should guarantee string entries. Evidence: probe
`test_non_string_workspace_entries_are_dropped_on_both_paths`.

**N4 — two dead guards, and one changed refusal.** The edits at `posting.py:333-334`
(withdrawal) and `posting.py:534-536` (record-only `ignored`) are unreachable: the new
check at the top of `post` already refuses any non-None `ask_mentis` unless the action
is `ask-mentis`, and both of those branches require a different action. One visible
consequence: a post carrying `ask_mentis` with `action: "record-only"` is now refused
outright where at the baseline it was recorded with `refused: ["ask_mentis"]` in the
answer. `ask_mentis` was a reserved, never-consumed field at the baseline, so no
caller is affected, and failing closed is the better behaviour — but the two guards no
longer guard anything and read as if they do.

**N5 — record-shape divergence for `follow_up`.** Ask Mentis stores `follow_up: "ask"`
when the owner explicitly chooses Ask; the named path deliberately omits it
(`posting.py:1396-1398`). Every reader normalises through `follow_up_value` /
`follow_up_of`, so behaviour is identical and I found no consequence; only the stored
detail differs. Cosmetic.

**N6 — owner-only is attribution plus the owner session, not protection from a
same-user process.** Detailed above. Pre-existing, documented, explicitly out of
scope in the proposal, and narrower here than on the existing named path. No new
escalation; recorded so nobody reads the new check as a boundary it is not.

## What I did not check, and did not repair

- The composer / frontend part, including whether the browser actually serialises
  `coordinate: false` (N1). Separate review.
- Rust-front parity (23 worker cases, `MENTIS_R3_FRONT`) and live MARS
  (`tests/test_execution_mars.py`, `MENTIS_TEST_MARS`). Both skipped in the builder's
  run and in mine. In place of running them I checked that no Rust crate mentions
  `ask_mentis`, that the Rust route table owns no POST turns route, and that the change
  introduces no new grant shape.
- Integration seams with the composer branch, and anything on TEST, production, a live
  Brain or a Magnet.
- I repaired nothing. Accepting or rejecting this part is the carrier's or the owner's
  decision.
