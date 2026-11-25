# Magnet visual fidelity — plan (owner ent-a24ec84c8176, request opr-7b0ac9bd1816)

The owner's judgement: the panel still reads as the original administrative forms,
not as the approved round-3 design. Another restyle of those forms is explicitly
ruled out. **Rebuild the presentation components; reuse the functionality behind
them unchanged.**

## The design is CSS, not a picture

`magnet-design-round3/render.py` renders the approved PNGs from CSS, importing the
shared `style` from `magnet-design-round2/render.py`. Read both files. They give
the exact type scale, spacing, proportions, colours and states — implement those,
do not re-describe them.

That CSS is ported verbatim into
`apps/fluid-web/src/quiet2/magnets/design.css` as `mgd-` classes scoped to
`.q2-magnet-card` (commit 4ff3e083). **Every part composes from it.** If a rule you
need is missing, say so in your return; do not invent a different value, and do not
edit `design.css` — it is the carrier's file.

Mockup → surface:

| Mockup | Surface |
|---|---|
| `02-compact-current.png` | Perspectives, nothing asked yet |
| `03-sources.png` | Collection → Sources, and the configuration rows |
| `04-browse.png` | Collection → Collected items |
| `05-future-answer.png` | Perspectives, a question with its current understanding |
| `06-future-support.png` | Perspectives → supporting items |
| `07-future-expanded.png` | Perspectives with room (two columns) |
| `08-history.png` | Perspectives → past questions |
| `09-current-help.png` | Perspectives, the one "what can I do today" panel |
| `10-current-discussion.png` | Perspectives, an ordinary discussion reply |

## What the owner asked to be gone

Visible mechanics, explanatory prose, administrative controls and redundant
disclosures. Concretely, on the surfaces as they stand today: the "3 of 20 sources
chosen" sentence, the "Add a source / Add Conversations / Add files" link row, the
`What to collect` checkbox form with its paragraph about folders, "Where this
configuration is saved through", "Save collection configuration" / "Cancel
configuration edits", the duplicated "Collected items · 5 →" / "Sources · 3"
floating links, the Perspectives "About … question — Remove" row, and the repeated
sentences saying discussion does not read collected items. The approved design says
each of those things once, or not at all.

What the design keeps: `AVAILABLE NOW` / `FUTURE CONCEPT` chips exactly where the
mockups put them, and history and provenance reachable behind one link
("Past questions ▾", "Limits and dates ▾", "Explore supporting items ↗").

## Must not change

Server authority and the write gates (`capabilities.ts`, `magnetWriteGate`,
`canWrite`), collection restrictions, stored configuration and its API shapes, the
puck, the badge, direct edge resizing and remembered dimensions (`magnet.css`'s
`q2-magnet-puck`, `q2-magnet-count`, `q2-magnet-resize`, `dimensions`). No backend
change, no new feature, no new mockup.

## Parts

Shared checkout `C:\Work\Mentis-workspace\day-to-day\magnet-refinement-integration`,
branch `magnet-fidelity-20261125`, baseline `4ff3e083` (which is `3b604fd7`, what
TEST serves, plus `design.css`).

Claim only your own files (`claim_resource`, path, exclusive). Commit only your own
paths (`git commit -- <paths>`). Never `git add -A`, stash, reset or clean.

| Part | Owns | Difficulty |
|---|---|---|
| **A — Panel chrome** | `Magnet.tsx`, `magnet.css`, `Host.tsx` | bounded |
| **B — Collection** | `EvidenceViews.tsx`, `SearchView.tsx`, `CollectionConfiguration.tsx`, `collectionRows.ts`, `configuration.css`, `search.css` | open |
| **C — Perspectives** | `InquiryPanel.tsx`, `perspectives.css`, `perspectives.ts` | open |
| **D — Summary and Conversation** | `Summary.tsx`, `summary.css`, `MiniConversation.tsx`, `conversation.css`, `ComposerBar.tsx`, `composer.css` | bounded |

Shared, carrier-owned, do not edit: `design.css`, `places.ts`, `contract.ts`,
`capabilities.ts`, `configuration.ts`, `state.ts`, `read.ts`, `search.ts`,
`conversation.ts`, `indicators.ts`.

### Seams, decided here so nobody waits

1. **A removes the frame's filter row and search toolbar.** `Magnet.tsx` stops
   rendering `q2-magnet-filters` and `q2-magnet-toolbar`, and drops the
   `searchToolbar` prop; `Host.tsx` stops passing it. The approved design puts the
   search and the type pills *inside* Collected items, under its heading
   (`04-browse.png`), and a question search inside Past questions
   (`08-history.png`). **B** therefore renders `SearchToolbar` and the type pills
   inside `EvidenceViews`, and a search at the top of `SearchView`; **C** renders
   its own question search. The underlying places and lens state (`places.ts`,
   `MAGNET_COLLECTION_FILTERS`) are unchanged — only who draws the controls.
2. **A renders the footer composer on the Conversation place only.** No approved
   mockup shows a pinned composer under Collection, Summary or Perspectives; the
   compose box in `02`, `05`, `09`, `10` is in the body of Perspectives. **C**
   renders that in-body compose itself, reusing the existing ask/send path.
3. **The header is the Magnet's name, then `⤢`, `⚙`, `×`.** The header
   `Collect now` button goes; collecting moves into Collection's "Collect manually"
   row (`03-sources.png`), **B**'s. The `⚙` stays although the mockups show two
   icons, because it is the only way to rename or remove a Magnet and losing that
   is a loss of function the owner ruled out — carrier's decision, recorded.
4. **Each view owns its own heading block**: `mgd-eyebrow` with the place's name,
   then `mgd-h2` with what is being shown, with the counterpart link on the same
   row at the far edge. That is the pattern in every round-3 mockup and it replaces
   the floating link rows that are there now.

### First candidate

A + B + C. D lands in the same candidate if it is back in time, otherwise in the
next one. The carrier integrates, inspects the built panel against the mockups in
headless Edge, corrects, and deploys to TEST.

## Checks

Focused UI files only: `node tests/<file>.mjs` from `apps/fluid-web`, plus
`npm run typecheck:tests` when types changed, and `npm run build`. Not `npm test`.
A rebuilt surface breaks the tests that pinned the old markup — update those tests
to assert the approved design's structure and keep every behavioural and authority
assertion they already make. Report each command with passed / failed / skipped /
error counts and keep the output in a log.
