/* A PASSAGE, CAPTURED ONCE (passage-capture round).
 *
 * A selection (`Selected`, types.ts) is the record's own identities: the post,
 * the exact version, a range inside one of its text parts. Three things can
 * be done with it, each its own operation:
 *
 *   SAVE FOR LATER   an ANCHOR is made on the passage (`POST /api/anchors`: a
 *                    place that asserts nothing, durable in the Brain), and
 *                    the passage is listed among this reader's saved passages.
 *                    MENTIS HAS NO PER-READER SAVED LIST (no bookmark entry,
 *                    no endpoint): the list is kept in this browser, per
 *                    Brain, and each entry names the anchor, so reopening it
 *                    goes to the exact place. Nothing is reacted, commented,
 *                    or asked of anyone.
 *   ADD TO COMPOSER  the composer the reader last wrote in takes a REFERENCE
 *                    to the post (a `turn` reference part: Fluid's own, by
 *                    dropping the post on it) and the words, quoted, at its
 *                    caret -- both through the composer's own handling, so its
 *                    destination, addressees and draft stay its own. An
 *                    ANCHOR reference cannot be used here: Mentis lets a post
 *                    carry an anchor only when it replies to the anchored post,
 *                    and at most one (`anchors.check_parts`).
 *   SEND TO AGENT    SendToAgent.tsx: an ordinary reply to the post carrying
 *                    the anchor, through Fluid's real composer.
 */
import { CLIENT_HEADERS } from '../../api'
import { drawnRange } from '../../fluid/conversation/annotated'
import { Refused, type PostAnchor } from '../../fluid/actions'
import { fluidFetch } from '../../fluid/http'
import { POST } from '../../fluid/workspace/keep'
import { store, type Id } from '../../fluid/store'
import { highlightFor } from '../../surfaces/passage'
import { BRAIN } from '../live'
import { postOf, sourceOfPost } from '../real'
import { repairText } from '../text'
import type { Selected } from './types'

/** The anchor on a passage, made or found (the same place answers the same anchor). */
export async function anchorOn(sel: Selected): Promise<Id> {
  const me = await store.loadMe()
  const res = await fluidFetch('/api/anchors', {
    method: 'POST',
    headers: { ...CLIENT_HEADERS, 'Content-Type': 'application/json' },
    body: JSON.stringify({
      author: me, version: sel.version, type: 'text-range',
      part: sel.passage.part, start: sel.passage.start, end: sel.passage.end,
      unit: sel.passage.unit ?? 'utf16', expected_excerpt: sel.passage.expected_excerpt,
    }),
  })
  const got = await res.json().catch(() => null) as { anchor?: Id; error?: string } | null
  /* refused: the whole answer is kept, so its structure can be said (refusal.ts) */
  if (!res.ok || !got?.anchor) throw new Refused(res.status, got ?? { error: res.statusText })
  return got.anchor
}

/* -- saved passages ------------------------------------------------------- */

export interface SavedPassage {
  anchor: Id
  post: Id
  conversation: Id
  version: Id
  part: number
  start: number
  end: number
  excerpt: string
  number?: number
  at: number
}

const KEY = () => `q2:saved-passages:${BRAIN?.brain ?? 'page'}`
const heard = new Set<() => void>()
export const onSaved = (fn: () => void) => { heard.add(fn); return () => { heard.delete(fn) } }

export function savedPassages(): SavedPassage[] {
  try { return JSON.parse(localStorage.getItem(KEY()) ?? '[]') as SavedPassage[] } catch { return [] }
}
function put(list: SavedPassage[]) {
  try { localStorage.setItem(KEY(), JSON.stringify(list)) } catch { /* this page only */ }
  heard.forEach((f) => f())
}

/** Saves the passage: its anchor in the Brain, its entry in this browser's list. */
export async function savePassage(sel: Selected): Promise<SavedPassage> {
  const anchor = await anchorOn(sel)
  const entry: SavedPassage = {
    anchor, post: sel.post, conversation: sel.conversation, version: sel.version,
    part: sel.passage.part, start: sel.passage.start, end: sel.passage.end,
    excerpt: sel.excerpt, number: postOf(sel.post)?.number, at: Date.now(),
  }
  put([entry, ...savedPassages().filter((x) => x.anchor !== anchor)])
  return entry
}

export const forgetPassage = (anchor: Id) => put(savedPassages().filter((x) => x.anchor !== anchor))

/** Once the post is drawn, its passage is brought into view and marked a
 *  moment, placed from the saved range (not by matching words). */
