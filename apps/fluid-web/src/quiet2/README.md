# Quiet Chat Mark 2: design round 1

Open `/quiet2`. `/quiet` is still Mark 1 and `/` is still Fluid. See
`docs/quiet-chat/MARK-2.md` for where Mark 2 stands.

Round 1 is a design iteration: an editorial conversation drawn from a sample
(`sample.ts`), not from a Brain.

| File | What it is |
| --- | --- |
| `Quiet2.tsx` | The page: top line, the reading column, arrangements, the docked composer |
| `Post.tsx` | One post: topics, title, byline, body blocks, margin marks, attachments, toolbar |
| `Markers.tsx` | Stepped markers (conversations left, topics right) and their round-1 thresholds |
| `sample.ts` | The sample conversation; participant ids are the dev Brain's |
| `real.ts` | The one post store every view reads; real posts and threads from the serving Brain; the long-form reel |
| `Thread.tsx` | Replies as presentations of the same posts: the three-dot fold, the reply tree, the thread view |
| `Dock.tsx` | Each place's own composer (Fluid's), its destination, the one-line foot (who is working · Shift+Enter) |
| `Surface.tsx` | A working surface: a conversation, thread, post, picture/file or table/code block, named by what it holds, with Back |
| `presence.ts` | Who is working on which post, from Mentis's activity (`/api/activity`); the sample's work is simulated |
| `links.ts` | Which parent is emphasised: the reply pointed at, the post a composer is answering |
| `thread.css` | The shallow reply tree: two indent levels, curved connectors to the real parent |
| `Look.tsx` | Settings' palette: a few backgrounds, More… (Fluid's LookBody), Add from file (Fluid's picture maker), theme, reading surface |
| `viewer/` | The content viewer: `Viewer.tsx` (the frame: identity, source, maximise/restore, move, close), `viewers.ts` (open viewers, held once, with their renderer state), `types.ts` (the contract), `PdfView.tsx` + `pdfDoc.ts` (PDF via pdf.js), `GalleryView.tsx` (picture collections), `Harness.tsx` (a renderer test stage, dev only: `?harness=pdf|gallery`) |
| `GlobalDock.tsx` | The global Mentis dock: Needs you, Working, Recent, Capacity, Search, Settings (existing Fluid reads) |
| `Discover.tsx` | Every conversation, from the rail's chevron |
| `live.ts` | Which Brain the page reads, and whether it may write |
| `text.ts` | Repairs UTF-8 read as Windows-1252 ("â€”") in what is drawn; the record is untouched |
| `quiet2.css` | Mark 2's styles; colours only from theme tokens |

Reused, not rebuilt: Fluid's `BrandMenu` (the logo's Brain menu, click-only), Fluid's `editPost`,
`ConversationInstructions`, the conversation and thread read routes, Fluid's `Composer` (its `replyTo`/`thread` targeting) (live, against the first named
conversation of the serving Brain), Fluid's `Avatar`, the shared `Prose`
reader, and Mark 1's in-page viewer (`quiet/media/MediaLayer`).

URL parameters for review: `at=<post number>` (real conversation read around one post), `arr=one|two|three`, `side=left|right`, `receded=1`,
`measure=current|wide`, `content=sample|long|real`, `c=<conversation id>`.

Dev preview: `MENTIS_API=http://127.0.0.1:8790 npm run dev -- --port 5190`,
then `http://127.0.0.1:5190/quiet2`.

## The one development server (two Brains)

`C:\Work\Mentis-workspace\quiet2-preview\vite.cmd` starts Vite on :5190 with
`Q2_BRAINS=1` (`quiet-brains.mjs`). The page's top line says which Brain it
reads and whether it may write; click it to switch (the page reloads):

- **Development Brain** (:8790, the disposable copy): writes on.
- **DAY-TO-DAY** (:8760): strictly read-only. The proxy refuses every
  non-GET, and `GET /api/capacity` (which records a reading), before anything
  is forwarded.

Each page sends its Brain on every fetch (`X-Q2-Brain`, `live.ts`); `<img>`
requests use the cookie. Requests naming no Brain go to the development Brain.
