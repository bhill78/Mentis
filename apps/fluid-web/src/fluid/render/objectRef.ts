/* AN OBJECT REFERENCED FROM ANOTHER POST (Fluid final W4; fluid-arrange
 * DROP.md and both owner decisions of 2026-10-28).
 *
 * An object inside a post -- a chart, a table, a form, an attachment -- is
 * referenced by its originating post and stable key, never copied and never
 * a record of its own. A post carries the reference as one content part
 * (objects/CONTRACT.md, "Object reference part"):
 *
 *   {type: "object", ref: <root post id>, key: <object key>,
 *    exact: "exact:<version>:<part>:<key>", text: <what the author sees>,
 *    about: {kind, title, home, home_name, number, by}}
 *
 * `ref` + `key` is its identity (the live address), `exact` pins what the
 * author selected, `about` is a caption so it still reads when the original
 * is gone. The server checks each one where the post is written
 * (mentis/conversation/objectref.py) and refuses in words.
 *
 * PURE: what the part is, what a drop on a post or a conversation means, and
 * the words each says. The drawing is ObjectRefPart.tsx; the drops are
 * conversation/linkDrop.tsx; the composer's chips are composer/draft.ts. */

import type { Id, Part, Post, PostObjectEntry } from '../store'
import { kindOf } from '../../experimental/objectkinds'

/** The part's type. */
export const OBJECT_PART = 'object'

export interface ObjectAbout {
  kind?: string | null
  title?: string | null
  home?: Id | null
  home_name?: string | null
  number?: number | null
  by?: string | null
}

export interface ObjectRefPart {
  type: 'object'
  ref: Id
  key: string
  exact: string
  text: string
  about: ObjectAbout
}

/** A whole post named by a reference (the existing `turn` part). */
export interface TurnRefPart { type: 'turn'; ref: Id; text: string }

export const isObjectPart = (p: Part | Record<string, unknown> | null | undefined): p is Part & ObjectRefPart =>
  !!p && p.type === OBJECT_PART && typeof p.ref === 'string' && typeof (p as { key?: unknown }).key === 'string'

/** The live address a part names: `live:<root>:<key>`. */
export const liveOf = (p: { ref: Id; key: string }) => `live:${p.ref}:${p.key}`

/** The server's bounds (objectref.py): what the author sees, each word of `about`. */
const TEXT_MAX = 300
const WORD_MAX = 200
const clip = (s: string | null | undefined, n: number) => (s == null ? s ?? null : s.length > n ? s.slice(0, n - 1) + '…' : s)

/** What an object is called in a reference: its title, else what it is. */
export function objectTitle(o: PostObjectEntry): string {
  if (o.title && o.title !== o.type) return o.title
  if (o.kind === 'post-text') return 'Post text'
  if (o.kind === 'media') return o.type === 'returned' ? 'Returned file' : 'Attachment'
  return o.type.charAt(0).toUpperCase() + o.type.slice(1)
}

/** What kind of thing it is, in one word ("chart", "table", "image"...). */
export const objectKind = (o: PostObjectEntry): string => kindOf(o).word || o.type

/** The reference part for object `o`, as its post `from` is read now (the
 *  post gives where it lives and who wrote it). */
export function objectRefPart(o: PostObjectEntry, from?: Pick<Post, 'home' | 'home_name' | 'number' | 'author_name'> | null): ObjectRefPart {
  const title = clip(objectTitle(o), WORD_MAX)!
  return {
    type: 'object', ref: o.post, key: o.key, exact: o.address.exact,
    text: clip(title, TEXT_MAX)!,
    about: {
      kind: clip(objectKind(o), WORD_MAX), title,
      home: from?.home ?? null, home_name: clip(from?.home_name ?? null, WORD_MAX),
      number: from?.number ?? null, by: clip(from?.author_name ?? null, WORD_MAX),
    },
  }
}

/** The reference part for a whole post (`turn`): "#4", or its home and number when elsewhere. */
export function turnRefPart(post: Pick<Post, 'id' | 'number' | 'home_name'>, here?: Id | null, home?: Id | null): TurnRefPart {
  const num = post.number != null ? `#${post.number}` : 'a post'
  return { type: 'turn', ref: post.id, text: home && here && home !== here && post.home_name ? `${post.home_name} ${num}` : num }
}

/* -- the words ------------------------------------------------------------- */

/** Each kind's mark, as the post card's chips draw them (conversation/Carries.tsx). */
const MARK: Record<string, string> = {
  table: '▦', chart: '▥', checklist: '☑', diagram: '◇', timeline: '┄', image: '▣', doc: '¶', note: '✎',
  reference: '↗', file: '▤', video: '▶', audio: '♪', panel: '▣', text: '¶', link: '⛓', form: '☰', post: '↗',
}
export const markOf = (kind: string | null | undefined) => MARK[kind ?? ''] ?? '▤'

const bare = (name: string | null | undefined) => (name ?? '').replace(/^@/, '')
const cap = (s: string) => s.charAt(0).toUpperCase() + s.slice(1)

/** Where the original is, in words: "Dungeons and Dragons #4". */
export function whereOf(a: ObjectAbout): string {
  const num = a.number != null ? `#${a.number}` : null
  return [a.home_name, num].filter(Boolean).join(' ') || 'its post'
}

/** The provenance header: "▥ Adjusted XP · from Dungeons and Dragons #4 · claude";
 *  when the original is gone, "▥ Chart · Adjusted XP — from Dungeons and
 *  Dragons #4 · claude · no longer available". Never a substitute. */
