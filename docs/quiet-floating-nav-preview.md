# Track B preview

Branch: `quiet-nav-floating-antigravity`, based on `2ed8eb9` -- the same base
Track A used. Nothing is deployed. Use **1440 × 1000 CSS pixels**, browser
zoom **100%**, light theme and the default background, as Track A's preview
does, for a comparable capture. This track seeds its own fixture Brain (same
sources as Track A, different generated IDs); open each track's own Brain,
not the other's.

## Build and open

In PowerShell, from this worktree:

```powershell
Set-Location C:\Work\Mentis-workspace\day-to-day\quiet-nav-floating-antigravity\apps\fluid-web
npm.cmd run build
Set-Location C:\Work\Mentis-workspace\day-to-day\quiet-nav-floating-antigravity
& C:\Work\Mentis\.venv\Scripts\python.exe -m tools.preview_quiet_floating_nav
$preview = Get-Content scratch\quiet-floating-nav\manifest.json -Raw | ConvertFrom-Json
$preview.long.url
$preview.mixed.url
& C:\Work\Mentis\.venv\Scripts\python.exe -m mentis.web scratch\quiet-floating-nav\brain --port 19872 --workspace C:\Work\Mentis-workspace\day-to-day\quiet-nav-floating-antigravity
```

Leave that terminal open. The server uses this checkout's `apps/fluid-web/dist`.
Open **http://127.0.0.1:19872/quiet**. Click **Quiet carried** in the
Conversations rail, or open the exact `$preview.mixed.url` printed above.
The long fixture's exact URL is `$preview.long.url`. No Vite process or API
proxy is needed. Stop the server with Ctrl+C. To reopen later, skip seeding
and reuse `scratch/quiet-floating-nav/manifest.json` and its Brain. `node_modules`
is already provisioned in this worktree (junctioned from the main checkout),
so `npm ci` is not needed; a normal network-enabled checkout should still run it.

`node tests/quiet_seam_unit.mjs` passes in this worktree, confirming the
provisioned dependencies actually work before any of the above.

## What is different from Track A, in this same fixture

- **Conversations (left)** is a collapsible rail IN PLACE: it is the same
  grid cell the shell always mounted navigation in, and closing it narrows
  that cell to a labelled edge tab -- the reading column gets the freed width
  back. Track A instead lifts both rails out of the grid entirely into
  fixed, padding-reserved rails; Track B's left rail stays a normal column
  that collapses, rather than an overlay docked outside the margins.
- **Topics (right)** floats: a small **Topics** button beside the existing
  Brief/Activity/Carried controls opens a card that overlays the page near
  the top right, the way a Medium article's table of contents appears over
  the text. It never reserves a grid column, open or closed -- Track A's
  right rail is fixed-but-collapsible and always keeps its own outer gutter.
- **Brief / Activity / Carried** are byte-for-byte the existing working
  margin (`rail/Rail.tsx`), untouched, in the same reserved right-hand grid
  column it always used. Topics is no longer one of its tabs; it is reached
  only through the floating toggle now.

## Comparable arrangements of the same Conversation

1. Open **Quiet carried** at the mixed URL. In Settings, select the default
   background, solid surface, light theme; leave header, margins and toolbar
   pinning off. Scroll to the page top. Conversations starts open on desktop;
   Topics starts closed (it only ever opens on request).
2. **Reading arrangement:** leave Brief/Activity/Carried and Topics closed.
   Read the central posts, including "What the run came to," the
   checklist/table, the files and the annotated passage.
3. **Workspace arrangement:** on the SAME URL, click **Carried** beside the
   heading. The checklist, table and file boxes, the annotation and the image
   appear in the right working margin exactly as they did before this track's
   change; Decisions remains under them. The underlying Conversation, topic,
   posts and composer have not changed.
4. Click **Topics** to open the floating card over the page; click a topic,
   confirm the card closes and the reading column shows that topic; reopen
   Topics and use **All posts**. Click outside the card, or press Escape, to
   dismiss it without choosing anything.
5. Click the **Conversations** toggle to collapse the left rail to its edge
   tab and confirm the reading column widens into the freed space; reopen it.
6. Repeat with the long URL, **Quiet layout correction** (12 posts, no
   attachments -- Carried's empty state is expected there).

## Browser smoke checks still to do

- Collapse/reopen Conversations; open/close Topics by its toggle, an outside
  click, and Escape, each returning focus sensibly.
- In Topics, use its own Find (⌕) to filter, then All posts and browser
  Back/Forward. Conversations keeps the existing **more… / Show fewer**
  recency list and its own Find.
- With Carried open, collapse/reopen Conversations and open/close Topics;
  confirm the working margin (left column stays with ConversationNav, right
  column stays with Brief/Activity/Carried) is unaffected either way. Tick a
  checklist carried from a post and confirm it still reflects in the post.
- Use **Reply to this post**; type a draft; toggle Conversations and Topics
  and confirm the draft survives. In this disposable fixture, choose **Post
  only** before posting -- **Ask Mentis** would request a real agent.
- At a narrow viewport, confirm Conversations starts collapsed behind its
  tab and Topics still floats centred rather than running off the right edge.

## Fixture sources and limits

Same sources Track A used, so the two previews read the same Conversation:

- Long: `tests/test_quiet_layout_correction_browser.py::reading`, named
  **Quiet layout correction** (12 posts).
- Mixed: `tests/test_quiet_r4_margin_browser.py::carried`, named
  **Quiet carried**: checklist, table, mockup.html, notes.txt and an
  annotated passage, plus a Reading topic and one image post
  (`tests/test_quiet_media_browser.py::PNG`, the existing 1×1 transparent
  test image -- suitable for attachment behavior, not photographic judgment).
- `manifest.json` names the exact generated Conversation and post IDs for
  this track's own seeded Brain; they differ from Track A's.

**No browser smoke checks or screenshots were performed by this run.** This
runtime has no `drive_browser` capability, the same limitation Track A
reported -- this is a known limitation of the runtime, not a defect in the
candidate. The non-browser checks above do not establish painted geometry,
visual quality, focus behavior, outside-click dismissal or pointer
interaction; those remain for the owner's hands-on check in a real browser.

At the supplied baseline, `/quiet` has static carried boxes; Fluid's
floating, splitting, pinning, Magnets and drag/drop belong to `/fluid` and
remain unchanged there, reachable through Menu → Open Fluid. This variant
does not add those Fluid mechanisms to Quiet, the same gap Track A reported;
closing it would need a different baseline or a separate integration change,
tracked as discovered work rather than attempted here.
