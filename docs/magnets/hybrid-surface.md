# The hybrid Magnet surface: the seam H1 publishes

This records the agreement the hybrid Magnet parts build against, so it is readable in
the repository and not only in a plan. H1 owns everything named here as "H1 only"; a
part that needs a frame change asks H1 rather than editing it.

The design this implements is the owner's approved hybrid interaction
(`magnet-preview.html`, `hybrid.js`, `check_hybrid.py`). The implementation plan is
`adm-8ba17c0776c6` §4–6; this file is its repository-side record, not a second plan.

The surface under development is the **quiet2 puck Magnet**
(`apps/fluid-web/src/quiet2/magnets/*`). `src/fluid/surface/magnet/*` is a parallel
implementation in another shell: a reading reference, never changed by this work.

## The frame is a frame

`Magnet.tsx` holds the puck, the card geometry, the view-state spine and six slots:

| Slot | Who fills it |
|---|---|
| `header` — title, collected count, gear, size, close | H1 |
| `tabs` — the six approved tabs | H1 |
| `searchToolbar` — the search line (the frame renders its own until H4 supplies one) | H4 |
| `view` — **the only scroll container**; one component per place | H3 (Summary, All, Posts, Files), H5 (Perspectives, settings), H2 (Conversation), H4 (search) |
| `footerComposer` — the persistent composer, hidden only in settings | H2 |
| `foot` — collected-at and Collect now | H1 |

Views are supplied through `MagnetProps.views`, keyed by `MagnetPlaceKey`. No part but
H1 edits `Magnet.tsx`, `Host.tsx`, `contract.ts`, `places.ts`, `state.ts`,
`workingState.ts`, `indicators.ts`, `navigation.ts` or `magnets/magnet.css`.

H1 landed `EvidenceViews.tsx`, `Summary.tsx`, `SettingsView.tsx` and `SearchView.tsx` as
**working extractions, not empty stubs**: each is the control the card body already had,
moved to its slot so both the frame and the product keep working while H3, H4 and H5
replace the contents. The slot shape is the contract; the contents are theirs.

## The published types (`contract.ts`)

```
MagnetTab     = 'Summary' | 'All' | 'Posts' | 'Files' | 'Perspectives' | 'Conversation'
MagnetOverlay = null | 'search' | 'settings'
MagnetPlaceKey= MagnetTab | 'search' | 'settings'
MagnetPlace   = { scroll, inspected, inspectScroll, inspectOrigin, provenance, history }
MagnetRoute   = { tab, overlay, searchTarget, lens, query, searchType,
                  searchListScroll, placeKey, placeSnapshot }
SearchEntry   = { key, kind, title, text, open() }
SearchSource  = { entries(), complete?(query, signal), queryDependent?, bound?() }
MagnetContext = { ref, kind, label, text? }     // only ref/kind/label are persisted
```

`MagnetSnapshot`'s persisted working state is exactly: `x`, `y`, `open`, `wide`, `tab`,
`overlay`, `places`, `query`, `searchType`, `searchTarget`, `searchListScroll`, `lens`,
`returnRoute`, `settingsReturn`, `context`, `contextSuppressed`, `agentId`,
`assistanceMode`, `batchSelection`. `previousOpen`/`openedAt` stay in memory.

`pinned`, `expanded`, `scroll`, `scrolls`, `inspection`, `inspectionScroll` and
`inspectionReturn` are **retired**. `open`/`wide` replace the first two; the rest live in
`places[...]`, and the return lives in `returnRoute`.

Two decisions worth stating, because they are not obvious from the type:

- `lens` is the **selected Perspective's reference** (a `string | null`), not an index.
  The approved preview used an index into a local array; the product selects by id.
- `context` persists its reference, kind and label only. Captured collection text never
  enters device storage, which `quiet_magnet_read_unit.ts` and
  `quiet_magnet_hybrid_shell_unit.ts` both assert.

## The spine (`places.ts`)

```
place(s)                      the current MagnetPlace (places[overlay ?? tab])
remember(resource)            write the live scrollTop into the current place
route(s)                      a DEEP snapshot of where the reader is
restore(resource, r)          assign it back AND overwrite places[placeKey]
goTab / openOverlay / closeOverlay / leaveSettings
inspect / closeInspect        one-level inspection with its origin and return
setOpen(resource, open)       the one writer of the open transition baseline
registerViewScroll(...)       the frame tells the spine how to read the live scroll
writePlace / clearInspections / emptyPlaces / emptyPlace
```

**Deep copying is the contract, not an implementation detail.** `route()` copies
`searchTarget` and the place; `restore()` writes copies back; no helper mutates a
`MagnetPlace` in place. That is what makes a return survive an intervening search.

Any part needing the reading position written before it navigates calls
`remember(resource)` — it does not reach into the DOM.

## The open model, which is clicked and not hovered

- `open` is **persisted** working state. Only the puck (`open = !open`), the header `×`
  (`open = false`) and the host's Magnet phase change it.
- **Hover opens nothing and closes nothing.** Keyboard focus reaching the puck opens
  nothing; pressing Enter or Space on it does, because that is the click.
- `wide` is a width only (650 ↔ 900 px, full width ≤ 700 px). When the card is open the
  tabs, search line, composer slot and foot are always present. There is no compact
  content state, and the two phase buttons that switched it are gone.
