# Round 4 verification and handoff

Status: drafted and browser-verified offline prototype, returned for owner approval. Product implementation, deployment, merging into a shared branch and pushing are outside this request and were not performed. No owner approval is claimed.

## Delivered files

- `governance.html`: the complete runnable preview. Open this file directly in Edge with a `file://` URL. It reads no companion file; all styles, scripts and realistic example content are inline.
- `DESIGN-NOTE.md`: per-kind rationale, exact field coverage, source grounding and click routes, including every required composing, warning, preserved-draft and created state.
- `fixtures.json`: the source snapshots embedded in the HTML, for inspection only.
- `verify.mjs`: focused browser verifier, using Node's built-in WebSocket and local Edge debugging protocol. No packages, build or application server.
- `evidence/results.json`: authoritative final test counts, browser version and exact tested commit; generated after the handoff commit.
- `evidence/*.png`: twelve screenshots. The ZIP contains these files and this report; the HTML also returns separately.

Branch: `governance-forms-round4`, in the supplied workspace. The verifier records `git rev-parse HEAD` in its results, so the evidence identifies the exact handoff commit without a self-referencing hash in this committed report. The documentation part was authored on `governance-round4-note` at `bd7625c5fde4e7c21481b77cde2c64ff5e1bbe38`, merged locally, and reconciled with the final UI labels. The final workspace is checked clean after testing. Nothing was pushed.

## Final targeted acceptance run

Command: `node verify.mjs`, after committing all prototype, verifier and documentation changes. Browser: installed Windows Microsoft Edge `157.0.4341.60`, in a hidden isolated headless profile under this workspace. The script closes its own browser before returning. It uses the same installed browser engine the owner tests in; no other engines or full suites were run.

Result: **97 passed, 0 failed, 0 skipped, 0 errors**. Exact commit and each assertion are in `evidence/results.json`. The documentation worker's focused coverage check on its final branch commit was **14 passed, 0 failed, 0 skipped, 0 errors**. Its note was subsequently integrated and its routes reconciled against the HTML.

The browser acceptance checks cover:

- Direct offline `file://` loading with browser networking emulated offline; four explained kind choices; full workspace use at 1440.
- Every kind at 1440, 1024 and 375: desktop editor/preview geometry, a single column on mobile, no horizontal page overflow, and working mobile Write/Live preview jumps.
- Every kind's empty validation, realistic fixture, live preview, readable leave warning, whole-draft retention, creation and fresh return to Records. Desktop Create stays inside the viewport.
- Ten real Workflow activities, structured actor/Discipline/done fields, readable Persona selection, adding and editing, moving up and down without losing fields, neighbours, previous/next navigation, removal cancellation and confirmation, and immediate selected-activity positioning in the preview.
- All Workflow sections, project/decision list rows, participant/Persona defaults, completion/evidence/interruption fields and capability choices. Draft values survive navigation between sections and the leave warning.
- Part-written activities, newly added empty activities and list rows, list paste split by line, row removal, long Discipline procedure/tool-use/verification and capabilities.
- Explicit discard, Escape retention, simulated failure with no write, safe text rendering, supporting-reference explanation, deliberate owner establishment and placement validation.
- Native browser reload warning and cancellation retaining the half-written draft.
- **Zero page HTTP requests, zero page resource requests, zero JavaScript exceptions and zero browser console errors** during the final run. Local CDP traffic is verification control traffic, not a dependency of the HTML.

## Screenshots and click routes

All screenshots were captured through the rendered UI during the final acceptance run. The design note contains the corresponding click routes. Screenshots are viewport captures, rather than cropped or composited images.

| File | Viewport / state |
| --- | --- |
| `01-kind-choice-1440.png` | 1440 × 1000, all four explained kinds |
| `02-decision-1440.png` | 1440 × 1000, guidance, short writing and live record |
| `03-workflow-1440.png` | 1440 × 1000, ten-activity sequence and selected activity beside live record |
| `04-discipline-1440.png` | 1440 × 1000, practice beside tools and live record |
| `05-conversation-instruction-1440.png` | 1440 × 1000, conversation context, writing guidance and live record |
| `06-leave-warning-1440.png` | 1440 × 1000, readable warning over the Workflow draft |
| `07-workflow-1024.png` | 1024 × 1000, sequence editor and preview side by side |
| `08-workflow-375.png` | 375 × 900, stacked sequence workspace and mobile jumps |
| `09-workflow-preview-375.png` | 375 × 900, live record reached with the preview jump |
| `10-created-workflow-1440.png` | 1440 × 1000, simulated created result |
| `11-warning-375.png` | 375 × 900, warning and both explicit actions |
| `12-kind-choice-375.png` | 375 × 900, stacked entry cards |

## Repairs and limits

In-scope repairs during verification: made mobile jumps immediate; fitted the preview and its creation controls to the available viewport; brought the selected activity into view immediately; included the real Workflow's Planner Persona in the fixture picker. The first run also found verifier issues: its Workflow route remained in Overview after exercising empty validation, a paste payload was not escaped for browser evaluation, and a text assertion treated rendered whitespace as source text. These were corrected. The first completed run recorded 62 passed, 12 failed and 1 execution error (the failed total includes that error); its `initial-results.json` is retained. A separate start attempt hit the old debugging port before Edge was ready and ran no browser assertions; bounded startup readiness was added. The intermediate corrected run passed 95 checks. New selected-preview and Persona checks bring the final run to 97.

No unrelated discovered work was pursued. No dispatch, execution boundary, shared API or product source was changed, so their boundary suites are not applicable. This is one bounded offline artifact with a separate documentation part, rather than a product integration or release. No independent product review was started; the owner is reviewing the design preview.

Limitations: creation, identity pickers and standing are simulations. Pickers contain local examples, not a live identity lookup. Drafts and created records last only in the tab's memory; browser reload/close protection uses the native warning, not persistent draft storage. At 375 the preview follows the editor and is reached through the fixed jump links; it is not a second side-by-side pane. Physical-device, screen-reader, exhaustive keyboard, headed-window and other-browser testing were not performed; responsive checks used Edge viewport emulation and real browser input. No live Brain was opened by the browser or tests.

The cited owner posts, round-3 HTML/note, live Kind declarations and real Workflow/Discipline were read through Mentis. `find` searches for the short kinds returned discussion Turns; `governed` then exposed the actual entries and `resolve` read Decision `ent-5717950cf451` and Conversation Instruction `ent-16490bdfadf4` in full. The examples use those actual bodies. The preview does not confer or request standing for that source material.

## Done-when check

The HTML is self-contained and offline; all four named kinds have distinct layouts; the Workflow supports an ordered multi-activity sequence; live preview and creation remain in the composing experience; draft safety is verified; 1024 and 375 geometry is verified; required state routes are written down; and the isolated work and integrated documentation are committed. The targeted run finishes in the returning session on that commit, with its exact counts retained. Approval is the remaining owner decision; the prototype has not been implemented in or deployed to the product.
