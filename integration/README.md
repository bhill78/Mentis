# C2 integration handoff

Stage: C2 reader bound to returned C1a terminal contract. No shared route,
GlobalDock, authorization, worker, execution or general viewer file is edited.

Baseline: cumulative TEST commit 71b064703ffe8094cc391555ac1695e0dca60996.
Inventory at start: TEST serving.json release 20261120-71b0647-1587619b and its
RELEASE.json pin that commit. Main/test-integration worktrees also name 71b06470.
The permission-presets prep clone was ca9b4fb8; result projection 2cba081b. Neither
candidate is incorporated here. This work's plain clone and branch are both
activity-recorded-end, claimed lease opr-dbc94a4d4b2f. No suitable existing C2 tree
was found. Worktree/branch/remote/status/unpublished-log inventory was read before
creation. Other leased or serving trees were read only for inventory/source.

## Sole web integrator

Apply the exact section patch, not a replacement web file:

    git apply --check integration/activity-feed-route.patch
    git apply integration/activity-feed-route.patch

The patch reads recorded_end for held as well as evicted feeds, including after
beyond the live tail and when memory has not yet exposed ended_at. Live observation
fields/events/next remain unchanged. Reader errors propagate through existing HTTP
error handling. Route ownership remains Python (the current front forwards GET
/api/*); the Rust owner/integrator must verify the final candidate's route table.

Tests install the exact patch's _routes function in memory for fixture HTTP calls;
the shared source file itself is unchanged. This is package verification, not
integrated-route or front-proxy verification.

## Returned C1a terminal contract

C1a source pin: 21dd13dcccf0c0b1474ae0d06bce0bd858c96d18, returned in
adm-f66db22ea3f6 / ent-bc3c7d0c9a3a. This consumer acknowledges the exact names:
collected_text (string|null; missing/null means unavailable; empty string means
recorded empty text), collected_text_format (work-outcome-reported-v1),
collected_text_chars (Python len, Unicode code points, integer|null), error,
notes, returned_artifacts (exact string IDs), reply_turn, response_owner,
request, request_turn, terminal, exit_code and timed_out. The run ID is derived
from the exact start used to query the end. Existing optional runtime_evidence
and outcome_unclaimed pass through, with their specific diagnostics available
in the disclosure. No text-retention bound is introduced by C2.

The projection also supplies run, end (terminal act ID), act, because, ended_at,
stop_reason (existing terminal alias) and per-field availability booleans. Existing
tool/usage/native_workers fields pass through. Old records are not reconstructed
from final_text. In particular C1a reports that the existing upstream service
normalizes empty RunResult.text to reported=None: C2 preserves what WorkOutcome
and the terminal actually supply and does not claim native transcript fidelity.

The focused C1a contract test reads _retained_end from the exact Git object in
MENTIS_C1A_SOURCE, compiles that function without merging or importing the external
checkout, calls it against disposable fixture records, and reads its actual output
through C2. It checks success/failure/cancel/deadline/exception/empty/missing text,
Unicode character counts, prior-run artifact exclusion, exact answer/request IDs,
held/evicted projection equality and read-only GETs. This verifies the writer/read
seam; full C1a/C1b dispatch and front-proxy integration remain with the carrier.

## Host/navigation integration

RunControls accepts optional referenceWords using the existing RefWords contract
(or inherits RefWordsContext). Its open(id, label) method is called with the exact
reply_turn or artifact ID. The host must resolve availability, Brain identity and
permissions via its existing guarded opener and preserve origin/return context.
No URL is inferred from collector prose. With no opener the UI shows identity and
honest unavailable wording. The fixture supplies a synthetic host, tests exact IDs,
keyboard activation, close and focus return. It does not verify a real viewer,
artifact authorization or integrated Conversation return. The shared UI integrator
must wire this seam; C2 does not edit GlobalDock or the general viewer.

## Verification commands

From the repository root, using the repository venv:

    C:\Work\Mentis\.venv\Scripts\python.exe -m pytest -q tests/test_run_activity.py tests/test_execution_visibility.py tests/test_brain_binding.py tests/test_owner_auth.py --basetemp=.pytest_tmp/c2-final-reader

For the pinned real-writer seam, from the clone root:

    $env:MENTIS_C1A_SOURCE = 'C:\Work\Mentis-workspace\day-to-day\dispatch-answer-ownership'
    C:\Work\Mentis\.venv\Scripts\python.exe -m pytest -q tests/test_activity_c1a_contract.py --basetemp=.pytest_tmp/c2-c1a-contract

The contract test skips when no C1a source is explicitly supplied; supply it for
acceptance. It reads the returned Git object, not uncommitted/live source.
Create .pytest_tmp before selecting a nested --basetemp. From apps/fluid-web:

    node --test tests/activity_recorded_unit.mjs
    node tests/quiet2_hierarchy_unit.mjs
    node tests/brain_binding_unit.mjs
    npm.cmd run typecheck:tests
    node tests/build_activity_fixture.mjs
    npm.cmd run build

Then from the root, with an exclusive lease on fixture port 8947:

    C:\Work\Mentis\.venv\Scripts\python.exe -m pytest -q tests/test_activity_recorded_browser.py --basetemp=.pytest_tmp/c2-final-browser

The browser module runs headless installed Google Chrome at 390px. Its HTTP server
and browser are foreground test-owned resources, joined/closed in fixture teardown.
No live Brain/MARS, screenshots, full suites, other browser engines or TEST changes.
Independent implementation/rendered review and combined C1 dispatch acceptance remain
with the coordinated carrier. The final return report names the exact tested tip
and results; this document is an integration contract, not a test receipt.
