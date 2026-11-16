# Manage Brain in Quiet Chat (Mark 2)

Governance over the Brain's records, inside Quiet Chat. The approved design is
`DESIGN-r2.md` (round 2 mockups, `apps/fluid-web/mockups/manage-brain-r2/` on branch
`manage-brain-mockups`). Fluid's Governance page (`/fluid?gov=1`) is unchanged and still there.

## Navigation

- **The rail has one Brain icon**, above its `+`. The rail's dashes stay conversations; the rail
  never changes mode. On a phone the icon is in the top line.
- **The icon opens the Brain browser**, a card (a bottom sheet on a phone): search, the views
  **Knowledge · Governing · Needs you · All**, a Kind and a standing filter, and a page of rows with
  "Show more". The card keeps its filter, words, rows and scroll while it is closed.
- **A row opens the record in the main reading area.** Back returns to the browser as it was left;
  "Back to the conversation" returns to the conversation at the place it was being read.
- **A post's record mark opens the record beside the conversation** where a working surface is
  free, else in the reading area with Back to that post.
- **A record's links**: another record opens in the same place (Back returns); a post is shown in
  its conversation, with one step "Back to the record".
- `…/quiet2?record=<entry id>` opens a record directly (what "Copy link" copies).

## The record

Kind, the words, one line that says whether it is in effect (the Ladder's status as a pill beside
plain words), one line of who and when. Everything else is folded: why it stands (basis,
provenance, adoption requests and declines), details (other fields), how it has gone (outcomes
with their verdict by name, where each was observed, bounded recent deliveries), challenges,
related (lineage, what replaced it, what cites it), where it applies, history.

Acts are the existing ones, through the existing routes:

| Act | Where | Route / component |
|---|---|---|
| Adopt, Decline, Edit wording first | the owner's decision card | `BrainDecision` → `buildAdoptPayload`, `/api/entries/<id>/adopt|decline` |
| Revise, Establish, Replace, Place, End placement, Delete, Preview persona | ⋯ menu | `useRecordActs` (`surfaces/governance/R2Record.tsx`), offered when the server's `governance_actions` allows |
| Challenge, Withdraw, Set aside, Request adoption | ⋯ menu and the Challenges section | `/dispute`, `/withdraw-challenge`, `/set-aside`, `/request-adoption` |
| New record (Instruction, Persona, Rule/decision/lesson, Discipline, Workflow) | the browser's ⋯ | `R2Create` |
| Import an archive | the browser's ⋯ | `ImportArchiveTab` |
| See what an agent will receive | the browser's ⋯ | `FluidPreviewSheet` |

The server decides every act whatever the page offers. Nothing here adds a rule, a score or an
approval step.

## Reads

- `GET /api/ladder/browse?view=knowledge|governing|needs-you|all&q=&kind=&status=&past=1&challenged=1&limit=&offset=`
  — one list, one status vocabulary (`adoption_status`), newest first, paged; `total`, `past`
  (replaced or deleted, left out unless asked for) and `kinds` (from the record) are said with it.
  `needs-you` is `home.asking_owner` resolved to records: the bell's own rule.
- `GET /api/ladder/items/<id>` — now bounded: the newest `delivered_limit` (25) deliveries with
  `delivered_total`; `cited_by` with each citing record's words; `superseded_by`; outcomes and
  basis posts with `where` (conversation, number); `usage.outcomes_after_delivery.inconclusive`.
- Under them, `store.operational(about=, detail_names=)` finds the acts about one entry in SQLite
  instead of decoding the whole act history.

## Record summaries

A list row shows one sentence saying what the record means or requires
(`mentis/record_summaries.py`). It is **presentation metadata beside the record**
(`<brain>/presentation/record-summaries.json`): not an Entry, read by nothing that forms context,
retrieves, delivers or governs, and it changes no standing. The record's own wording is what its
view shows and what agents are given.

| Source | Meaning |
|---|---|
| `written` | the owner wrote or corrected it (record ⋯ → "Correct the summary…"); never overwritten by a generated one |
| `generated` | a model wrote it once, in a batch somebody ran; it says who ran it, what wrote it and when; shown as "generated, not reviewed" |
| `derived` | nothing is kept: the record's own first sentence, shortened; computed, never stored |

A summary is bound to the words it was written for (a hash); one that does not match is not shown.

Making them in bulk is a bounded batch, never a service:

    python tools/brain_summaries.py export --server <url> --out missing.json
    python tools/brain_summaries.py import --server <url> --file summaries.json --model "<what wrote them>"

The tool acts on whichever Brain the named server serves. Each environment's Brain has its own
summaries; a Brain with none shows derived ones.
