# Quiet Magnet additions — candidate evidence

Request `opr-480c3d1e3467` / `ent-0c1b8e7e9fa0`, under the Magnet Architecture
and Quiet Integration Investigation (`ent-c0d3b497df7f`). Owner feedback
`ent-d9805bb7f8bc`, approval `ent-ea447212ce00`, TEST follow-up `ent-341640ddc1eb`.
Accepted visual/source baseline: `b1146760d8db87f80b0cb6d86fea15a55261425c`.

Review reconciliation, 2026-11-22 03:49 UTC (integrated checks completed 03:37 UTC). All three additions and the two
returned blocking corrections are integrated in `4a08680367e90a97a4f4880da5546e0f0fd1a2aa`.
This exact clean commit builds, passes focused integrated checks, and is running
on a fresh intended-instance-bound synthetic fixture. Windows Edge passed 24/24.
Management/host review and both correction re-reviews have passed.
This is implemented, locally verified and independently reviewed for this bounded
iteration, with known nonblocking findings. It is not deployed to TEST.

Open **Magnet Management -> Island observatory -> Open selected Magnet** at:
`http://127.0.0.1:8963/quiet2?c=ent-26ffd98e3351&at=1`.
The old port-8943 preview is retired. No TEST or DAY-TO-DAY change was made.
Own clone/branch: `C:/Work/Mentis-workspace/day-to-day/quiet-magnet-additions`,
`quiet-magnet-additions`. No main merge, shared TEST update or push is claimed.
The carrier independently assigned TEST continuation `opr-7656b8431f4e` in
`ent-bc4499b65531`; it is not duplicated by this resumption.

## Exact integrated verification on resumption

All commands below completed on clean `4a086803`, with zero failed, skipped,
cancelled or error counts. Node assertion-runner counts are separate from the
Node test-runner cases and are not added into a misleading suite total.

| Command (from apps/fluid-web unless noted) | Result |
|---|---|
| `npm.cmd run build` | exit 0, clean exact commit in dist/build-identity.json; existing chunk/circular-reexport warnings |
| `node --test tests/quiet_magnet_mini_unit.mjs tests/quiet_magnet_management_unit.mjs tests/quiet_magnet_wire_unit.mjs tests/quiet_magnet_read_unit.mjs tests/quiet_magnet_navigation_unit.mjs tests/quiet_magnet_indicators_unit.mjs tests/quiet_magnet_puck_unit.mjs` | Node: 87 passed including two wrappers; mini 50, management 6, wire 2, read 16, navigation 11; wrappers independently report indicators 27 and puck 52 checks |
| `node node_modules/typescript/bin/tsc -p tsconfig.test.json --noEmit` | exit 0, zero diagnostics |
| `node tests/brain_binding_unit.mjs` | 89 checks passed |
| `node tests/draft_keep_unit.mjs` | 84 checks passed |
| `node tests/quiet_space_nav_unit.mjs` | 226 checks passed |
| `node tests/quiet_address_unit.mjs` | 282 checks passed |
| `node tests/quiet_nav_unit.mjs` | 127 checks passed |
| root: `node tools/test_quiet_magnet_additions_preview.mjs` | 29 passed |
| root: `node tools/test_quiet_magnet_preview.mjs` | 13 passed |
| root: `C:/Work/Mentis-workspace/r1-fixtures/venv/Scripts/python.exe -m pytest -q tests/test_quiet_magnet_additions_boundary.py tests/test_quiet_magnet_functional_fixture.py tests/test_quiet_magnet_fixture.py tests/test_quiet_magnet_detached_report.py --basetemp .pytest_tmp/resumed-integrated-4a086803 --junitxml=.preview/resumed-integrated-4a086803.xml` | 88 passed in 92.50s; teardown returned, exit 0 |
| root: same Python, `.preview/quiet-magnet-reviewed/setup-warm.py` | 10 bounded source reads, fixture logical records unchanged |
| root: same Python, `tools/quiet_magnet_additions_browser.py`, `QUIET_MAGNET_FIXTURE=.preview/quiet-magnet-reviewed`, `QUIET_MAGNET_PREVIEW=http://127.0.0.1:8963` | Windows Edge headless: 24 passed, 0 failed/skipped/errors; no page errors; two C posts and one A Magnet creation |