- Escape, innermost first: search target → settings → search → inspection → close the
  card, returning focus to the puck. H2's send menu and H5's editor stop it earlier.
- The open transition writes `previousOpen = openedAt; openedAt = now` — on a click or a
  restore that opens the card, never on a pointer or on focus. The retained read fires
  on the same transition, and `cancel()` on close. Opening never collects and never
  reads a live source.
- A closed puck shows its **name**, and the collected count only once a retained read has
  returned. Before that the count is genuinely unknown, and `indicators.ts` forbids
  inventing one.
- Two different closes, two different labels: the header `×` is "Close Magnet" and closes
  the card; "Remove this Magnet from the workspace" lives in the Settings overlay. No
  control does both.

## Persisted working state and the v1 migration

The key is **not** bumped: it stays
`mentis.magnet.working.v1:<brainKey>:<boundBrain>:<magnetId>`. The loader reads both
shapes and always writes the hybrid one. Unknown keys were already ignored, so the v1
payload is safe to read; rolling back to the previous release reads the hybrid shape and
loses working state only — nothing durable.

| v1 key | New home | Rule |
|---|---|---|
| `x`, `y` | `x`, `y` | unchanged, still clamped to this canvas |
| `tab` | `tab` | `Overview`→`All`; the others by name; absent or unrecognised → `Summary` |
| `expanded`, `pinned` | `open`, `wide` | `open = expanded \|\| pinned`; `wide = false` |
| `inspection` | `places[tab].inspected` | into the migrated tab's place; `inspectOrigin = null` |
| `inspectionScroll` | `places[tab].inspectScroll` | same place |
| `inspectionReturn` | **`returnRoute`** | kept, not dropped — see below |
| `query` | `query` | unchanged |
| `scroll` | `places[tab].scroll` | only when `scrolls` has no entry for the migrated tab |
| `scrolls` | `places[*].scroll` | `Overview`→`All`; `Compact` dropped (no compact view) |
| `agentId`, `assistanceMode`, `batchSelection` | unchanged | `batchSelection` is load-bearing in `state.ts` |

New fields take their defaults on a migrated payload: `overlay = null`,
`searchType = 'All'`, `searchTarget = null`, `searchListScroll = 0`, `lens = null`,
`settingsReturn = null`, `context = null`, `contextSuppressed = false`, and empty places
for `search` and `settings`.

**One deliberate difference from plan §5-H1-6.** The plan dropped `inspectionReturn`.
The continuation request (`ent-36ab51aa6360`) asks for "full v1 state including
inspection return behavior", so it is **mapped onto `returnRoute`** instead: the v1
return tab becomes a one-place route carrying that tab's migrated scroll. Nothing is
lost either way; this way the reader who reloads mid-inspection still has their return.

## The universal search seam

H4 assembles the index; each view exports a `SearchSource`. A source whose material is
paginated owes a `complete()` that reaches **all** of it, so the index is over collected
information and not over what happened to be loaded.

| Source | Exported from | Owner | `complete()` must reach |
|---|---|---|---|
| `summarySource` | `Summary.tsx` | H3 | — (already complete) |
| `evidenceSource` | `EvidenceViews.tsx` | H3 | — (one `collection` read returns the whole batch) |
| `batchSource` | `BatchHistory.tsx` | H3 | every earlier batch, walking `collection/history` to exhaustion |
| `messageSource` | `conversation.ts` | H2 | every matching post in the Magnet's own Conversation, paging `/fluid/api/search` |
| `perspectiveSource` | `perspectives.ts` | H5 | every Perspective and every earlier wording |
| `settingsSource` | `configuration.ts` | H5 | — (already complete) |

Query-independent sources complete once per opened search overlay and are cached in
`places.search`; the one query-dependent source (`messageSource`) is debounced and cached
per query. While a completion is running, bounded or refused, the results header says so.
It never claims a complete search it did not make.

## The evidence-access boundary

What is enforced today is artifact reach, the activation verifier, Perspective
durability invariants and bind-time checks. What is **not** enforced is "a grounded
answer reads only the configured sources". Therefore grounded and qualified synthesis
stays refused server-side and unavailable in the UI; no part adds a field, setting,
audience assertion or consent choice that enables it, and no part words ordinary
assistance so that it implies scoped evidence access. Ordinary assistance is
distinguished by shape only (`POST /fluid/api/requests` with `from:{magnet}`) and keeps
saying so.

`GET /fluid/api/magnets/<id>/read` in any mode is **not called** by this surface: it
reads the Magnet's sources live, which this surface exists not to do.

## The host seam

`Quiet2.tsx` writes the Magnet's phase in six places; all six now call
`setOpen(resource, …)` from `places.ts`:

- `expandMagnet` → `open: true`; `collapseMagnet` → `open: false`
- the cover's `apply`, for another maximised Magnet → `open: false`
- the resume route, `to.phase === 'details'` → `open: true`, otherwise `false`
- the two item-opening collapses → `open: false`

`navigation.ts`'s `phase: 'details' | 'inspect'` names are unchanged; only their effect
on the snapshot changed. Nothing else in `Quiet2.tsx` is touched by this work.
