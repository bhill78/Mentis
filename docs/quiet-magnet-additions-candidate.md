# Quiet Magnet additions — candidate evidence

Request `opr-480c3d1e3467` / `ent-0c1b8e7e9fa0`, under the Magnet Architecture
and Quiet Integration Investigation (`ent-c0d3b497df7f`). Owner feedback
`ent-d9805bb7f8bc`, approval `ent-ea447212ce00`, TEST follow-up `ent-341640ddc1eb`.
Accepted visual/source baseline: `b1146760d8db87f80b0cb6d86fea15a55261425c`.

This report is in preparation. The host/Management package is implemented;
the mini Conversation, indicators and fixture gate packages are still delegated.
No integrated build, browser verification, final code review or running additions
preview is claimed yet. No TEST or DAY-TO-DAY change has been made.

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
Implementation still requires its final independent code/boundary review.

Delegated packages (each a separate claimed clone/branch):

* A: `ent-a452352cbb78`, Mini Conversation, `quiet-magnet-mini`.
* B: `ent-2b8fd79eb947`, puck indicators, `quiet-magnet-indicators`.
* C: `ent-f7aa28249816`, gated fixture/proxy, `quiet-magnet-additions-fixture`.
* Parent: `quiet-magnet-additions`, Management, host, rail, nonmodal expansion,
  realistic history fixture extension, cumulative integration and browser seam.

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

## Focused development checks completed so far

These are development checks, not a claim of final integrated verification.
All started checks below finished in this run.

| Source | Command | Result |
|---|---|---|
| host work before `3bf08983` | `node node_modules/typescript/bin/tsc -b --pretty false` | exit 1, 3 diagnostics from Windows Management/management casing collision |
| host work at `3bf08983` application tree | same typecheck after renaming helper `managementApi.ts` | exit 0, 0 diagnostics |
| `3bf08983` | `node tests/quiet_magnet_management_unit.mjs` | 5 passed, 0 failed/cancelled/skipped/errors |
| `10e7198d` | `python -m pytest -q tests/test_quiet_magnet_functional_fixture.py --basetemp .pytest_tmp/functional-development` | 2 passed, 0 failed/skipped/errors |

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
unchanged by that extension. The gated runtime's separate fixture format will be
seeded afresh rather than overwriting this root.

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