Browser readback: A posts 2 -> 2; B posts 36 -> 36; C posts 40 -> 42.
Exactly one new supported definition/placement was persisted. Main/source posts
are unchanged. The startup gate refused capacity, other writes and encoded aliases.
The UI's source-wide Posts versus loaded Files scope and unavailable Perspectives /
new-item totals remain explicit. No live agent execution was tested or fabricated.

New startup: arm `opr-5517de94c182`, report `opr-6a550abe2ef6`, post
`ent-5049dcc719d3`, completed and verified. Helper PID 57964, launcher 8364,
proxy 68460, Python wrapper 45636, front 44288; actual serving identity is in
`.preview/quiet-magnet-reviewed/ready.json`. Hidden WMI wrapper PID 67460.
Both built UI and backend startup name exact `4a086803`. Later documentation
commits do not change the verified application/helper tree or rebuild identity.
The helper has no restart/retry behavior. This resumption leaves it running.

One failed new attempt is preserved: arm `opr-3ea9329a656d` reached identity
verification, then stopped because its private report config had a UTF-8 BOM.
Failure was explicitly reported in `ent-950ccd2a2f12`; config was rewritten UTF-8
without BOM before the separately armed successful attempt. The helper stopped
its children on that failure. Initial sandbox WMI create was refused; the approved
escalated launch was hidden. No failed launch is claimed as a running preview.

The prior startup reports `ent-e75224215105` (WinError 6, failed) and
`ent-aaae7619400c` (old successful start) are reconciled to original request
`opr-480c3d1e3467`, not the replacement request. The successful older runtime
served backend b989cf84 and later static 19e6a32d, not the corrected exact commit.
After the new preview and browser check passed, its owned helper PID 51060 tree
was stopped explicitly; no unrelated process was selected or stopped.

Read-only TEST check on this resumption: `/api/server` still answered at 8780
with source `ceb306a2eb2aa8caea936f1bedbc97177a2cc649`, PID 14508, Brain
`C:/Work/Mentis-env/test/brain`. Local `git rev-list --count
HEAD..cumulative/test-integration` remains 0. This is not a fresh fetch of the shared
branch and not authority to switch TEST. The exact coordination path below still
applies and belongs to the carrier's continuation.

## Plan and review

Plan: `docs/quiet-magnet-additions-plan.md`. Quill reviewed it on claude/opus-5,
independently of the codex author, and returned `ent-bf4eaee820fb`, verdict
`opr-dc014d9b2569` **block**. The two plan blockers were folded into `e332add9`:
proxy verifies the fixture itself before enabling writes, and global preview
read-only mode stays on with a dedicated, identity-verified scope for only the
mini Conversation and Magnet creation. The revised plan names exact HTTP/state
interfaces, preservation of X-Mentis-Brain, canonical raw paths, nonmodal focus,
unsupported counts and per-resource draft retention. The carrier checked the
revision against both findings; no unresolved plan architectural choice remains.
Initial review blockers below have returned corrections, and both independent
correction verdicts are now pass. The carrier accepts these scoped verdicts on
their source and independent evidence; the known nonblocking findings remain.

Delegated packages (each a separate claimed clone/branch):

* A: `ent-a452352cbb78`, Mini Conversation, `quiet-magnet-mini`.
* B: `ent-2b8fd79eb947`, puck indicators, `quiet-magnet-indicators`.
* C: `ent-f7aa28249816`, gated fixture/proxy, `quiet-magnet-additions-fixture`.
* Parent: `quiet-magnet-additions`, Management, host, rail, nonmodal expansion,
  realistic history fixture extension, cumulative integration and browser seam.

Merged commits: A `e4175602` and `43c59e26`; B `e3992629`; C `2cfb940b`.
Parent owns the strict minimal sender payload seam, common test registration,
Management/host and browser fixture checks. Author corrections use their own
clones and branches; no parent edits are delegated.

