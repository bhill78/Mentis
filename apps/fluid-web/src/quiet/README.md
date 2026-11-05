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
key; changing the text, action, or reply target makes a new key. Drafts are
kept in memory by scope while switching within Quiet Chat. Reloading the page
discards unsent drafts.

Quiet Chat uses the shared theme / atmosphere tokens, including background
image and reading-veil hooks. Fluid's layout styles and root load through
`FluidEntry.ts` only on the Fluid path, in their original order. Quiet's own
layout is a reading column plus an optional margin.

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
node tests/quiet_unit.mjs # ten focused cases, also included in run.mjs

# From the repository root, after building; Python needs pytest + Playwright
# and the installed Chromium and WebKit engines.
$env:MENTIS_QUIET_BROWSER = '1'
python -m pytest tests/test_quiet_chat_browser.py -q
```

The browser test uses a disposable fixture Brain and real Mentis HTTP routes.
It covers conversation switching, history paging, long Markdown, topic filing,
a 65-reply chain, nested replies, posting, retained drafts, refusal handling,
operation keys, delayed responses, mobile layout, and both original Fluid
entry paths. It starts no real agent and never opens a live Brain.
