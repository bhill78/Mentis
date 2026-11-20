# Known test failures on the integration branch

2026-11-19, `test/integration`. A full run with the browser tests
(`MENTIS_QUIET_BROWSER=1 python -m pytest tests -o addopts=""`) fails the tests below. Every one
was run alone and its cause established (evidence: `C:\Work\Mentis-env\evidence\test-integration\`,
`BASELINE-FAILURES.md`). None was made to pass by changing what it expects.

**No failure here is an unresolved authority or data-integrity defect.** Where a browser test
fails on an owner operation, it fails because the server REFUSED the operation without an owner
session (401, nothing recorded, nothing dispatched). Two user-work-loss risks were found while
investigating, both in legacy interfaces, neither fixed: see the end.

| Group | Tests | Cause | Whose fault | Fix |
|---|---|---|---|---|
| A. No owner session in the browser | 14: `test_quiet_activity_browser` (2), `test_quiet_composer_browser::test_asking_mentis_with_no_dispatch…`, `test_quiet_layout_correction_browser` (2), `test_quiet_r4_composer_browser` (4: hash pick, slash pick x2, slash selects workflow), `test_quiet_r5_reading_browser` (1), `test_quiet_surface_browser` (4) | Since 2026-11-11 every POST but five exempt routes needs an owner session. These pages send none; the server answers 401 and the client goes to `/owner/login`. The "CSP EvalError" some report is the login page's own policy | test | `context.set_extra_http_headers(owner_headers())`, as `test_quiet_navigation_correction_browser` now does |
| B. Owner session, and a renamed control | 4: `test_quiet_composer_browser` (2), `test_quiet_r4_composer_browser` (2) | as A, then a locator for a title that was reworded on 11-11 ("…runtime, model, effort, permission and execution") | test | owner session and the current title |
| C. Owner session, title, Permission wording | 2: `test_quiet_track3_correction_browser` | as B, then "Routine work" is now "Allow routine operations" | test | three text updates; its dispatch assertions hold |
| D. Mark 1 conversation tests | 2: `test_quiet_chat_browser::test_quiet_chat_real_api` (owner session, then reads the record before the door has answered), `…::test_quiet_chat_reconciled_findings` (expects the newest page where Mark 1 now stays on the page asked for; not walked to its end) | test | rewrite, or retire with Mark 1 |
| E. 3D Brain placement the owner replaced | 6: `test_quiet_space_matrix_browser` (5), `test_quiet_brain_space_browser::test_quiet_hosts_the_graph` | On 2026-11-18 the owner ruled the graph always opens full screen in its own stage. These tests (11-17) expect a column, Maximise/Restore and "Close viewer". With only the obsolete controls swapped in a copy, their assertions pass | test | rewrite for the full-screen stage; two (column room, second surface beside the graph) no longer apply |
| G. A delivery row gained a field | 1: `test_activity_step` | rows gained `for_expectation` on 11-14; the test compares an exact dict. What the agent is given is unchanged | test | add the key to the expected row |
| H. Two readers of runs disagree | 1: `test_live_fields` | `agents_runs()` gained `workers` on 11-16 and `run_observations()` did not. Nothing reads the missing field today | PRODUCT, latent | add `workers` to `run_observations` and its Rust type, or state the exclusion in the contract |
| J. A helper is not built | 2: `test_brainlock_claim` | needs `MENTIS_R3_CLAIM_READER` naming `claim_reader.exe`; with it set all 12 tests in the file pass | environment | build it and set the variable for suite runs |
| K. Installer proof | 1: `test_windows_installer` (runs only because `-o addopts=""` drops the default deselection) | (a) the proof looks for a source line that changed on 11-13, so its migration steps cannot run; (b) `uninstall.exe /S` leaves files whose paths exceed 260 characters | harness (a), PRODUCT (b), installer only | fix the proof's marker; shorten the updater's damaged-copy path. Matters only if the Windows installer is shipped; the release path to DAY-TO-DAY and TEST does not use it |
| L. A stale lock file | 4 errors: `tests/bench/test_sql_trace.py` | the probe's own `Cargo.lock` predates a dependency added on 11-13, so `cargo build --locked` refuses | test input | regenerate `tests/bench/trace_probe/Cargo.lock` |

Groups A to D drive the archived Quiet Chat Mark 1 interface at `/quiet`, not the current one at
`/quiet2`. While they fail, nothing in the suite covers, in a browser: answering an owner decision
from the Mark 1 rail, stopping a run, the posted body from the Mark 1 composer, reply targets,
saved appearance settings.

Fixed on this branch on 2026-11-19 and no longer failing: the declared run shape
(`test_quiet_seam_browser`, re-recorded from the handler), the compact settings test
(`test_quiet_navigation_correction_browser`, given the owner session), and the eye-travel check
(`test_quiet_brain_space_browser::test_choosing_moves_the_eye_in_the_hosted_graph`, which failed
about one run in ten for test-side reasons: a hovering pointer, random star positions, and waits on
this process's clock instead of the page's).

## User-work-loss risks found while investigating (NOT fixed)

1. **Legacy Fluid, creating a Brain record.** Escape, Cancel and the close button discard a
   half-written record with no question (`surfaces/governance/R2Forms.tsx`, hosted by
   `fluid/governance/GovPage.tsx`; the leave question is shown only to a host that passes `quiet`,
   and none does). Fluid is still the default route. Quiet Chat's compact editor and its revise
   editor ask before discarding. Recorded as finding `opr-3f8e9ea1a367`; a plan exists, no code.
2. **Archived Mark 1 (`/quiet`), posting without an owner session.** The post is refused (401) and
   the page goes to the login; on return the typed words are gone, because Mark 1 keeps drafts in
   memory only. Mark 2 (`/quiet2`) keeps the draft. Staged attachments were not exercised.