| Independent review | Actual source/runtime | Verdict and continuation |
|---|---|---|
| A: `ent-78e95beb3302` | `43c59e26`, Codex reviewing Claude author | **block**, `opr-c7fbcbaca2a0`: F1 late success/remount can duplicate a post; F2 successful send clears changed reply intent; F3 Refresh can strand earlier-history loading; F4 overlapping same-root threads can show an older response. Corrected at `9c2bf87e`, integrated at `23f12726`; **pass** re-review `opr-77250b9ccfa5` in `ent-34f1733c8a78` (Claude reviewing Codex correction), with three nonblocking findings, evidence `adm-ee21e06cb1c2`. |
| C: `ent-cddb9daa4191` | `2cfb940b`, Codex reviewing Claude author | **block**, `opr-81e8c6cf6398`: B1 gate verifies corpus/path but not exact server instance. Synthetic same-corpus copy accepted a write after a relay changed recipient. Corrected at `9e0ebbfa`, integrated at `4a086803`; **pass** re-review `opr-e175a9a7ad1b` in `ent-6c577a8fbc9e` (Claude reviewing Codex correction), no blocking finding, report `adm-b3b6f9f17c94` and probe `adm-869cf00bcb34`. |
| Parent: `ent-d5e00a9acf5b` | application `19e6a32d`, Claude reviewing Codex author | **pass**, `opr-b74b77a6e23a`, result `ent-246beebef289`; no blocker. Scoped UI is byte-identical through `4a086803`. |

A reports: `adm-2e01f510f039`, evidence `adm-db550afa8dd6`.
C reports: `adm-b0c8cda9822f`, evidence `adm-f51a496fc787`.
A's nonblocking F5 cancel/preflight and F6 capability/preflight observations are
deferred, recorded separately as `ent-9531ac841823` / `opr-50cd3616d84c`.
They are not pending blocking work in this candidate.

## TEST investigation and handoff boundary

Read-only inspection at 2026-11-22 01:53:48 UTC:

* TEST address: `http://127.0.0.1:8780`.
* `/api/server` identifies Python PID 14508 on public port 8780, loaded from
  `C:/Work/Mentis-env/releases/20261121-ceb306a-2b2d33fd/code`, source
  `ceb306a2eb2aa8caea936f1bedbc97177a2cc649`.
* `serving.json` names that release. The authoritative environment status tool
  could not match a living front or served interface to a recorded release.
* A harmless GET of `/fluid/api/magnets/mag-readiness-probe/read?mode=summary`
  returns HTTP 404 with `no such Fluid surface`. This confirms the public server
  is missing the native Magnet read route, not merely an unknown saved Magnet.
  Exact response: `.preview/test-native-route-inspection.json`.
* `/api/working` reported no open runs at inspection. This is a point-in-time
  observation, never permission to stop a process or a guarantee at deployment.
* The persistent `test/integration` branch is `ceb306a2`. The Magnet base lacked
  12 of its commits. Parent merged it into its own candidate as `d9bbb028`, using
  ordinary `git merge`; the cumulative shared branch was not modified.
* `git rev-list --count HEAD..cumulative/test-integration` returned **0** after
  integration. This must be rechecked against the actual serving commit and the
  latest shared branch immediately before a carrier-controlled TEST switch.

Required safe integration path: obtain TEST service/path leases and appropriate
coordination grant; reconcile actual serving front/interface identity; fetch the
latest cumulative branch; merge this reviewed candidate INTO `test/integration`
without dropping its commits; commit and push that cumulative branch; build its
exact source with known matching front binaries through `tools/env/mentis_env.py`;
use the normal drain/switch protocol only when it can preserve active work; verify
release identity, native Magnet route and affected browser interactions. No
feature-branch-only replacement, no baseline overwrite, no DAY-TO-DAY restart.
That TEST operation is outside this Builder's isolated candidate grant and has
not been launched. The carrier must coordinate it.

