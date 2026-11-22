# Result-first navigation: the cumulative candidate, mounted

**Candidate `6b1e4d072651fd320394751c09014a878a7121fe`**, branch
`result-nav-cumulative-mounted`, in the separately claimed plain clone
`C:\Work\Mentis-workspace\day-to-day\result-nav-cumulative-mounted`
(worktree lease `opr-8f933c1d6bea`, ports 8891/8892 claimed and in the end not
needed — the mounted checks bind an ephemeral loopback port of their own).
Every count in this document was measured on that commit; the branch tip adds
this document and nothing else.

This is **implemented, built and verified against its own targeted checks**.
It is not reviewed, not merged, not integrated into `test/integration`, not
pushed and not deployed. TEST, `main`, production and every other workspace
were untouched; see "Workspaces preserved" below.

## What is in it, and what each part is

Four merges onto one line, in this order:

| In | Commit | Status it came with |
| --- | --- | --- |
| reviewed projection/activity baseline reconciled with TEST `ceb306a2` | `b11ad75f` | focused checks passed; reconciliation itself unreviewed (`ent-834627a37757`) |
| P4 clean-clone correction | `cce3ed93` | corrected and re-reviewed (`adm-c3baadeaa81a`); **contains `b11ad75f`** |
| result opener, operation-ownership correction | `c39cf709` | independent re-review **pass**, verdict `opr-c8f5cdd9f0da`, report `adm-0c40c5395a16` |
| result chooser | `2434a932` | committed and fixture-tested; **no recorded independent review** |
| what TEST serves now: the reviewed Quiet Magnet candidate | `90f5642f` | reviewed and **deployed to TEST** as release `20261121-90f5642-382af24b` |

`cce3ed93` already contains the reconciled baseline, so the baseline is not a
separate merge: `git rev-list --count b11ad75f..cce3ed93` = 21, the other way
0. The opener shares history with P4 to `3a59d4a6` and diverges by 7 commits
against P4's 44 (the baseline included). The chooser branches from
`2cba081b`, an ancestor of P4, by 3 commits.

Then the host wiring, which is this candidate's own work (`ea99c7b3`), and
then the reconciliation with the current TEST head (`6b1e4d07`).

## TEST moved while this round ran, and the candidate follows it

`C:\Work\Mentis-env\test\serving.json`, read directly at the end of this work,
names release **`20261121-90f5642-382af24b`**, commit
`90f5642fdc320e3e1d257256553fab16b2be5d65`, serving since
**2026-11-21 22:52:36 -0500**, previous `20261121-ceb306a-2b2d33fd`. Its
manifest describes it as "cumulative TEST baseline ceb306a2 plus reviewed
Quiet Magnet candidate: mini Conversation, real supported puck counts, Magnet
Management, and reviewed lifecycle/fixture binding corrections".

That is **one release later than the `ceb306a2` this round's baseline
reconciliation (`b11ad75f`, note `ent-834627a37757`) was built against**, and
it changes one of that note's own conclusions: Magnet is no longer "not in the
accepted TEST baseline". Before the reconciliation this candidate lacked **71**
commits TEST serves and would have dropped the whole newly accepted Magnet
stream; `AGENTS.md` requires that count to be 0 before any TEST deploy. After
it, `git rev-list --count HEAD..90f5642f` is **0**, and the other way 55.

Ordinary `git merge --no-ff`, merge-base exactly `ceb306a2`. Five files were
touched by both sides since then; three conflicted, and each resolution keeps
both behaviours rather than choosing:

- **`quiet2/address.ts`** — both arms added to `CentreAt`, and both to
  `placeOf`'s legacy-entry test. A Magnet entry and a result entry are
  different places and neither replaces the other.
- **`quiet2/results/mount.ts` `whereOf`** — the Magnet stream added a
  `'canvas'` place to the viewer store, which `Shown` does not have. A viewer
  on the canvas is in neither the maximised place nor a working column, so it
  answers `'none'` there exactly as `'parked'` does: it displaces no centre and
  owns no history entry. Nothing claims a result can be placed on the canvas.
