# B1 correction: Work result paging refresh

Scope: only blocking B1 in independent integration review adm-3cd592e03131
on candidate 35834ea6e5cee9ea17431dd9f5f836707330c5e9. No other package,
route, authorization, Brain binding or mounted UI behavior is changed.

`useApi` and therefore `useWorkDetail` retain their existing `data`, string
`error`, `loading` and same-path `reload()` contract. They additionally return
`errorKind: 'ResultsRefreshRequired' | null`. The property is optional in
`ApiState<T>` for compatibility with callers constructing that interface.

Only the typed error produced by the existing HTTP 409/kind binding sets this
discriminator. An ordinary error with identical prose, a different 409 kind,
or the right kind at a different HTTP status leaves it null. The discriminator
belongs to the current request path, irrespective of the legacy `ownErrors`
message-retention option. It clears on successful reads and does not follow a
reader to another Work, viewer, paging URL, or disabled path.

The cursor owner handles `state.errorKind === 'ResultsRefreshRequired'` by
discarding **all** of `resultsBefore`, `resultGroup`, and `itemsAfter`, then
rendering `useWorkDetail(expectation, viewer, { runs, ...noPagingFields })`.
That starts the first-page read through the existing client. A consumer may
offer that restart explicitly. `reload()` alone keeps the current URL and
therefore is not cursor recovery. Keep the exact Work/viewer and existing
Brain guards. Do not decode cursors or parse the error message.

On refusal, `data` remains the last settled response under the existing generic
hook contract. It is not a newly accepted page, empty results, or permission to
append/skip groups. After cursor discard, replace the displayed result pages
with the successful fresh first page. Cursor/aggregate ownership stays with the
consumer; this correction does not introduce an automatic retry or a chooser.

Focused behavioral evidence is in `tests/work_result_client_unit.mjs` under
`apps/fluid-web`. It executes actual TypeScript modules along
`useWorkDetail -> useApi -> request -> fluidFetch`, replacing only fetch and
React's lifecycle with a dependency-aware state/effect adapter. It covers both
group and item refusal, consumer cursor discard, a fresh first-page read,
replacement data, path scoping, clearing on success/disable, generic errors,
same-path reload and `ownErrors`. The independent original B1 reproducer is
retained separately in the correction evidence. These are client seam tests,
not rendered React/DOM or a mounted chooser acceptance test.

## Current TEST baseline and limits

Read-only inspection on 2026-11-21 found TEST's `/api/server` and
`/build-identity.json` both naming
ca9b4fb8c667bd549b92df23b3eb77e4d2031e83,
release 20261121-ca9b4fb-b4a3cf18. The original 71b06470 baseline is an ancestor
of this candidate, but the new TEST commit is not present in this clone.
No ancestry claim against that unavailable object is made. Reconciliation is
recorded as discovered work (ent-ac9bef522551 / opr-d90f2079c08e); it is excluded
from this B1-only request, which prohibits merging other branches.

Independent re-review should check this correction and the shared hook seam
against the original B1, using the exact returned tip and focused commands in
the correction report. The prior review's other seam verdicts are unchanged.
No new browser surface was changed: no browser, live Brain/MARS, Rust-front,
full-suite, TEST integration, deployment, push or merge is claimed by this
correction. All later product/chooser/opening/return acceptance remains with
the coordinating work. This document is a contract, not an independent verdict.
