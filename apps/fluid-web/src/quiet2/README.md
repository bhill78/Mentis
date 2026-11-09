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
| `quiet2.css` | Mark 2's styles; colours only from theme tokens |

Reused, not rebuilt: Fluid's `Composer` (live, against the first named
conversation of the serving Brain), Fluid's `Avatar`, the shared `Prose`
reader, and Mark 1's in-page viewer (`quiet/media/MediaLayer`).

Dev preview: `MENTIS_API=http://127.0.0.1:8790 npm run dev -- --port 5190`,
then `http://127.0.0.1:5190/quiet2`.
