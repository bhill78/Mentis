# C2 integration handoff

Stage: fixture implementation; real terminal binding awaits C1a. No shared route,
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

## Fixture terminal contract; replace only after C1a returns

The fixture detail contains collector_text (string; null/absent means unavailable;
empty string is a recorded empty collector), collector_chars (observed character
count), collector_version (1), error, error_kind, notes (strings), terminal,
exit_code, artifacts (exact string IDs), reply_turn, response_owner and run_start.
The projection also supplies run, end (terminal act ID), act, because, ended_at,
stop_reason (existing terminal alias) and per-field availability booleans. Existing
tool/usage/native_workers fields pass through. No retention bound is introduced.
These collector names are explicitly synthetic until the returned C1a contract is
bound; do not claim compatibility with a real writer from these tests.

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
Independent implementation/rendered review and real C1 terminal acceptance remain
with the coordinated carrier. The final return report names the exact tested tip
and results; this document is an integration contract, not a test receipt.
