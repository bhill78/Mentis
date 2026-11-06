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
image and reading-veil hooks, and no colour of its own: `quiet.css` holds no
literal colour, so light and dark are whatever `theme.css` says. Dark arrives
two ways — the system preference, and the owner's own choice, which
`index.html` applies as `data-theme` before the first paint — and the browser
test measures the contrast actually painted in both. Fluid's layout styles and
root load through `FluidEntry.ts` only on the Fluid path, in their original
order. Quiet's own layout is a reading column plus an optional margin.

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
node tests/quiet_unit.mjs # thirteen focused cases, also included in run.mjs

# From the repository root, after building; Python needs pytest + Playwright
# and the installed Chromium and WebKit engines.
$env:MENTIS_QUIET_BROWSER = '1'
python -m pytest tests/test_quiet_chat_browser.py -q
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
open a live Brain.
