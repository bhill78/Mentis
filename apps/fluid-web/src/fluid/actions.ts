/* ------------------------------------------------------------------------ *
 * THE TOOLBAR'S ACTS ON A POST, AND WHAT IS ATTACHED TO ONE.
 *
 * Typed calls to Fluid's own commands (`mentis/fluid/commands.py`) -- react,
 * comment, deep dive, edit, delete, withdraw a reaction, file, unfile, move --
 * and to the annotations read (`mentis/fluid/anchored.py`). Fluid never calls
 * production's `/api/*` for these: each command runs the operation Classic's
 * toolbar reaches, so what is recorded, refused and attributed is the same.
 *
 * Nothing here decides who may do what. A refusal is thrown as a `Refused`
 * carrying the server's own words (`error`) and its whole answer (`refusal`);
 * `status` says how it was answered: 422 refused, 400 malformed, 404 not a
 * post or reaction this record holds.
 *
 * Each answer carries `cursor`, the change cursor after the commit: a change
 * feed read from it has already seen this act. The feed names
 * `anchors:<post>` whenever a post's annotations may read differently, so a
 * holder of `readAnchors(post)` reads it again.
 *
 * Only types and CLIENT_HEADERS come from production's `api.ts`, which Fluid
 * already imports, so using this module moves nothing in production's build.
 * ------------------------------------------------------------------------ */
import { CLIENT_HEADERS, type AnchorOnTurn, type AnchorView, type Id, type ReactionRow } from '../api'

/** A refusal or a malformed request, in the server's own words. */
export class Refused extends Error {
  readonly status: number
  readonly refusal: Record<string, unknown>
  constructor(status: number, refusal: Record<string, unknown>) {
    super(typeof refusal.error === 'string' ? refusal.error : `refused (${status})`)
    this.status = status
    this.refusal = refusal
  }
}