- **`quiet2/Quiet2.tsx`**, three hunks — the viewer frame keeps the Magnet's
  own `guardedViewer` on move/maximise/restore while Close still routes
  through the result part (whose plan for an unregistered `magnet-item` viewer,
  which has no post source, is the baseline's bare close); `toSource` takes the
  Magnet arm first and then the result arm, the two being exclusive by
  construction; and the column chooser's placement, which TEST had moved into
  `chooseViewer`, is now `placeChosen` reached through the chooser's own
  `decide`, so the three buttons still say only where and whoever asked owns
  the placement. The Magnet item opener's own "every column is in use" path
  goes through the same `chooseWhere` helper.
- **`tsconfig.test.json`** — the one include list, both sets kept. (TEST's copy
  had been reformatted by a JSON round-trip; the compact form is kept.)
- `quiet2/places.ts` and `quiet2/viewer/viewers.ts` auto-merged.

## Included dependencies and conflicts, exactly

**Merge 1 — opener `c39cf709` onto P4 `cce3ed93` (`f97c3ff4`).** One content
conflict: `results/mount.ts`, where both streams add optional `ResultPage`
members. Both kept (P4's `viewer`/`resultNow`/`refNow`; the opener's
`confirmServing`). `HOST-INTEGRATION.md`, `results/opener.ts` and
`tests/quiet2_result_{mount,history}_unit.ts` auto-merged.

Two seams the auto-merge could not see, both because P4 forked before the
opener's F4 and press-time read landed. **No product behaviour was changed to
make a test pass**:

1. `tests/quiet2_result_p4_unit.ts` built a host with the old three-argument
   `record(entry, go, stay)`; the opener's F4 made it `record(begin, stay)`.
   Its `record`, `pickConversation` and `openPost` are brought to the wiring
   `HOST-INTEGRATION.md` §1.2 documents and `quiet2_result_mount_unit.ts`
   executes — `begin()` inside the guard, the reference and report from its
   answer.
2. The opener's seven commits added blocks to
   `tests/quiet2_result_mount_unit.ts` that press a post, record or
   conversation result and assert synchronously. Under P4 every such press is
   described again before anything moves, so those blocks now wait for the
   read — exactly the change P4 itself made to the blocks that existed when
   it forked. Two assertions take their read-first form (`leaving` on the
   press, `opened` once the read answers). Net +2 checks (1020 → 1022).

**Merge 2 — chooser `2434a932` (`3d110e09`).** One content conflict:
`apps/fluid-web/tsconfig.test.json`, the single `include` list several parts
add to. Both sets kept, as §3.4 requires. Nothing else overlapped: the
chooser's files under `src/quiet2/results/` (`ResultChooser.tsx`,
`ResultsEntry.tsx`, `host.ts`, `results.css`, `words.ts`) are disjoint from
the opener's.

## Excluded, and why — none of it guessed

| Not included | Why |
| --- | --- |
| **Needs You** (`needs-decision-ui`, `35859019`) | under Builder correction in its own held workspace; not in TEST. Its workspace was read only (HEAD and dirty count unchanged) and nothing of it is here. |
| **`GlobalDock.tsx` §2 of the handoff** | the Needs You stream owns those rows and holds them under correction; §2's `Openers`/`NeedsItemRow` changes belong with it, not with this integration. Recorded as discovered work, not applied. |
| **Magnet's ongoing candidate** (`quiet-magnet-candidate`, `b1146760`) | the *reviewed* Magnet work is IN, through the TEST head `90f5642f` above. What stays out is the working candidate the owner asked to go on improving (Magnet Architecture #134): `b1146760` is not what TEST serves and is nobody's accepted baseline. |
| **`worker-atomic-answer` `d239e1ca`, `dispatch-answer-corrections`** | unreviewed, and outside result navigation. |
| **`result-target-opener` `9118db60`** | superseded by the opener lineage this candidate merges. |