## Focused checks completed so far

These are development checks, not a claim of final integrated verification.
All started checks below finished in this run.

| Source | Command | Result |
|---|---|---|
| host work before `3bf08983` | `node node_modules/typescript/bin/tsc -b --pretty false` | exit 1, 3 diagnostics from Windows Management/management casing collision |
| host work at `3bf08983` application tree | same typecheck after renaming helper `managementApi.ts` | exit 0, 0 diagnostics |
| `3bf08983` | `node tests/quiet_magnet_management_unit.mjs` | 5 passed, 0 failed/cancelled/skipped/errors |
| `10e7198d` | `python -m pytest -q tests/test_quiet_magnet_functional_fixture.py --basetemp .pytest_tmp/functional-development` | 2 passed, 0 failed/skipped/errors |
| clean `b989cf84` | `npm.cmd run build` | exit 0; built identity matches exact commit, dirty false, untracked 0 |
| clean `b989cf84` | `node node_modules/typescript/bin/tsc -p tsconfig.test.json --noEmit` | exit 0; 0 diagnostics |
| clean `b989cf84` | `node tests/quiet_magnet_management_unit.mjs` | 6 passed |
| clean `b989cf84` | `node tests/quiet_magnet_wire_unit.mjs` | 2 passed |
| clean `b989cf84` | `node --test tests/quiet_magnet_mini_unit.mjs` | 33 passed |
| clean `b989cf84` | `node tests/quiet_magnet_indicators_unit.mjs` | 27 passed |
| clean `b989cf84` | `node tests/quiet_magnet_puck_unit.mjs` | 52 passed |
| clean `b989cf84` | `node --test tests/quiet_magnet_read_unit.mjs` | 16 passed |
| clean `b989cf84` | `node --test tests/quiet_magnet_navigation_unit.mjs` | 11 passed |
| clean `b989cf84` | `node tests/brain_binding_unit.mjs` | 89 checks passed |
| clean `b989cf84` | `node tests/draft_keep_unit.mjs` | 84 checks passed |
| clean `b989cf84` | `node tests/quiet_space_nav_unit.mjs` | 226 checks passed |
| clean `b989cf84` | `node tests/quiet_address_unit.mjs` | 282 checks passed |
| clean `b989cf84` | `node tests/quiet_nav_unit.mjs` | 127 checks passed |
| clean `b989cf84` | `node tools/test_quiet_magnet_additions_preview.mjs` | 28 passed |
| clean `b989cf84` | `python -m pytest -q tests/test_quiet_magnet_additions_boundary.py tests/test_quiet_magnet_functional_fixture.py tests/test_quiet_magnet_fixture.py tests/test_quiet_magnet_detached_report.py --basetemp .pytest_tmp/integrated-final` | 63 passed in 54.76s |
| clean `19e6a32d` | `npm.cmd run build` | exit 0; built identity matches exact commit, dirty false, untracked 0 |
| application `19e6a32d`, harness `79a372fe` | `python tools/quiet_magnet_additions_browser.py` (Windows Edge headless) | 24 passed, 0 failed/skipped/browser errors; two C posts and one A create, source B and main A post counts unchanged |

All passing rows have zero failed/skipped/cancelled/errors unless a different
count or diagnostic is explicitly stated. Node counts mix test cases and the
existing assertion-runner checks; they are not presented as one suite total.
Those earlier results are historical; the resumption section above records completed final integrated checks at `4a086803`.

Browser development failures are retained in `.preview/browser-attempt-N.json`
and `.preview/browser-attempt-N.log`, not hidden by the later passing run:
attempt 1 (1 pass, 1 fail) rail inherited pointer-events; 2 (5/1) orbit over rail;
3 (6/1) test pointer probe hit navigation; 4 (18/1) source control exact-label
lookup; 5 (9/1) harness assumed one reply after a previous fixture write;
6 (18/1) source exact-label lookup included option text. Each had 0 browser
runtime errors. Rail/CSS and pointer probe were corrected. The initial Brain
resolution effects were also made non-destructive in `19e6a32d`; a later read-only
diagnostic showed the remaining creation failure was its exact-label locator,
not a vanished form (partial label 1, exact label 0). Attempt 7 passed 24/24.

