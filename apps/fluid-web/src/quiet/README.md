# Quiet Chat

Open `/quiet` (or `/quiet/`). `/` and `/fluid` still open Fluid. The existing
Mentis static-file fallback serves all three from the same build; no backend
route or API has changed.

From `apps/fluid-web`, using PowerShell:

```powershell
npm.cmd ci
$env:MENTIS_API = 'http://127.0.0.1:8790' # the Mentis API you intend to use
npm.cmd run dev
```

Then open `http://localhost:5173/quiet`. For a development server, use a fixture
Brain or a copy, as required by the repository's AGENTS.md. `npm.cmd run build`
also produces the bundle a Mentis server serves from this checkout's `dist`.
Building it does not deploy it or change the day-to-day server.

The MENTIS menu switches conversations and offers a small conversation-name
filter. Topics, Brief, and Activity open in the right margin (above the posts
on a phone). All posts clears topic focus. Older / Newer / Latest navigate
the API's existing history batches. Posts are fully readable, with no length
clamp. Open thread reads the full reply chain; its post selector and Previous /
Next links navigate even long threads. A topic shows its filed replies along
with its filed root posts. Reply to this post chooses the exact reply target
and focuses the composer. Back to conversation returns to the selected topic,
if any. The shared address helpers keep conversation, topic, and post links in
the hash, including reload and browser Back / Forward.

The composer uses `api.ts`, the shared `bodyOf` payload builder, and
`POST /fluid/api/posts`. Ask Mentis and Post only are the existing actions;
the server remains responsible for permissions and any execution. A selected
topic is sent explicitly, and replies retain their exact parent. There is no
automatic posting retry. Failed submissions retain their text and operation
key, and the words, posting action and reply target together are what one
submission is (`submissionKey`): an attempt that failed is remembered with the
draft, so typing its words away and back asks again with the key it already
used rather than a fresh one (`settlingKey`). That matters because an attempt
whose answer never arrived may have reached the record; a different message
still gets a new key, and a success clears the draft and its memory with it,
so posting the same words again on purpose is still two posts. A draft
remembers its last failed attempt only. Drafts are kept in memory by scope
while switching within Quiet Chat. Reloading the page discards unsent drafts.

A reader speaks with one voice at a time. `useApi` keeps the last failure's
words until a read succeeds, so Reading… and the failure could stand together
after Try again; a read in flight is the newer fact and is the only thing said,
and the failure returns unchanged if that read fails too.

Quiet Chat uses the shared theme / atmosphere tokens, including background
image and reading-veil hooks, and no colour of its own: none of Quiet's
stylesheets holds a literal colour, so light and dark are whatever `theme.css`
says. Its type, though, is now its own: every size, weight and tracking comes
from a `--qc-type-*` / `--qc-track-*` token declared in `type.css`, so a
package can choose a step without changing Fluid's scale with it. Dark arrives
two ways — the system preference, and the owner's own choice, which
`index.html` applies as `data-theme` before the first paint — and the browser
test measures the contrast actually painted in both. Fluid's layout styles and
root load through `FluidEntry.ts` only on the Fluid path, in their original
order.

## The seam: ten packages, one shell

Round two builds Quiet in ten parts at once, so the seam commit (P0) fixed the
shape they meet at and froze it. After P0 a package changes the BODY of the
modules it owns and nothing else — not `QuietChat.tsx`, not `contract.ts`, not
`layout.css`, not another package's module.

`contract.ts` is the list: every entry module, its owner, and the exports it
must keep. `tests/quiet_seam_unit.mjs` asserts each one still imports and still
exports what it declares, so a renamed component fails there rather than at
integration, with nine branches already written against it.

**Quiet is an app shell above 900px.** `.qc` is the viewport's height;
`#qc-stream` inside the reading column is the one region that scrolls; and the
composer sits in `.qc-dock` BELOW that container, mounted once by the shell
rather than by Flow and Thread. So it is always on screen without being fixed,
the rails are simply their own cells instead of sticky offsets, and no later
package has to edit a file two of them would own. At 900px and below (the
`max-width: 900px` breakpoint is inclusive of 900) the document scrolls as it
always has and the dock sticks to the viewport's lower edge. `Flow.move` resets
whichever of the two actually scrolled, by that same boundary — the stream
element is in the DOM at both widths, so a reset hard-coded to it would succeed
narrow while moving nothing.