The **chooser is included although unreviewed**, and that is a judgement, not
an oversight. Its actual status, read from the record rather than assumed:
committed with fixture checks (`quiet2_results_unit`, 143 checks; a
keyboard/narrow browser check in `tests/test_result_chooser_browser.py`), and
its independent rendered review was *attempted* at Turn 85 and never
confirmed — Mentis timed out before recording the assignment, and no verdict
for `2434a932` exists. It is included because it is the **visible half** of
the deliverable: `Post.tsx` draws its "Results" entry on the posts the record
maps, and the opener is the operation behind that press. Mounting one without
the other leaves either no visible way in or nothing to open what is chosen,
and no mounted check of the owner's §2/§3 would be possible at all. **The
rendered review this candidate is handed to is its first review.**

## The host is wired, not described

`mountResults` had no caller outside `results/` and its tests; the production
host had no `mountResults` call, which both the handoff and the independent
review named as the thing a successful build does not give you. Now:

- `src/quiet2/Quiet2.tsx:2202` — `results.current = mountResults(resultPage)`,
  an ordinary expression in the component body, re-made every render.
- the centre's `apply` asks `R.applyCentre` first (B4.2, F7-R2b, F16, B2).
- every viewer-frame Close and Go to source routes through `R.closeResult` /
  `R.goToSource`; an ordinary picture keeps N3's reveal.
- one `ColumnChoice` for both callers; the three buttons say only where.
- `pickConversation`/`openFromDock`/`showPost` carry their guarded ends
  (F4/F5) through one route; `guarded()` takes `stay` (B3).
- a dock file press goes through `R.openResult`, so it is described again on
  the press and fails closed (B4.1).
- the explicit return bar is drawn (`data-control="result-return"`) and its
  press applies the launch's own `restoreSteps` plan. It is offered, never
  taken (H4).
- no Brain identity and no fresh read are wired: `mount.ts` reads
  `serving.ts` and `refRead`/`refNow` itself (F1/F2/F3, B4.1).
- `src/quiet2/results/fromWork.ts` (new) is the §3.3 seam the handoff left to
  the integrator: the chooser's exact `WorkResult` as the opener's
  `ResultDestination`, `destinationOfTarget` (§3.2), and the post mapping from
  the server's own `origin`/`update_turns`. Nothing inferred; provenance
  carried, not restated; the producing post never borrowed.
- `Post.tsx`'s chooser is lent its host from the conversation's existing
  bounded `/api/work?conversation=` read (`runs: false`), and its `more` reads
  are the same work-detail route with the server's own cursors.

## Checks run, on this exact commit

Node, `apps/fluid-web`, 33 suites, **all exit 0**:

```
quiet2_result_targets 100 · opener 152 · viewable 44 · host 63 · mount 1022
quiet2_result_history 184 · serving 38 · p4 69 · results 143
quiet2_results_from_work 43 (new) · needs_inspect 49
work_result_client 8/8 · work_result_freshness 29/29 · activity_recorded 7/7
quiet_address 282 · quiet_nav 127 · quiet_sources 140 · quiet_space_nav 226
space_session 96 · brain_binding 89 · fluid_workspaces 206
quiet2_hierarchy 44 · quiet2_refresh 24 · quiet_post 55 · quiet_media 11/11
permission_default 197 · permission_lifecycle 109 · permission_send 92
quiet2_permission ok · quiet2_usability ok
quiet_magnet_mini 50/50 · quiet_magnet_management 6/6 · quiet_magnet_indicators 27
```

The last three are the reconciliation's boundary: the Magnet suites of the
TEST head, run here because this candidate touches `address.ts`,
`results/mount.ts` and the shared host they share.

0 failed, 0 skipped, 0 cancelled, 0 todo. `npm run typecheck:tests` exit 0,
`npm run build` exit 0 (pre-existing dynamic-import and chunk-size warnings),
`node render-check.mjs dist/render-check.js` exit 0.

Python, targeted, one run on the exact commit:

