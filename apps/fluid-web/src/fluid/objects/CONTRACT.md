# Fluid final workspace: shared contract for the parallel workstreams

The owner's final consolidation brief (2026-10-28) is built by five workstreams in parallel.
This file fixes the seams between them. **Code against these interfaces. Don't change a
seam you don't own; if one is wrong, say so in your report.**

Approved references (read what is relevant to you, don't re-design):
- `C:\Work\Mentis-prototypes\fluid-arrange\index.html`: the consolidated recommendation,
  overlaps with code references, object-reference changes, decisions.
- `C:\Work\Mentis-prototypes\fluid-arrange\alt-a|alt-b|alt-c` (+ `NOTES.md`): the prototypes.
- `C:\Work\Mentis-prototypes\fluid-arrange\DROP.md`: drag-to-link + both owner decisions.
- `C:\Work\Mentis-prototypes\fluid-focus\alt-b` (lens model) and `alt-a` (controls).

## Seams (already on branch `fluid-final`)

| Seam | File | Owner | Everyone else |
|---|---|---|---|
| Object actions: `act.open/peek/float/keep/primary/focus(target)`, `ObjectTarget`, `provide()`; `ACTION_LOOK.open = ◨ Open` | `objects/actions.ts` | W1 provides peek, primary, focus; W7 open | call `act.*`; never write a separate action |
| Where Open goes and the row's order: `openRoute(address)` (`post:<id>` → the post read, This post showing its context; `brain:<entry>` → the record's inspector; else → `openObject`, the detail), `ACTION_ORDER` = Open · Peek · Float · Keep · ◎ · ⛶ | `objects/route.ts` (browser-free) | W7 | read, don't re-route |
| The action row: `only`, `compact`, `onAct` (step aside first), `onOpen` (a place's own Open = what a click on the thing does there) | `objects/ObjectActions.tsx` (+ `objects.css`) | W1 (look), W7 (Open, `onOpen`) | draw `<ObjectActions target=… />` on every object; a click on the object or post itself is Open |
| Focus lens API: `lens.enter/setPresentation/stepBack/restore/keepLayout/current/subscribe`, `FocusTarget`, `FocusPresentation`, `PRESENTATIONS`, remembered presentation | `focus/lens.ts` | W1 implements (`provideLens`) | call `lens.*` |
| Split Focus control | `focus/FocusSplit.tsx` | W1 | mount it (ObjectActions already does) |
| Esc | one coordinator, `fluid/escape.ts` (W1 creates): `onEscape(priority, handler)`, the highest-priority handler that returns true wins; Shell.tsx and TreeView.tsx listeners move onto it | W1 | register, don't add window listeners |
| Conversation-wide objects read: `GET /fluid/api/objects?conversation=<id>&before=&limit=` → summaries `{address, exact, kind, title, post, number, reply_to_number, home, preview?}`; `store.loadConversationObjects(id)` | server `mentis/fluid/objects.py` + `web` route; `store.ts` | W2 | read through the store |
| Contents source | `sections/conversationViews.tsx` registers source id **`contents`**; `media` stays registered as an alias for one release | W2 | presets may name `contents` as a feed |
| Preset API | `workspace/place.ts`: `applyLayout(named, scope: 'page' \| 'place')` (never touches defaults); `setDefaults(places, id)`; displaced sections go to the Page's set-aside list (`setAside` on the Page view, presentation only) | W3-server (Kimi) | the Arrange sheet (W3-ui) calls these |
| Reply thread as a surface (fb2): a zone `show: 'thread'`, `options.root` (+ `conversation`, `follow`); `nav.hostThreads(fn)` turns "open replies" into a window where windows can be (wide conversation page), else the sheet; saved `threads.pinned` read as thread windows | `focus/model.ts` (THREAD_SHOW, floatThread, threadWindowRect, setMinimized), `focus/threadWindow.ts`, `conversation/ThreadWindow.tsx`, `nav.ts` | fb2-surfaces | open replies through `nav.openDetail({kind:'replies'})` as before; never draw a thread sheet yourself |
| Window and section menus: `workspace/zoneMenu.tsx` (`lookGroup`, `presentGroup`, `placeItems`, `windowItems`) drawn by `frame/IconMenu.tsx` | `workspace/zoneMenu.tsx` | fb2-surfaces | build a window's ⋯ from these columns |
| Object reference part | `{type: "object", ref: "<root post id>", key: "<object key>", exact: "exact:<version>:<part>:<key>", text: "<what the author sees>", about: {kind, title, home, home_name, number, by}}`. Client renders it in `render/ObjectRefPart.tsx` | W4 | the composer and drop targets create it through W4's helpers |

## Workstreams

- **W1 Focus, Primary, Peek, transitions (Claude).** `focus/lens.ts` implementation: per-Page lens, never saved; a stable Focus area; switching targets replaces the content in place; Docked/Floating/Mixed/Only Focus; Esc history, Restore, Keep this layout; Tidy around Focus and Hide other windows (both reversible). Peek as a first-class surface with Previous/Next over `siblings` and the action row; Peek never changes Primary or Focus. Make primary for an embedded object in one step. The Esc coordinator. Focus Search keeps working in Focus.
- **W2 Rich-content discovery (Codex).** The conversation objects read. Post-card "In this thread" navigator (prototype alt-a): the kind chip unfolds the reply objects in the card and no longer switches Page; ◆ lists the same objects. Reply cards in the sheet get an object strip. The `contents` source with grouping, filters and previews (prototype alt-b). Reading a reply highlights its row instead of narrowing the section. Focus Search reports matches in replies that aren't drawn (prototype alt-c).
- **W3-server Presets and persistence (Kimi K3).** `applyLayout(scope)` with no default side effect (fix `usePreset` → `setDefaults(PLACES)`); set-aside instead of loss; presets get meaningful sources (feeds from the registry, e.g. `contents`, presentation modes, geometry). Server `PRESETS` in `mentis/fluid/arrangements.py` with tests; v1/v2 still read; preset ids unchanged; "Focus layout" as the Focus preset's name.
- **W3-ui Arrange sheet (Antigravity).** The compact Arrange entry stays one entry. Inside: icon groups for This Page (Save, Restore saved, Undo, Reset, Tidy, Sketch), Layouts (mini diagram previews, apply to Page / place, explicit Default for…), Focus presentations (W1's `PRESENTATIONS` + `lens.setPresentation`), Look (the existing AppearancePicker + "objects open over/beside"). Words in tooltips, not long rows. Remove dead "Fit to content" rows (float and column menus); a drag-onto-centre swap records primary history like Make primary.
- **W4 Drag-to-link and object references (Claude).** Server: the `object` part validated where posts are written (`posting.py`, worker reply path), `_REFERENCE_PARTS`, a resolve read, agent context beside `artifacts.referenced_by_request` (that one object only; an artifact if held, otherwise extracted source and description from `exact`; unresolved said in words; no new authority), `worker._turn_line`. Client: render the part (MIUI renderer, provenance header, unavailable state); composer accepts object and post drags as reference chips; drop targets on posts, replies and the conversation header with a confirmation in the DROP.md wording; Include in… for whole posts.

- **W7 One action row everywhere; Open / Peek / Focus distinct (Claude).** The owner's correction: clicking a post or an object card, or ◨ Open, opens the existing detail (`workspace/Detail.tsx`; a post is read in its context); ◱ Peek is the light inspector that changes nothing (`present/viewer.tsx`); ⛶ Focus is the stable Focus area. ⤢ is kept only for enlarging in place or full screen, and says so. The row is drawn on section cards, plates and list lines, blocks in posts and replies, the post's own toolbar, Brain cards and entries, the bar's search hits, Focus Search's reply matches and object float headers.

## Rules for every workstream

- Your own clone `C:\Work\Mentis-wt\ff-<name>`, branch `ff-<name>` off `fluid-final`. Commit there (Codex: the integrator commits for you if `.git` is read-only).
- Targeted tests only: `node apps/fluid-web/tests/<file>_unit.mjs` for what you touch, add unit tests for new logic, pytest by file for server changes. **Never the full suite.** No Mark IV.
- Typecheck before you finish: `cd apps/fluid-web && npx tsc -b`.
- Don't start servers on :8760/:8790; don't touch `C:\Work\Mentis-brains` or MARS config.
- Visual language: restrained, content-first. No heavy borders or outlines. Theme tokens from `src/theme.css`. Write non-ASCII as real UTF-8 and grep your diff for mojibake (`Ã`, `â€`).
- Final message: what you changed (files), how to see it in the app, test results, what's unfinished.
