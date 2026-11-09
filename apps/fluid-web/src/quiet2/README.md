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
| `text.ts` | Repairs UTF-8 read as Windows-1252 ("â€”") in what is drawn; the record is untouched |
| `quiet2.css` | Mark 2's styles; colours only from theme tokens |

Reused, not rebuilt: Fluid's `BrandMenu` (the logo's Brain menu, click-only), Fluid's `editPost`,
`ConversationInstructions`, the conversation and thread read routes, Fluid's `Composer` (its `replyTo`/`thread` targeting) (live, against the first named
conversation of the serving Brain), Fluid's `Avatar`, the shared `Prose`
reader, and Mark 1's in-page viewer (`quiet/media/MediaLayer`).

URL parameters for review: `arr=one|two|three`, `side=left|right`, `receded=1`,
`measure=current|wide`, `content=sample|long|real`, `c=<conversation id>`.

Dev preview: `MENTIS_API=http://127.0.0.1:8790 npm run dev -- --port 5190`,
then `http://127.0.0.1:5190/quiet2`.
