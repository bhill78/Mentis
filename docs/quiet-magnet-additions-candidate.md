# Quiet Magnet additions — candidate evidence

Request `opr-480c3d1e3467` / `ent-0c1b8e7e9fa0`, under the Magnet Architecture
and Quiet Integration Investigation (`ent-c0d3b497df7f`). Owner feedback
`ent-d9805bb7f8bc`, approval `ent-ea447212ce00`, TEST follow-up `ent-341640ddc1eb`.
Accepted visual/source baseline: `b1146760d8db87f80b0cb6d86fea15a55261425c`.

Progress report, 2026-11-22 02:56 UTC. All three additions are implemented and
merged into this isolated candidate. The ordinary Windows Edge fixture flow
passed 24 checks, but independent reviews found four mini Conversation async
blockers and one fixture instance-binding blocker. Corrections and the separate
Management/host review are running; this is NOT a final reviewed candidate.
No TEST or DAY-TO-DAY change has been made.

Running fixture: `http://127.0.0.1:8943/quiet2?c=ent-d8263b2315a4&at=1`.
It is for disposable-data inspection while review corrections are pending.
Own clone/branch: `C:/Work/Mentis-workspace/day-to-day/quiet-magnet-additions`,
`quiet-magnet-additions`. No main merge, shared TEST update or push is claimed.

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
The initial implementation reviews below have not yet passed.

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
| A: `ent-78e95beb3302` | `43c59e26`, Codex reviewing Claude author | **block**, `opr-c7fbcbaca2a0`: F1 late success/remount can duplicate a post; F2 successful send clears changed reply intent; F3 Refresh can strand earlier-history loading; F4 overlapping same-root threads can show an older response. Correction `ent-6d81b083e8df` / `opr-f5b1d9eff4b5` is running. |
| C: `ent-cddb9daa4191` | `2cfb940b`, Codex reviewing Claude author | **block**, `opr-81e8c6cf6398`: B1 gate verifies corpus/path but not exact server instance. Synthetic same-corpus copy accepted a write after a relay changed recipient. Correction `ent-0381ccbac762` / `opr-1cffca5e7ca9` is running. |
| Parent: `ent-d5e00a9acf5b` | application `19e6a32d`, Claude reviewing Codex author | Review `opr-0ac6f14c1070` running; no verdict yet. |

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
| clean `b989cf84` | `python -m pytest -q tests/test_quiet_magnet_additions_boundary.py tests/test_quiet_magnet_functional_fixture.py tests/test_quiet_magnet_fixture.py tests/test_quiet_magnet_detached_report.py --basetemp .pytest_tmp/final` | 63 passed in 54.76s |
| clean `19e6a32d` | `npm.cmd run build` | exit 0; built identity matches exact commit, dirty false, untracked 0 |
| application `19e6a32d`, harness `79a372fe` | `python tools/quiet_magnet_additions_browser.py` (Windows Edge headless) | 24 passed, 0 failed/skipped/browser errors; two C posts and one A create, source B and main A post counts unchanged |

All passing rows have zero failed/skipped/cancelled/errors unless a different
count or diagnostic is explicitly stated. Node counts mix test cases and the
existing assertion-runner checks; they are not presented as one suite total.
The final integrated correction commit still needs its focused checks.

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
not be collapsed into a false exact-current-runtime claim. Corrected gate will
require a new armed, verified startup using only this work's own processes.

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