Independent review evidence is not converted to green product counts: A's
33 author tests passed while six of seven property probes failed; nine rendered
checks confirmed defects. C's resumed benign slice passed 20 with 36 deselected,
but retained copied-fixture evidence substantiated B1. The interrupted C full
run has no confirmed final exit/teardown and is not claimed as passing. All
reviewer-owned processes were subsequently checked/stopped by their reviewer.

Python executable: `C:/Work/Mentis-workspace/r1-fixtures/venv/Scripts/python.exe`.
Node commands run from `apps/fluid-web`; pytest from the candidate root.

## Fixture and limitations

The original setup at `.preview/quiet-magnet-additions` is synthetic, under the
claimed candidate clone. It has separate A (main), B (source), C (pre-existing
Magnet Conversation), held Markdown/file/image records and dated source pages.
`tools/quiet_magnet_functional_fixture.py` adds sanctioned owner/participant,
Conversation and expectation records: 35 history roots, one clearly labelled
historical reply and actual nonexecuting Work. No fake running status or live
agent reply is used. The second Brain, definitions and held artifacts remain
unchanged by that extension. The gated runtime uses a separately seeded root
`.preview/quiet-magnet-functional`, with completed additions-format manifest.
Previous browser posts are deliberately preserved; they are not fixture resets.
Allowed browser writes so far: six C posts across attempts 4, 6 and 7 and one
supported A Magnet creation in attempt 7. No agent was dispatched.

Detached startup: first arm `opr-96bb57615484` failed (Windows stdout handle);
receipt `ent-e75224215105`, owned processes stopped. Corrected hidden wrapper
startup arm `opr-7daa97e59aac` completed and reported via `ent-aaae7619400c` /
receipt `opr-09c34e0b7fee`. Current helper 51060, launcher 42072, proxy 21612,
Python 40752 and front 21832, recorded in this root's `ready.json`. The runtime
startup captured application `b989cf84`; static UI was subsequently rebuilt at
`19e6a32d`. Python source and Rust crates did not change. This distinction must
not be collapsed into a false exact-current-runtime claim. This old runtime was superseded and stopped during resumption; the corrected startup is documented above.

Preview limitations by design: main Conversation remains readable but its writes
are disabled; scoped mini sends record ordinary posts/replies, without dispatching
or starting agents. Starting/resuming agents uses the full supported Conversation
flow outside this fixture. New Magnet creation does not fabricate an own
Conversation. Perspectives and numeric new-item totals are unavailable. Files
are loaded selected results, never an invented collection-wide total; Posts
source tally has its explicit source-wide scope. Source text preview limitations
of the accepted baseline are preserved. Full live-agent execution is untested.

Reusable Rust binaries were copied into this work's `.preview/bin`, never run
from another worker's checkout. `git diff b1146760 -- crates` is empty.
SHA-256 front: `0406877248539ebbc09266e3271d57d07643301e49da4700b742582820840fb8`.
SHA-256 launcher: `48a1148afb338bc281b4cb0fe6b6b86a63a7208ed03401177a1b4a3afbb38cd1`.
No binary rebuild, live Brain, production credential, real agent run or TEST
write has been used for this candidate.

## Completed correction review and remaining coordination

Both correction reviews are complete and accepted for the bounded iteration.
Part A: `opr-9247a3fcc780`, pass verdict `opr-77250b9ccfa5` at exact
`9c2bf87e`; result `ent-34f1733c8a78`. Part C: `opr-b4db58da5905`, pass verdict
`opr-e175a9a7ad1b` at exact `9e0ebbfa`; result `ent-6c577a8fbc9e`. Both used
Claude after Codex authored the corrections. No review was repeated or handed
out again. No code, tests or build changed on this reconciliation; there is no
new test run. Integrated application remains verified `4a086803`.