```
C:\Work\Mentis\.venv\Scripts\python.exe -m pytest -q \
  tests/test_result_routes.py tests/test_result_destinations.py \
  tests/test_result_destinations_scaling.py tests/test_result_readability_contract.py \
  tests/test_p4_corrections_routes.py tests/test_current_work.py tests/test_read_model.py \
  tests/test_run_activity.py tests/test_run_interruption.py tests/test_execution_visibility.py \
  tests/test_activity_c1a_contract.py tests/test_worker_boundary.py tests/test_worker_read_gate.py \
  tests/test_brain_binding.py tests/test_owner_auth.py tests/test_ask_mentis_permissions.py \
  tests/test_composer_permission_payload.py tests/test_result_mounted_browser.py
→ 277 tests: 254 passed, 0 failed, 0 errors, 23 skipped, 84.47 s
```

All 23 skips are `MENTIS_R3_FRONT names no front`. `MENTIS_C1A_SOURCE` was set
to this clone after fetching the pinned object `21dd13dc` into it, so the C1a
contract tests ran rather than skipped. Synthetic fixtures only: no live
Brain, no MARS, no dispatch (`world` captures dispatches), everything under
`--basetemp evidence/pytest-tmp2`. JUnit XML: `evidence/pytest-targeted.xml`.

### The mounted checks, and what they actually drive

`tests/test_result_mounted_browser.py` (new, opt-in `MENTIS_QUIET_BROWSER=1`):
the **built interface served by a real Mentis server over a disposable
fixture Brain**, in headless Chrome 157, over the owner's own §8 scenario —
25 generations of returned mockups, each with a mapped carrier update, buried
under 50 later replies about delegation and review routing. 3 passed.

1. **The record's own mapping.** The server's `/api/work?conversation=` answer
   is read first; then the mapped carrier update is reached the way a reader
   reaches it ("Read earlier posts" back through the chatter), its Results
   entry is opened, and the chooser lists that generation's exact files by the
   names the server holds them under. A post the record maps nothing to
   carries no chooser.
2. **The deliverable, and the way back.** Pressing a result opens the file
   itself in the page's viewer with **exactly one** history entry for the
   displacement; its own Close gives up the viewer and puts the reader back at
   the post they pressed, with that post's Results entry where it was.
3. **360px.** No horizontal page overflow with the chooser closed or open, the
   popup's own box inside the viewport, its rows laid out with real boxes, and
   the chooser opened by keyboard alone.

Check 3 found a real defect and it is fixed in this candidate: the chooser
popup is positioned from an indented wrapper (`left: 0` on
`.q2r-entry-wrap`) while its width was measured against the viewport
(`100vw - 24px`), so **24px of every row sat off-screen at 360px**. It is now
clamped to the post it hangs under (`max-width: 100%`, and `width: 100%` in
the narrow query). The check fails if it returns.

## Silent background change, and the preserved result's return path

Both were assessed against the mounted candidate, not re-derived.

**The silent centre change (`opr-182b26d35c91`) is real in the mounted host
too, and remains non-blocking.** When result A's applied landing completes
while a separately accepted result B is still maximised, A's restore runs
through this host's real setters — thread, reading position, reply target —
so the centre under B does change, and nothing says so: `page.say` is reached
only on a refusal. What the mounting adds to the reviewer's reading is where
the reader is standing: B is maximised *over* the centre, so the change is not
shown to them at the moment it happens, and when B's own close gives up the
frame it is a frame-only close, which **offers** B's original launch as the
way back rather than navigating anywhere. The reader is therefore never
stranded without a stated way out of it. No data is lost: B keeps its renderer
state and its whole launch, which is what the B2/B2-R2 corrections established.

**The preserved result's actual return path now exists as a control.** The
review was explicit that it had verified a retained return *object* and an
executable plan, and certified no mounted pill. This candidate draws that pill
(`data-control="result-return"`), and its press applies
`restoreSteps(launch, …)` through the same page members the ordinary close's
restore uses — `pickConversation` for another conversation, `centre.replace`
for the centre, and `putBack` for thread, reading, reply and draft place. So
the return path is wired to verified code. **Its own click is not exercised in
a browser here**: the pill is owed only by a frame-only close of a maximised
result that does not own the entry it is on, which needs the pending-walk
interleaving the synthetic probes construct and which I could not reach
through the real history API from Playwright. The ordinary close's return IS
exercised, mounted, in check 2.