**One column template.** `--qc-columns` is declared once, in `layout.css`, and
used by the header row AND the work row. That is what makes the centre column
continue through the header, and it is why no package positions itself: A fills
the first cell and the header's centre cell, B the third, and neither knows
where it sits. Moving conversation lines to the right is a change to that one
declaration. The first cell is empty until A lands.

**Which stylesheet owns what.** `layout.css` owns the page's skeleton — the
grid rows, the column template, which cell is which, and what scrolls — and
says nothing about how anything looks, including for classes named there.
`type.css` owns the scale and the shared element rules. Everything else is a
package's own file, and a package's stylesheet declares only classes its own
sources construct. Where a class is built by one package and laid out by the
shell, it is split by property, not duplicated: `.qc` (skeleton in
`layout.css`, paint in `surface/surface.css`) is the pattern, and `.qc-global`,
`.qc-margin` and `.qc-heading` follow it. `.qc-nav-heading` is in `type.css`
rather than `chrome/chrome.css`, where the plan's table put it, because at P0
both A's popover and B's margin build it, and the ownership rule above is what
decides that; B replaces it with its own `.qc-rail-heading`.

| Stylesheet | Owner |
| --- | --- |
| `layout.css`, `type.css` | P0, frozen |
| `chrome/chrome.css` | A |
| `rail/rail.css` | B |
| `composer/composer.css` | C |
| `activity/activity.css` | D |
| `post/post.css`, `post/prose.css` | E |
| `media/media.css` | F |
| `surface/surface.css` | G |

`prose.css` and `media.css` are empty at P0 and imported anyway: a stylesheet
no module imports is neither checked by `fluid_css_unit.mjs` nor loaded at all.

This first slice reuses the shared prose reader for ordinary Markdown. Rich
interactive fences and HTML remain readable as source. Held attachments open
via their existing URLs; there is no upload UI. Creating conversations or
topics, direct agent/runtime addressing, Pages, magnets, floating windows,
activity consoles, and the other Fluid tools remain outside this slice.

Verification:

```powershell
# From apps/fluid-web
npm.cmd run typecheck:tests
node tests/run.mjs
npm.cmd run build
node tests/quiet_unit.mjs      # fourteen focused cases, also in run.mjs
node tests/quiet_seam_unit.mjs # the seam's own three, also in run.mjs

# From the repository root, after building; Python needs pytest + Playwright
# and the installed Chromium and WebKit engines.
$env:MENTIS_QUIET_BROWSER = '1'
python -m pytest tests/test_quiet_chat_browser.py tests/test_quiet_seam_browser.py -q
```

The browser test uses a disposable fixture Brain and real Mentis HTTP routes.
It covers conversation switching, history paging, long Markdown, topic filing,
a 65-reply chain, nested replies, posting, retained drafts, refusal handling,
operation keys, delayed responses, mobile layout, and both original Fluid
entry paths. A second case asks this build the findings that blocked three of
the four parallel track branches: the contrast actually painted in light,
system dark and chosen dark; a conversation switched while an older page is
still in flight; a thread whose root was deleted; one voice at a time from a
reader; and a resubmission's settling key. Both start no real agent and never
open a live Brain. The contrast measurement itself is in
`tests/quiet_contrast.py`, so G's suite and this one cannot disagree about what
4.5:1 means here.

`tests/test_quiet_seam_browser.py` is what the seam commit is judged by.
`tests/quiet_seam_baseline.json` is the ARIA tree and the visible words of a
fixture conversation, captured on `59749a8` — the commit before the split — and
the split page must equal it; that is "no visual regression" as something a
machine can refuse. Beside it: the header's centre cell and the stream share
their left and right edges to within 1px, and the region that scrolls is the
one each regime names. Those two fail on `59749a8`, which is why they are
evidence. The paging-returns-you-to-the-top case does NOT fail there — a
remounted page is briefly empty and the browser clamps the position of its own
accord — so it is kept as a regression guard and reported as nothing more.
