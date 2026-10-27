/* WHAT IS ATTACHED TO A POST, HELD FOR ITS CARD, AND WHERE IN ITS WORDS.
 *
 * READ IN ONE BATCH. Every card on screen asks for its post's anchors; the
 * asks of one moment are one `readAnchorsOf` (actions.ts), not one read per
 * card. What is held is read again when the change feed names
 * `anchors:<post>` (store.ts tells that key) or when this page acted on it.
 * Held under `annotated:<post>` in the store's own listeners.
 *
 * A PASSAGE IS A PLACE IN THE STORED TEXT. The card draws `said(post).words`:
 * every text and reference part joined, with the renderable blocks taken out.
 * Classic's alignment (`surfaces/passage.ts`) walks the rendered text against
 * a source string, so it is given the joined parts with each removed block
 * blanked to spaces, character for character: every offset is still the
 * joined text's, and a blanked block is markup to the walk, never a letter it
 * must find. A joined offset is then said as one text part's own. */

import { useCallback, useEffect, useSyncExternalStore } from 'react'
import { placeSelection, rangeOf } from '../../surfaces/passage'
import { readAnchorsOf, anchorsKey, type Passage, type PostAnchor } from '../actions'
import { store, type Id, type Post } from '../store'

/* -- held, in one batch ---------------------------------------------------- */

const held = new Map<Id, PostAnchor[]>()
const wanted = new Set<Id>()
let timer: ReturnType<typeof setTimeout> | null = null
const EMPTY: PostAnchor[] = []
const key = (post: Id) => 'annotated:' + post

async function flush() {
  timer = null
  const ids = [...wanted]
  wanted.clear()
  if (!ids.length) return
  try {
    /* the read takes a list in its address: kept short */
    for (let i = 0; i < ids.length; i += 40) {
      const got = await readAnchorsOf(ids.slice(i, i + 40))
      for (const id of ids.slice(i, i + 40)) {
        held.set(id, got.posts[id] ?? EMPTY)
        store.notify(key(id))
      }
    }
  } catch {
    /* Not read: what was held stays, and the next change that names these
       posts, or the next card that asks, reads them again. */
  }
}

/** Read this post's anchors again, with whatever else is asked now. */
export function reread(post: Id) {
  wanted.add(post)
  timer ??= setTimeout(() => void flush(), 30)
}

/** The anchors on a post, as last read; read when first asked for, and
 *  again whenever the feed names them. */
export function useAnchors(post: Id): PostAnchor[] {
  const sub = useCallback((fn: () => void) => store.subscribe(key(post), fn), [post])
  const got = useSyncExternalStore(sub, () => held.get(post) ?? EMPTY)
  useEffect(() => {
    if (!held.has(post)) reread(post)
    return store.subscribe(anchorsKey(post), () => reread(post))
  }, [post])
  return got
}

/* -- where in its words ---------------------------------------------------- */

const REFERENCE = new Set(['turn', 'topic', 'conversation', 'acquired'])
const FENCE = /^ {0,3}(`{3,}|~{3,})\s*([A-Za-z][\w-]*)\b([^\n]*)$/

export interface Source {
  /** the joined parts, as stored */
  text: string
  /** the same, each renderable block blanked: what the card draws, in place */
  drawn: string
  /** each text part's span in `text`, by its index in `post.parts` */
  spans: { part: number; start: number; end: number }[]
}

/** The post's words as the card draws them, with each text part's place
 *  (text.ts `said`, kept offset for offset). */
export function sourceOf(post: Post): Source {
  let text = ''
  const spans: Source['spans'] = []
  post.parts.forEach((p, i) => {
    if (p.type !== 'text' && !REFERENCE.has(p.type)) return
    const s = p.text ?? ''
    if (p.type === 'text') spans.push({ part: i, start: text.length, end: text.length + s.length })
    text += s
  })
  const lines = text.split('\n')
  const out: string[] = []
  for (let i = 0; i < lines.length; i++) {
    const m = FENCE.exec(lines[i].replace(/\r$/, ''))
    if (m && /\bversion=\d/.test(m[3])) {
      const run = m[1]
      const nested = new RegExp('^ {0,3}' + (run[0] === '`' ? '`' : '~') + '{' + run.length + ',}\\s*$')
      let j = i + 1
      while (j < lines.length && !nested.test(lines[j].replace(/\r$/, ''))) j++
      for (let k = i; k <= Math.min(j, lines.length - 1); k++) out.push(' '.repeat(lines[k].length))
      i = j
      continue
    }
    out.push(lines[i])
  }
  return { text, drawn: out.join('\n'), spans }
}

/** A selection in the card's words as a passage of one text part, or why
 *  it cannot be one. */
export function passageOf(range: Range, body: HTMLElement, src: Source): { ok: Passage } | { refused: string } {
  const got = placeSelection(range, body, src.drawn)
  if ('refused' in got) return got
  const { start, end } = got.ok
  if (src.text.slice(start, end) !== src.drawn.slice(start, end))
    return { refused: 'select within the words, not across what This post shows' }
  const span = src.spans.find((s) => s.start <= start && end <= s.end)
  if (!span) return { refused: 'select within one block of text' }
  return { ok: { part: span.part, start: start - span.start, end: end - span.start, unit: 'utf16', expected_excerpt: src.text.slice(start, end) } }
}

/** Where an anchor's passage is drawn in the card, when the words the card
 *  shows are the version it is on. */
export function drawnRange(a: PostAnchor, body: HTMLElement | null, src: Source): Range | null {
  if (!body || a.deleted || a.selector.type !== 'text-range' || !a.utf16) return null
  if (!a.version_is_current) return null
  const span = src.spans.find((s) => s.part === a.selector.part)
  if (!span) return null
  return rangeOf(body, src.drawn, span.start + a.utf16.start, span.start + a.utf16.end)
}

/* -- what is attached, said briefly ---------------------------------------- */

/** Whether an anchor carries anything now (Classic's `isAnnotation`). */
export const carries = (a: PostAnchor) => a.reactions.length > 0 || a.replies.length > 0 || a.deep_dives.length > 0

/** Whole-post first, then passages in the order they are in the text. */
export function inTextOrder(xs: PostAnchor[]): PostAnchor[] {
  const at = (a: PostAnchor) => (a.selector.type === 'version' ? [-1, -1] : [a.selector.part ?? 0, a.selector.start ?? 0])
  return [...xs].sort((x, y) => {
    const [p, s] = at(x), [q, t] = at(y)
    return p - q || s - t
  })
}

/** "❤️2 💬1 ↗1": what is attached to one anchor, in words for a label. */
export function tallyWords(a: PostAnchor): string {
  const bits = [
    ...a.reactions.map((r) => r.token + (r.count > 1 ? r.count : '')),
    ...(a.replies.length ? [`💬${a.replies.length}`] : []),
    ...(a.deep_dives.length ? [`↗${a.deep_dives.length}`] : []),
  ]
  return bits.join(' ') || 'nothing now'
}

/** The one mark that leads, and how many things are attached in all. */
export function lead(a: PostAnchor): { glyph: string; n: number } {
  const n = a.reactions.reduce((k, r) => k + r.count, 0) + a.replies.length + a.deep_dives.length
  const top = [...a.reactions].sort((x, y) => y.count - x.count)[0]
  return { glyph: top?.token ?? (a.replies.length ? '💬' : a.deep_dives.length ? '↗' : '•'), n }
}