let revealing = 0
export function revealPassage(s: SavedPassage, tries = 40, mine = ++revealing): void {
  if (mine !== revealing) return
  const body = document.querySelector<HTMLElement>(`.q2-conv [data-post="${s.post}"] .q2-body`)
    ?? document.querySelector<HTMLElement>(`[data-post="${s.post}"] .q2-body`)
  const src = sourceOfPost(s.post)
  if (!body || !src) { if (tries > 0) window.setTimeout(() => revealPassage(s, tries - 1, mine), 150); return }
  /* the saved range belongs to the version it was saved from: on a later
     version the post is shown, but no words are marked as if they were it */
  const fluid = store.posts.get(s.post)
  const current = !fluid || fluid.version === s.version
  const like = {
    selector: { type: 'text-range', part: s.part, version: s.version }, utf16: { start: s.start, end: s.end },
    deleted: false, version_is_current: current,
  } as unknown as PostAnchor
  const range = current ? drawnRange(like, body, src) : null
  const el = (range?.startContainer.parentElement ?? body) as HTMLElement
  el.scrollIntoView({ block: 'center' })
  if (range) {
    highlightFor('q2-flash', 'q2s', [range])
    window.setTimeout(() => highlightFor('q2-flash', 'q2s', []), 2200)
  }
}

/* -- the composer written in last ----------------------------------------- */

let lastComposer: HTMLElement | null = null
if (typeof document !== 'undefined') {
  document.addEventListener('focusin', (e) => {
    const c = (e.target as Element | null)?.closest?.('.fx-composer') as HTMLElement | null
    /* Send to Agent's own composer is not where passages are gathered */
    if (c && !c.closest('.q2s-send')) lastComposer = c
  }, true)
}

/** The composer a passage would be added to: the one last written in (if
 *  still on the page), else the conversation's own. Null where there is none. */
export function targetComposer(): { el: HTMLElement; label: string } | null {
  const el = lastComposer?.isConnected && lastComposer.offsetParent !== null ? lastComposer
    : document.querySelector<HTMLElement>('.q2-conv .q2-dock .fx-composer')
  if (!el) return null
  const where = el.getAttribute('data-where') ?? ''
  const conv = /^(?:conversation|thread):([^:]+)/.exec(where)?.[1]
  const name = conv ? repairText(store.conversations.get(conv)?.name ?? '') || 'this conversation' : 'the composer'
  const pane = el.closest('.q2-pane')
  const column = pane?.classList.contains('q2-surface') ? ` (column ${(pane.querySelector('[data-surface]') as HTMLElement | null)?.dataset.surface ?? ''})`.replace(' ()', '') : ''
  const thread = where.startsWith('thread:') ? ', in a thread' : ''
  return { el, label: `${name}${thread}${column}` }
}

/** Adds the passage to that composer, through its own handling: the post as a
 *  reference (the composer's drop), the words quoted at its caret (its input). */
export function addToComposer(sel: Selected): Promise<string> {
  const t = targetComposer()
  if (!t) return Promise.reject(new Error('no composer is open on this page'))
  const dt = new DataTransfer()
  dt.setData(POST, JSON.stringify({ post: sel.post }))
  t.el.dispatchEvent(new DragEvent('drop', { bubbles: true, cancelable: true, dataTransfer: dt }))
  const n = postOf(sel.post)?.number
  const quote = `> ${sel.excerpt.replace(/\n+/g, '\n> ')}` + (n != null ? `\n> — #${n}` : '') + '\n\n'
  /* after the drop has opened it; said done only when the words are in */
  return new Promise<string>((resolve, reject) => window.setTimeout(() => {
    const box = t.el.querySelector<HTMLTextAreaElement>('textarea')
    if (!box) { reject(new Error(`the composer in ${t.label} is showing its preview: switch it back to writing, then add the words again`)); return }
    const had = box.value
    box.focus()
    const at = box.value.length
    box.setSelectionRange(at, at)
    const lead = box.value && !box.value.endsWith('\n') ? '\n\n' : ''
    if (!document.execCommand('insertText', false, lead + quote)) {
      /* a browser without insertText: the composer's own onChange, as typing would */
      const set = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value')?.set
      set?.call(box, box.value + lead + quote)
      box.dispatchEvent(new Event('input', { bubbles: true }))
    }
    if (box.value === had) { reject(new Error('the words could not be added to that composer')); return }
    resolve(t.label)
  }, 60))
}

