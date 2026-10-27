/* WHAT A POST CARD SAYS: its words, and what it carries.
 *
 * The demo's post shows only its author, number, time and words; what it
 * carries -- renderable blocks and attachments -- is named in one chip,
 * "checklist · chart → This post", and drawn in This post. So the card's
 * Markdown is the post's text with its renderable fences (```kind version=1)
 * taken out; plain Markdown (a pipe table, a list) stays in the words. */

import type { Part, Post } from '../store'
import { parseInfo } from '../../experimental/spec/core'

const REFERENCE = new Set(['turn', 'topic', 'conversation', 'acquired'])
const FENCE = /^ {0,3}(`{3,}|~{3,})\s*([A-Za-z][\w-]*)\b([^\n]*)$/

/** Label for a renderable kind, as the demo's chip names it. */
const KIND: Record<string, string> = { pad: 'note', ref: 'reference', markdown: 'doc' }

export interface Said {
  /** the Markdown the card draws */
  words: string
  /** carried things, by kind, in the order first met */
  kinds: [string, number][]
}

export function textOf(post: Post): string {
  return post.parts
    .filter((p) => p.type === 'text' || REFERENCE.has(p.type))
    .map((p) => p.text ?? '')
    .join('')
}

/** The one text part a card's words come from, when the post has exactly
 *  one: its blocks can then be drawn in the card, keyed by that part. Null
 *  when it has none or several (their blocks stay in This post). */
export function inlinePart(post: Post): number | null {
  const at = post.parts.map((p, i) => (p.type === 'text' ? i : -1)).filter((i) => i >= 0)
  return at.length === 1 ? at[0] : null
}

/** Blocks drawn in the card itself rather than only in This post: a form
 *  is answered where it is asked (P5a), and so is a checklist, editable
 *  table or pad Mentis keeps (P5b) -- one with a name=, a table one with an
 *  editable column too -- and a timer Mentis keeps (one with a name=),
 *  which is started and stopped where it is posted. Any other checklist,
 *  table, pad or timer stays in This post, as before, so old posts read as
 *  they did. */
export const INLINE = new Set(['form'])
const KEPT = new Set(['checklist', 'table', 'pad', 'timer'])

/** Whether a renderable fence line is drawn in the card itself. */
export function inlined(kind: string, info: string): boolean {
  if (INLINE.has(kind)) return true
  if (!KEPT.has(kind)) return false
  const attrs = Object.fromEntries(parseInfo(info).attrs)
  if (!attrs.name) return false
  return kind !== 'table' || (attrs.editable ?? '').split(',').some((x) => x.trim() !== '')
}

/** `inline`: keep the blocks INLINE draws in the words (see `inlinePart`). */
export function said(post: Post, inline = false): Said {
  const lines = textOf(post).replace(/\r\n?/g, '\n').split('\n')
  const kept: string[] = []
  const counts = new Map<string, number>()
  const add = (k: string) => counts.set(k, (counts.get(k) ?? 0) + 1)
  for (let i = 0; i < lines.length; i++) {
    const m = FENCE.exec(lines[i])
    if (m && /\bversion=\d/.test(m[3])) {
      /* a renderable block: skip to its closing fence, of the same run or longer */
      const run = m[1]
      let j = i + 1
      const nested = new RegExp('^ {0,3}' + (run[0] === '`' ? '`' : '~') + '{' + run.length + ',}\\s*$')
      while (j < lines.length && !nested.test(lines[j])) j++
      if (inline && inlined(m[2].toLowerCase(), m[2] + m[3])) {
        kept.push(...lines.slice(i, j + 1))
        i = j
        continue
      }
      add(KIND[m[2].toLowerCase()] ?? m[2].toLowerCase())
      i = j
      continue
    }
    kept.push(lines[i])
  }
  for (const p of post.parts as Part[]) {
    if (p.type === 'text' || REFERENCE.has(p.type)) continue
    /* as the server's `objects.chip_kind` names an attachment */
    const mt = String((p as { media_type?: string }).media_type ?? '').toLowerCase()
    const name = String(p.name ?? '')
    add(mt.startsWith('image/') || /\.(png|jpe?g|gif|webp|svg)$/i.test(name) ? 'image'
      : /^text\/(markdown|plain|x-markdown)$/.test(mt) || /\.(md|markdown|txt)$/i.test(name) ? 'doc' : 'file')
  }
  return { words: kept.join('\n').replace(/\n{3,}/g, '\n\n').trim(), kinds: [...counts.entries()] }
}

/** "checklist · 2 charts · table" */
export function kindsLabel(kinds: [string, number][]): string {
  return kinds.map(([k, n]) => (n > 1 ? `${n} ${k}s` : k)).join(' · ')
}

/** The plain first words of a post, for a quiet line. */
export function excerpt(post: Post, max = 140): string {
  const w = said(post).words.replace(/[#*_`>|[\]()-]+/g, ' ').replace(/\s+/g, ' ').trim()
  return w.length > max ? w.slice(0, max - 1) + '…' : w
}

export const bare = (name: string) => name.replace(/^@/, '')

/** ONE NAMED BLOCK'S FENCE, as its post writes it (P11): what a Needs You
 *  card draws for a block waiting for the owner's input, keyed by the same
 *  text part and names as the post card, so it is the same block with the
 *  same answers. Null when that part holds no top-level block of that name. */
export function blockFence(text: string, name: string): string | null {
  const lines = text.replace(/\r\n?/g, '\n').split('\n')
  for (let i = 0; i < lines.length; i++) {
    const m = FENCE.exec(lines[i])
    if (!m || !/\bversion=\d/.test(m[3])) continue
    const run = m[1]
    let j = i + 1
    const nested = new RegExp('^ {0,3}' + (run[0] === '`' ? '`' : '~') + '{' + run.length + ',}\s*$')
    while (j < lines.length && !nested.test(lines[j])) j++
    const attrs = Object.fromEntries(parseInfo(m[2] + m[3]).attrs)
    if (attrs.name === name) return lines.slice(i, j + 1).join('\n')
    i = j
  }
  return null
}