The Part A evidence ZIP `adm-ee21e06cb1c2` was retrieved and inspected in this
run (digest f55f88e6723f240d733a2f455a58a3b260d0dea6620e2d5ab9e6ce2d1f8e9e89).
Its full report and probe source corroborate the required F1-F4 properties.
Independent checks: 50 author-suite cases reproduced with 0 fail; 12 separate
review probes, 9 pass and 3 fail (the nonblocking findings below), 0 skipped or
cancelled; eight required-property probes fail on pre-correction `43c59e26`
and pass after correction; boundary seam run 28 pass / 0 fail; mini typecheck
exit 0 / 0 diagnostics; headless Edge review 6 assertions, 3 pass / 3 fail,
0 page errors, exposing two of the findings. The review is pass on required
properties, not a claim of zero failed probes. Both new Part C artifact reads
timed out in this run; the complete returned Turn and its independent evidence
summary were read, as were the correction source and its unchanged integration.
The prior Part C review independently reproduced 29 + 13 Node checks, 80 + 3
pytest cases and 60 own probe cases, all passing with teardown; see its report.

The carrier agrees with the review's nonblocking classification under the
iteration criteria: no duplicate/data-losing write, authority breach, essential
navigation loss or build failure is shown. Three recoverable behaviors remain:

* RR-X1: a pending thread invalidated by a top-level send can display no replies
  until the thread is closed/reopened; Refresh explicitly reopens its thread.
* RR-X2: ordinary sends show the misleading put-away/unknown-outcome warning
  while the request is in flight; the send completes and clears it on success.
* RR-X3: Earlier posts stays enabled during Refresh but its click is dropped;
  pressing it again after Refresh reads history.

These are recorded without pursuing a correction in this candidate as
`ent-0fc3b27593ea` / `opr-599c6f1e4b74`. The reviewer recommends improving RR-X2
before owner testing, but this is not a blocking verdict or owner instruction.
The active TEST integrator may separately reconcile work it has already taken.
Management/host F1-F6 remain recorded as `ent-86fbce9c1d83` /
`opr-24974fbb27ec`, unfixed. Root F7 is corrected by `9e0ebbfa`.
Earlier Part A F5/F6 remain deferred as already recorded.

The returned INCOMPLETE flags were inspected read-only. The review clones have
no tracked source changes: `magnet-root-review-19e6a32d` at `19e6a32d` retains
untracked .review screenshots/probes and synthetic .preview data;
`quiet-magnet-mini-rereview-9c2bf87e` at `9c2bf87e` retains untracked independent
probe/render scripts, screenshots and its evidence ZIP;
`quiet-magnet-b1-rereview-9e0ebbfa` at `9e0ebbfa` retains untracked report/probe
files, logs and synthetic fixture copies. These are review evidence, not omitted
implementation patches. They are preserved and were not cleaned, committed or
modified by this run. Two reviewer temp directories could not be listed because
of filesystem permissions; no claim is made about their contents. Nothing from
those directories is needed to establish the tracked source identity.

The existing corrected preview survived the preceding run and answered HTTP 200
on this reconciliation at epoch 1795319191.8731844, 2026-11-22 03:46:31 UTC:
`http://127.0.0.1:8963/quiet2?c=ent-26ffd98e3351&at=1`.
Detached failure `opr-3ea9329a656d` (result `ent-950ccd2a2f12`) remains failed;
its separately armed successor `opr-5517de94c182` (result `ent-5049dcc719d3`)
is completed and verified for startup. Both belong to `opr-480c3d1e3467`.
No new process or restart was required for this reconciliation.

A separate integrator remains assigned under `opr-7656b8431f4e` by the carrier
(`ent-bc4499b65531`), using its claimed `quiet-magnet-test-integration` clone.
That resource and TEST were not built in, tested in, edited, stopped or switched
by this run. This original request still awaits that existing continuation via
`opr-c2643b33ce4a`. Use the existing reviewed candidate and running fixture as
the handoff. No new integration, deployment or review was delegated here. TEST
readiness/deployment must be reported by that integrator from its actual evidence.
