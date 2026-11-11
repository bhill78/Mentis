# Quiet Chat Mark 1 (archived 2026-11-09)

Mark 1 is the Quiet Chat built in rounds 1–4 (2026-11-05 to 2026-11-08). It is
kept whole under the tag **`quiet-chat-mark-1`** so that Mark 2 can start clean
and still take what it wants from it.

When it was tagged it was also what DAY-TO-DAY served at `/quiet` (release
cbfabaa carries the same Quiet sources as the tagged commit).

## Getting it back

```powershell
# Browse or run Mark 1 exactly as it was, in its own worktree
git fetch origin --tags
git worktree add C:\Work\Mentis-wt\quiet-mark-1 quiet-chat-mark-1

# Copy one piece of it into the current tree
git checkout quiet-chat-mark-1 -- apps/fluid-web/src/quiet/media

# Read a file without checking anything out
git show quiet-chat-mark-1:apps/fluid-web/src/quiet/README.md
```

To run it: build `apps/fluid-web` and open `/quiet` (the Mark 1 README,
`apps/fluid-web/src/quiet/README.md`, has the dev server and test commands).

## What is where

Everything Quiet-only is in `apps/fluid-web/src/quiet/` (about 4,800 lines).
The one place it is wired in is the `/quiet` route switch in
`apps/fluid-web/src/fluid/main.tsx`. It has no server route or API of its own.

| Folder | What it does | Lines |
| --- | --- | --- |
| `QuietChat.tsx`, `layout.css`, `type.css`, `contract.ts` | The shell, its column grid, its own type scale, the package seam | ~600 |
| `chrome/` | Header, the MENTIS menu, toolbar | 327 |
| `rail/` | Conversation list with recency marks | 175 |
| `post/` | Post rendering, parent-post header, prose styles | 402 |
| `composer/` | Composer, drafts kept per scope, settling keys, docked to the viewport | 614 |
| `activity/` | Activity panel and decisions | 341 |
| `margin/` | Right margin: Topics / Brief / Activity / carried items | 455 |
| `media/` | In-page viewer for files and HTML mockups, renderer artifacts | 656 |
| `annotations/` | Annotations on posts | 327 |
| `filter/` | Participant ("who") filter | 217 |
| `search/` | Search | 72 |
| `surface/` | Background, reading veil, viewport measurements | 312 |

`FluidEntry.ts` sits in `quiet/` but is **Fluid's** entry point, not Quiet's
(5 lines). Move it before removing the folder or Fluid will stop loading.

Tests: `tests/test_quiet_*_browser.py` (17 files), `tests/quiet_contrast.py`,
`tests/quiet_seam_baseline.json`, `tests/quiet_activity_run.json`, and the
`quiet*` files in `apps/fluid-web/tests/`.

## Shared pieces that stay regardless

These came out of Quiet work but are shared with Fluid, so they are not part
of Quiet and stay where they are:

- `apps/fluid-web/src/fluid/composer/choose.ts`: the `@` / `#` / `/` pick
  logic, moved out of Fluid's composer so both could use it.
- Server fixes found while running Quiet (artifacts, one coordinator per piece
  of work, resuming the work a post returns to). They fix the server for
  everyone.

Mark 1 also built on Fluid modules Mark 2 can use directly: `api.ts`, `model`,
`address`, `fluid/identity`, `fluid/actions`, `fluid/store`,
`experimental/renderable`, `fluid/runs/consent`, `fluid/search-in`.

## Archived experiments (never merged)

Each is tagged so its branch and worktree can go:

| Tag | What it was |
| --- | --- |
| `quiet-chat-mark-1-nav-rails-codex` | 2026-11-08 Track A: navigation split into fixed outer rails |
| `quiet-chat-mark-1-nav-floating-antigravity` | 2026-11-08 Track B: collapsible Conversations rail, floating Topics card |
| `quiet-chat-mark-1-r1-shell` | 2026-11-05 round 1 track: shell with nav/content/composer slots |
| `quiet-chat-mark-1-r1-nav` | 2026-11-05 round 1 track: conversation navigation |
| `quiet-chat-mark-1-r1-postview` | 2026-11-05 round 1 track: conversation and reply-chain display |
| `quiet-chat-mark-1-r1-composer` | 2026-11-05 round 1 track: composer |

## Owner decisions that carried through Mark 1

- The brand/logo must keep opening the full conversation list (the owner
  rejected a plan that removed it).
