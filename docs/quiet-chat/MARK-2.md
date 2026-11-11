# Quiet Chat Mark 2: starting brief

Status: preparation (2026-11-09). The concept is the owner's to state; this
file only sets the ground so the build can start when it is.

## Starting point

- Mark 1 is archived as `quiet-chat-mark-1` ([MARK-1.md](MARK-1.md)). It stays
  served at `/quiet` until Mark 2 replaces it.
- Mark 2 is built from scratch, next to Mark 1, so both can be compared:
  `apps/fluid-web/src/quiet2/`, served at `/quiet2`, wired in with one more
  branch of the route switch in `apps/fluid-web/src/fluid/main.tsx`.
- Development branch: `quiet-mark-2`, from main.
- Pieces come over from Mark 1 one folder at a time, deliberately
  (`git checkout quiet-chat-mark-1 -- <path>`), never as a wholesale copy.

## Mark 1 pieces to consider taking

To be marked keep / rework / drop with the owner:

| Mark 1 piece | Keep / rework / drop |
| --- | --- |
| Conversation list with recency marks (`rail/`), opened from the logo | |
| Post rendering and parent-post header (`post/`) | |
| Composer: per-scope drafts, settling keys, viewport dock (`composer/`) | |
| Right margin: Topics / Brief / Activity / carried (`margin/`) | |
| Activity panel and decisions (`activity/`) | |
| In-page media viewer (`media/`) | |
| Annotations (`annotations/`) | |
| Participant filter (`filter/`) | |
| Search (`search/`) | |
| Background and reading veil (`surface/`) | |
| Own type scale (`type.css`) | |
| Nav experiment: fixed outer rails (`quiet-chat-mark-1-nav-rails-codex`) | |
| Nav experiment: floating Topics card (`quiet-chat-mark-1-nav-floating-antigravity`) | |

## Carried from Mark 1

- Owner decision: the logo opens the full conversation list.
- Quiet holds no literal colours; light and dark come from `theme.css`.
- Server behaviour is unchanged by the UI: posting goes through `api.ts` /
  `POST /fluid/api/posts`, and permissions and execution stay with the server.
- Quiet's WebKit browser cases hang on launch (known, unfixed) and are skipped
  by default.

## Open questions for the owner

1. What is the Mark 2 concept: what should it feel like, and what is it for
   that Mark 1 was not?
2. Which Mark 1 pieces (table above) come over?
3. Build approach: one builder end to end, or packages in parallel behind a
   frozen seam as in Mark 1 round 2?
4. When Mark 2 is ready, does it take over `/quiet` and Mark 1 leave the tree?