## Limits — what this candidate does NOT claim

- **Not reviewed.** No independent review of this integration, its seams, the
  host wiring, `fromWork.ts`, or the chooser at all.
- **Nothing left running.** The mounted checks start and stop their own
  server; there is no preview process running at an address. Launch
  instructions are not a preview, and none is claimed.
- **No owner-facing smoke pass** in a visible Windows Chrome/Edge window; the
  browser checks are headless.
- **Not exercised:** the pill's own click (above); `GlobalDock.tsx` Needs You
  rows (excluded); a real Brain switch, 409 `BrainChanged`, revocation or
  authorization change in a browser; the Rust front (`MENTIS_R3_FRONT`
  unset — 23 skips); live MARS or any dispatch; screenshots.
- **The chooser's own browser suite** (`tests/test_result_chooser_browser.py`)
  was not run: it needs its separate Vite harness build and is superseded for
  this candidate by the mounted checks, which drive the chooser in the real
  page.
- **Pre-existing, untouched:** `apps/fluid-web/review/opener-recheck.mjs` R1
  still asserts obsolete handoff snippet text and still fails on both the
  parent and this candidate (`opr-26595de23754`). It is a stale documentation
  oracle, not a product regression, and was deliberately not edited.
- No TEST, `main`, production, push, merge or deployment of any kind.

## Workspaces preserved

Read only, and unchanged in HEAD and in uncommitted state, before and after:

| Workspace | HEAD | dirty entries |
| --- | --- | --- |
| `result-nav-test-reconcile` | `b11ad75f` | 1 |
| `fix-p4-clean-clone` | `cce3ed93` | 0 |
| `result-opener-opgate-correction` | `c39cf709` | 23 |
| `quiet-result-chooser` | `2434a932` | 0 |
| `needs-decision-ui` (Needs You, held) | `35859019` | 1 |
| `result-target-opener` | `9118db60` | 1 |
| `result-opener-b1b2-correction` | `1fcaefd8` | 17 |
| `result-opener-rereview-c39cf709` | `c39cf709` | 27 |
| `p4-clean-clone-rereview` | `cce3ed93` | 1 |

Nothing was committed, stashed, cleaned, reset or removed in any of them. This
clone was made with `git clone --no-hardlinks` from `fix-p4-clean-clone` and
its dependencies are a copy, not a junction. Its own `evidence/` directory is
untracked and holds every log and the JUnit XML.

## For the independent rendered review

Review the exact commit `6b1e4d072651fd320394751c09014a878a7121fe` in a clone
of your own, on a runtime other than Claude (this candidate's author).

Build before pytest in a fresh clone: `apps/fluid-web/dist/render-check.js` is
written by the UI build and `tests/test_brain_binding.py` errors at setup
without it.

```
cd apps/fluid-web && npm run build && npm run typecheck:tests
cd ../.. && MENTIS_QUIET_BROWSER=1 python -m pytest -q tests/test_result_mounted_browser.py
```

What warrants the hardest look, in order:

1. **The host wiring against the handoff**, §1.2 and §1.3 clause by clause —
   it is the one thing no earlier review could execute. Particularly the
   `applyCentre` ordering, the single `pickConversation` route, and that
   nothing a press waits on was put in the render-scoped mount.
2. **`fromWork.ts`**, the seam nobody specified: whether the chooser's wire
   shape becomes the right destination, and whether anything is inferred.
3. **The chooser itself**, which has never been independently reviewed, in the
   rendered page — its words, its bounds, its keyboard and its narrow layout.
4. **The two test-fixture seam changes** in merge 1: whether they are faithful
   to P4's own intent or whether either hides a real behaviour change.
5. **The TEST reconciliation's three resolutions**, above: the Magnet canvas
   as `'none'` in `whereOf`, the ordering of the two `toSource` arms, and the
   chooser's single `decide` over `placeChosen`. The claim that a result's
   viewer source is never `magnet-item` is the load-bearing one.