async function command<T>(path: string, body: Record<string, unknown>): Promise<T> {
  const res = await fetch('/fluid/api/' + path, {
    method: 'POST',
    headers: { ...CLIENT_HEADERS, 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  const got = await res.json().catch(() => null)
  if (!res.ok || !got || got.error) throw new Refused(res.status, got ?? { error: res.statusText })
  return got as T
}

async function read<T>(path: string): Promise<T> {
  const res = await fetch('/fluid/api/' + path, { headers: { ...CLIENT_HEADERS } })
  const got = await res.json().catch(() => null)
  if (!res.ok || !got || got.error) throw new Refused(res.status, got ?? { error: res.statusText })
  return got as T
}

const post = (id: Id, verb: string) => `posts/${encodeURIComponent(id)}/${verb}`
/** Only the keys that were given: an absent one is not sent as null. */
const given = (o: Record<string, unknown>) =>
  Object.fromEntries(Object.entries(o).filter(([, v]) => v !== undefined))

/* -- where in a post ------------------------------------------------------- */

/** A passage of one text part, as a browser selection measures it: UTF-16
 *  offsets by default, and the words the reader saw, which the server checks
 *  against the record. */
export interface Passage {
  part: number
  start: number
  end: number
  unit?: 'utf16' | 'codepoint'
  expected_excerpt: string
}

/** What a gesture is about: the post's current version whole when neither is
 *  given, or the `version` the reader saw, or a `passage` of it. */
export interface Place {
  passage?: Passage
  version?: Id
}

const place = (p: Place) =>
  given({ version: p.version, passage: p.passage && { unit: 'utf16', ...p.passage } })

/** What every command answers beside its own fields. */
export interface Answered {
  cursor: string
  replayed?: boolean
}

/** An act made on an anchor: the post acted on, and the anchor as it reads. */
export interface Anchored extends Answered {
  on: Id
  anchor: Id
  anchor_view: AnchorView
}

/* -- react, comment, deep dive --------------------------------------------- */

export interface Reacted extends Anchored {
  post: Id
  reaction: Id
  token: string
  /** the earlier reaction of one's own this one changed */
  changes?: Id
}

/** React to a post or a passage of it. Changing one's own reaction names it
 *  in `changes` (see `reactAs`, which finds it). */
export const react = (
  postId: Id,
  a: Place & { by: Id; token: string; changes?: Id; because?: string; op?: string },
) =>
  command<Reacted>(post(postId, 'reactions'), {
    author: a.by,
    token: a.token,
    ...given({ changes: a.changes, because: a.because, op: a.op }),
    ...place(a),
  })

export interface Commented extends Anchored {
  /** the comment: a post of its own, an anchored reply to `on` */
  post: Id
  home: Id
  home_name: string
  number: number
  operation: Record<string, unknown>
}

/** Comment on a post or a passage: an anchored reply, record-only, said in
 *  `conversation` (one the post is in) or else in the post's home. */
export const comment = (
  postId: Id,
  a: Place & { by: Id; text: string; conversation?: Id; op?: string },
) =>
  command<Commented>(post(postId, 'comments'), {
    author: a.by,
    text: a.text,
    ...given({ conversation: a.conversation, op: a.op }),
    ...place(a),
  })

export interface Dived extends Anchored {
  post: Id
  /** the new Conversation */
  conversation: Id
  opening_turn: Id
  parent: Id
  name: string
}

/** Open a deep dive from a post or a passage, for a stated reason. */
export const deepDive = (
  postId: Id,
  a: Place & { by: Id; why: string; name?: string; op?: string },
) =>
  command<Dived>(post(postId, 'deep-dives'), {
    author: a.by,
    why: a.why,
    ...given({ name: a.name, op: a.op }),
    ...place(a),
  })

/* -- edit, delete, withdraw ------------------------------------------------ */

export interface Edited extends Answered {
  post: Id
  edited: Id
  version: Id
  mode: string
  says: string
}

/** Write the post's next version. Only its author may. */
export const editPost = (postId: Id, a: { by: Id; text: string; because?: string }) =>
  command<Edited>(post(postId, 'edit'), { attributed_to: a.by, text: a.text, ...given({ because: a.because }) })

export interface Deleted extends Answered {
  post?: Id
  deleted: Id
  deletion: Id
}

/** Production's Delete: the post's line ends in a deletion record, and
 *  nothing is erased. */
export const deletePost = (postId: Id, a: { by: Id; because?: string }) =>
  command<Deleted & { post: Id }>(post(postId, 'delete'), { attributed_to: a.by, because: a.because ?? '' })

/** A comment is a post: removing one's own is its Delete. */
export const removeComment = deletePost

/** Withdraw one's own reaction: the reactor's own Delete. */
export const withdrawReaction = (reaction: Id, a: { by: Id; because?: string }) =>
  command<Deleted & { reaction: Id; post: Id }>(`reactions/${encodeURIComponent(reaction)}/withdraw`, {
    attributed_to: a.by,
    because: a.because ?? '',
  })

/* -- topics ---------------------------------------------------------------- */

export interface Filed extends Answered {
  post: Id
  turn: Id
  topic: Id
  topics: unknown[]
  filings: unknown[]
}

/** File the post under an existing Topic (`topic`), or open one by `name`
 *  in its Conversation and file it there. */
export const filePost = (postId: Id, a: { by: Id } & ({ topic: Id; name?: undefined } | { name: string; topic?: undefined })) =>
  command<Filed & { filing: Id; created_topic: boolean; already_filed: boolean }>(post(postId, 'topics'), given({ ...a }))

/** End the post's filing under one Topic. */
export const unfilePost = (postId: Id, a: { by: Id; topic: Id; because?: string }) =>
  command<Filed & { unfiled: unknown; was_filed: boolean }>(post(postId, 'unfile'), given({ ...a }))

/** File the post under this Topic only, among its Conversation's Topics. */
export const movePost = (postId: Id, a: { by: Id; topic: Id }) =>
  command<Filed>(post(postId, 'move'), { ...a })

/* -- what is attached to a post -------------------------------------------- */

/** One anchor in a post, as production's turn read draws it, with its whole
 *  reaction history: whose each reaction is, changed and withdrawn ones too. */
export interface PostAnchor extends AnchorOnTurn {
  history: ReactionRow[]
}

export const readAnchors = (postId: Id) =>
  read<{ post: Id; anchors: PostAnchor[]; cursor: string }>(post(postId, 'anchors'))

/** Several posts' anchors in one read; one the record does not hold as a
 *  post is listed in `missing`. */
export const readAnchorsOf = (posts: Id[]) =>
  read<{ posts: Record<Id, PostAnchor[]>; missing: Id[]; cursor: string }>(
    `anchors?posts=${posts.map(encodeURIComponent).join(',')}`,
  )

/** The change feed's key for one post's annotations. */
export const anchorsKey = (postId: Id) => `anchors:${postId}`

/** The anchor already made for this place, if there is one. */
export function anchorAt(anchors: PostAnchor[], version: Id, passage?: Passage): PostAnchor | undefined {
  return anchors.find((a) =>
    passage
      ? a.selector.type === 'text-range' &&
        a.selector.version === version &&
        a.selector.part === passage.part &&
        ((passage.unit ?? 'utf16') === 'utf16'
          ? a.utf16?.start === passage.start && a.utf16?.end === passage.end
          : a.selector.start === passage.start && a.selector.end === passage.end)
      : a.selector.type === 'version' && a.selector.version === version,
  )
}

/** This reader's current reaction on an anchor, if any. */
export const mineOn = (anchor: PostAnchor | undefined, me: Id) =>
  anchor?.history.find((r) => r.current && r.by === me)

/** React as Classic's toolbar does: the same token again is already the
 *  reader's and writes nothing; another token changes their own reaction
 *  there; otherwise it is a first one. `version` is the one the reader saw
 *  (the post's current version, which Classic reads as revision.current). */
export async function reactAs(
  postId: Id,
  a: { by: Id; token: string; version: Id; passage?: Passage; op?: string },
): Promise<{ already: true; reaction: Id } | ({ already: false } & Reacted)> {
  const held = await readAnchors(postId)
  const mine = mineOn(anchorAt(held.anchors, a.version, a.passage), a.by)
  if (mine?.token === a.token) return { already: true, reaction: mine.reaction }
  const got = await react(postId, { ...a, ...(mine ? { changes: mine.reaction } : {}) })
  return { already: false, ...got }
}