export function provenance(p: Pick<ObjectRefPart, 'text' | 'about'>, available = true): string {
  const a = p.about ?? {}
  const title = a.title || p.text
  const by = a.by ? ` · ${bare(a.by)}` : ''
  if (available) return `${markOf(a.kind)} ${title} · from ${whereOf(a)}${by}`
  return `${markOf(a.kind)} ${a.kind ? `${cap(a.kind)} · ` : ''}${title} — from ${whereOf(a)}${by} · no longer available`
}

/** Where the original remains: "Dungeons and Dragons, #4". */
const remains = (a: ObjectAbout) => [a.home_name, a.number != null ? `#${a.number}` : null].filter(Boolean).join(', ') || 'its own post'

/** What is being dropped, as the confirmation names it. */
export type Dragged =
  | { kind: 'object'; part: ObjectRefPart }
  | { kind: 'post'; post: Pick<Post, 'id' | 'number' | 'home' | 'home_name'> }

/** Where it would land. */
export type LinkTarget =
  | {
    kind: 'post'; post: Pick<Post, 'id' | 'number' | 'home' | 'home_name' | 'reply_to' | 'author' | 'author_name'>
    /** the conversation it is shown in, where the reply is written (its home when unset) */
    here?: Id | null
  }
  | { kind: 'conversation'; conversation: Id; name: string }

const num = (n: number | null | undefined) => (n != null ? `#${n}` : 'the post')

/** The caption chip while dragging over a target: "Link to #5 · reply",
 *  "Include in Session 8 planning". */
export function captionOf(t: LinkTarget): string {
  if (t.kind === 'conversation') return `Include in ${t.name}`
  return `Link to ${num(t.post.number)} · ${t.post.reply_to ? 'reply' : 'post'}`
}

/** A sentence in parts: plain words and the names said in bold. */
export type Words = (string | { b: string })[]

/** Why a drop is refused before anything is asked, in words, or null. */
export function refusalOf(d: Dragged, t: LinkTarget): string | null {
  const home = d.kind === 'object' ? d.part.about.home : d.post.home
  const own = d.kind === 'object' ? d.part.ref : d.post.id
  if (t.kind === 'post' && t.post.id === own) return d.kind === 'object' ? 'Not linked: that is the post it is in.' : 'Not linked: that is the post itself.'
  if (t.kind === 'conversation' && d.kind === 'post' && home && home === t.conversation) return 'Not included: that is the conversation it was written in.'
  return null
}

/** The confirmation's sentence (DROP.md, the owner's wording). */
export function confirmWords(d: Dragged, t: LinkTarget, hereName?: string | null): Words {
  if (d.kind === 'post') {
    const what = `${num(d.post.number)}${d.post.home_name ? ` from ${d.post.home_name}` : ''}`
    if (t.kind === 'conversation')
      return ['Include ', { b: what }, ' in ', { b: t.name }, '? It stays in ', { b: d.post.home_name ?? 'its own conversation' }, `; ${t.name} shows it too. Nothing is moved or copied.`]
    return ['Reply to ', { b: `${num(t.post.number)}${hereName ? ` in ${hereName}` : ''}` }, ' with a reference to ', { b: what }, '? ',
      `The post itself stays in ${d.post.home_name ?? 'its own conversation'} — nothing is copied.`]
  }
  const a = d.part.about, title = a.title || d.part.text, kind = a.kind ?? 'object'
  if (t.kind === 'conversation') {
    const home = a.home && a.home === t.conversation
    return ['Bring ', { b: title }, ` (${kind}) into `, { b: t.name }, '? ',
      ...(home ? [] : [`Include its post adds ${remains(a)} here. `]),
      `Post a reference here adds a post that shows this ${kind}. The ${kind} itself stays in `, { b: remains(a) }, ' — nothing is copied.']
  }
  return ['Link ', { b: title }, ` (${kind}) to `, { b: `${num(t.post.number)}${hereName ? ` in ${hereName}` : ''}` },
    `? A reply is added to ${num(t.post.number)} that shows this ${kind}. The ${kind} itself stays in `, { b: remains(a) }, ' — nothing is copied.']
}

/** The quiet line when the reply asks an agent (the owner's second
 *  decision): "Claude will be given this chart (Adjusted XP, as of #4's
 *  current version) — nothing else from #4." */
export function agentLine(agent: string, p: Pick<ObjectRefPart, 'text' | 'about'>): string {
  const a = p.about ?? {}, n = num(a.number), kind = a.kind ?? 'object'
  return `${cap(bare(agent))} will be given this ${kind} (${a.title || p.text}, as of ${n}'s current version) — nothing else from ${n}.`
}

/* -- what is sent ---------------------------------------------------------- */

/** The body of the reply a confirmed drop on a post writes: a reply to it
 *  (`replies_to`) carrying the reference, through the ordinary posting door.
 *  Record only, addressed to whoever wrote the post, unless `ask` asks that
 *  author to work on it. */
export function linkReplyBody(ref: ObjectRefPart | TurnRefPart, target: { id: Id; author: Id; home: Id | null }, me: Id, conversation: Id, op: string, ask = false) {
  return {
    author: me, conversation, replies_to: target.id, op,
    parts: [{ ...ref }], text: ref.text,
    addressed_to: target.author !== me ? [target.author] : [],
    topics: [], because: null,
    action: ask ? 'ask-participant' : 'record-only',
    dispatch: ask ? [{ participant: target.author, runtime: null, model: null, effort: null, persona: null, new_instance: false, coordinate: false }] : [],
  }
}

/** The body of a reference post in a conversation ("Post a reference here"). */
export function referencePostBody(ref: ObjectRefPart, me: Id, conversation: Id, op: string) {
  return {
    author: me, conversation, op, parts: [{ ...ref }], text: ref.text,
    addressed_to: [], topics: [], because: null, action: 'record-only', dispatch: [],
  }
}
