# Track A preview

Branch: `quiet-nav-rails-codex`, based on `2ed8eb9`. Nothing is deployed.
Use **1440 × 1000 CSS pixels**, browser zoom **100%**, light theme and default
background for both tracks. Use the same fixture Brain/manifest for Track B;
fixture IDs are generated, so seeding a second time creates different IDs.

## Build and open

In PowerShell, from this worktree (the existing machine venv has the dev dependencies):

```powershell
Set-Location C:\Work\Mentis-wt\quiet-nav-rails-codex\apps\fluid-web
npm.cmd ci
npm.cmd run build
Set-Location C:\Work\Mentis-wt\quiet-nav-rails-codex
& C:\Work\Mentis\.venv\Scripts\python.exe -m tools.preview_quiet_navigation
$preview = Get-Content scratch\quiet-nav-rails\manifest.json -Raw | ConvertFrom-Json
$preview.long.url
$preview.mixed.url
& C:\Work\Mentis\.venv\Scripts\python.exe -m mentis.web scratch\quiet-nav-rails\brain --port 19871 --workspace C:\Work\Mentis-wt\quiet-nav-rails-codex
```

Leave that terminal open. The server uses this checkout's `apps/fluid-web/dist`.
Open **http://127.0.0.1:19871/quiet**. Click **Quiet carried** in the left
Conversations rail, or open the exact `$preview.mixed.url` printed above.
The long fixture's exact URL is `$preview.long.url`. No Vite process or API
proxy is needed. Stop the server with Ctrl+C. To reopen later, skip seeding
and reuse `scratch/quiet-nav-rails/manifest.json` and its Brain.
The seeder refuses an existing directory; `--root scratch\another-name\brain`
creates another disposable fixture if needed. Never substitute a live Brain.

The installed dependencies in the delivered worktree were copied from
`C:\Work\Mentis\apps\fluid-web\node_modules` after network access prevented
`npm ci`. The lockfile was not changed. When using this worktree as delivered,
you can skip `npm ci`; a normal network-enabled checkout should use it.

## Comparable arrangements of the same Conversation

1. Open **Quiet carried** at the mixed URL. In Settings, select the default
   background, solid surface, light theme; leave header, margins and toolbar
   pinning off. Scroll to the page top. Both fixed rails start open on desktop.
2. **Reading arrangement:** leave **Brief**, **Activity** and **Carried**
   closed (their buttons have `aria-expanded=false`). Read the central posts,
   including “What the run came to,” the checklist/table, the files and the
   annotated passage. Capture `track-a-mixed-reading.png` at 1440 × 1000.
3. **Workspace arrangement:** on that SAME URL, click **Carried** beside the
   Conversation heading. The checklist, table and file boxes appear in the
   left inner margin; the annotation and image appear in the right inner
   margin. Decisions remain below the right margin's content. Scroll back to
   the top and capture `track-a-mixed-workspace.png` at the same viewport.
   The underlying Conversation, topic, posts and composer have not changed.
4. Repeat reading/workspace captures at the long URL, **Quiet layout
   correction**. It has 12 substantial posts and a Reading topic. It carries
   no attachments, so Carried's empty state is expected in this fixture.

## Browser smoke checks still to do

- Click **Conversations** to hide/show only the left rail and **Topics** for
  only the right. Each leaves a labelled edge tab. Escape inside a rail
  closes it and returns focus to its toggle. The first Escape in an open
  filter closes only that filter; the next closes its rail.
- In each rail click **Filter**, enter a partial name, select a result,
  then use **All posts** in Topics and browser Back/Forward. Conversations
  still has **more… / Show fewer** for the existing recency list.
- With Carried open, show/hide either rail; both inner working margins and
  the compact Brief/Activity/Carried controls must remain reachable. Open
  notes.txt or the HTML mockup, close the existing viewer, tick a checklist
  in either location and confirm the other location reflects the same tick.
- Use **Reply to this post**. Type a draft; change Conversations and return
  to check that the draft remains. In this disposable fixture only, choose
  **Post only** before posting; **Ask Mentis** would request a real agent.
- At a narrow viewport the rails start closed; they open over the page and
  collapse from their own labelled toggle or Escape. Inspect focus, scrolling,
  long labels, composer reachability and overlay behavior in the owner's browser.

## Fixture sources and limits

- Long: `tests/test_quiet_layout_correction_browser.py::reading`, named
  **Quiet layout correction**, used unchanged (12 posts).
- Mixed: `tests/test_quiet_r4_margin_browser.py::carried`, named
  **Quiet carried**: checklist, table, mockup.html, notes.txt and an annotated
  passage. The preview adds a Reading topic and one image post using
  `tests/test_quiet_media_browser.py::PNG` and its `hold` helper. The image
  is the existing **1×1 transparent test image**, so it is suitable for
  attachment behavior, not judging photographic presentation.
- The shared base fixtures come from `mentis/web/fixture.py::build`.
  `manifest.json` names the exact generated Conversation and post IDs.

**No browser smoke checks or screenshots were performed by Codex.** The
non-browser checks do not establish painted geometry, visual quality, focus
behavior, drag/drop or pointer interaction. This is a Build to Try candidate.

At the supplied baseline, `/quiet` has static carried boxes; Fluid's floating,
splitting, pinning, Magnets and drag/drop belong to `/fluid`, reachable through
Menu → Open Fluid. Those mechanisms and their layout engine are unchanged.
This variant does not add those missing Fluid mechanisms to Quiet. Full Fluid
margin behavior *inside Quiet* therefore remains an unmet part of the request;
it would require a different baseline or a separate integration change.
