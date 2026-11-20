/* A LINK OR AN ID SOMEBODY ALREADY HAS (the finder's advanced option).
 *
 * Choosing by words is the ordinary way to point a record at something. This
 * is for the reader who already holds an exact reference: a link copied from
 * a record or a post, or an id an agent wrote down. What is pasted is read
 * here, asked of the server BY EXACT ID (`GET /api/ladder/resolve`: no
 * search, no guessing), and said back in words -- what it is, what it says,
 * who recorded it and where -- before it can be added. What is added is the
 * same reference a search would have chosen.
 *
 * Nothing here draws anything, so the rules are checkable without a browser
 * (`tests/brain_author_unit.ts`). */
import { qs, read } from '../../../api'
import { statusWord } from '../data'
import type { Ref } from './model'

/** An exact reference: a record or post, a held file, or bytes of one. */
export const PASTED = /^(ent-[0-9a-f]{12}|adm-[0-9a-f]{12}(@[0-9a-f]{12,64}\[\d+:\d+\])?)$/
const ENTRY = /^ent-[0-9a-f]{12}$/
const ANY = /(?:ent-[0-9a-f]{12}|adm-[0-9a-f]{12}(?:@[0-9a-f]{12,64}\[\d+:\d+\])?)/g

/** What the pasted text asks for: one exact reference, or a post by its
 *  conversation and number (how a post's own link names it). */
export type Asked = { ref: string } | { conversation: string; number: number }

/** Read what was pasted. An id is taken as it is. A link is read by what
 *  Quiet Chat's own links carry (`record`, or `c` with `at`); any other link
 *  is taken only where it names exactly one thing. Words are not a
 *  reference: null. */
export function parsePasted(text: string): Asked | null {
  const t = text.trim()
  if (!t) return null
  if (PASTED.test(t)) return { ref: t }
  if (!/^https?:\/\//i.test(t)) return null
  let url: URL
  try { url = new URL(t) } catch { return null }
  const q = url.searchParams
  const record = q.get('record')
  if (record && PASTED.test(record)) return { ref: record }
  const c = q.get('c'), at = q.get('at')
  if (c && ENTRY.test(c) && at) {
    if (PASTED.test(at)) return { ref: at }
    if (/^\d{1,9}$/.test(at) && Number(at) > 0) return { conversation: c, number: Number(at) }
    return null
  }
  const hash = decodeURIComponent(url.hash.replace(/^#/, ''))
  if (PASTED.test(hash)) return { ref: hash }
  let whole = t
  try { whole = decodeURIComponent(t) } catch { /* said as it is */ }
  const named = [...new Set(whole.match(ANY) ?? [])]
  return named.length === 1 ? { ref: named[0] } : null
}

/** The server's answer (`mentis/web/ladder.py`, `_resolve`). */
export interface Resolved {
  found: boolean
  ref: string | null
  why?: string | null
  usable?: boolean
  kind?: string
  label?: string
  by?: string | null
  status?: string | null
  passage?: boolean
  where?: { conversation: string; conversation_name: string | null; turn: string | null; number: number | null } | null
  file?: { name: string | null; size: number | null; media_type: string | null; state: string | null; origin: string | null; collection: string | null } | null
}

const cap = (s: string) => s.charAt(0).toUpperCase() + s.slice(1).replace(/[-_]/g, ' ')
const clip = (s: string, n = 220) => { const t = s.replace(/\s+/g, ' ').trim(); return t.length > n ? t.slice(0, n - 1).trimEnd() + '…' : t }
const bytes = (n: number) => (n < 1024 ? `${n} bytes` : n < 1024 * 1024 ? `${Math.round(n / 1024)} KB` : `${(n / 1024 / 1024).toFixed(1).replace(/\.0$/, '')} MB`)

/** What a resolved reference is called. */
export const kindOf = (r: Resolved) => (r.kind === 'contribution' ? 'Post' : r.kind === 'file' ? 'File' : cap(r.kind || 'record'))

/** Where it comes from, in a line: for a post its place, for a record its
 *  standing and who recorded it where, for a file what part of it and whose. */
export function sourceOf(r: Resolved): string {
  const place = r.where ? [r.where.number != null ? `#${r.where.number}` : '', r.where.conversation_name ?? ''].filter(Boolean).join(' in ') : ''
  if (r.kind === 'contribution') return [place, r.by ? `by ${r.by}` : ''].filter(Boolean).join(' · ')
  if (r.kind === 'file') {
    const f = r.file
    const from = f?.collection ? `from ${f.collection}` : f?.origin === 'submission' ? `attached${r.by ? ` by ${r.by}` : ''}` : f?.origin === 'execution' ? 'returned by an agent' : ''
    return [r.passage ? 'a cited passage of it' : 'the whole file', f?.size != null ? bytes(f.size) : '', from].filter(Boolean).join(' · ')
  }
  return [r.status ? statusWord(r.status) : '', r.by ? `recorded by ${r.by}` : '', place].filter(Boolean).join(' · ')
}

/** The same sort of row a search finds: the words, the Kind, the source. The
 *  reference is exactly the server's. */
export function refOf(r: Resolved): Ref {
  return { ref: r.ref ?? '', label: clip(r.label || 'No words recorded'), kind: kindOf(r), note: sourceOf(r) }
}

export const NOT_A_REFERENCE = 'That is not a link or an id from Mentis. Paste a link copied from a record or a post, or search by words above.'
export const NOT_HELD = 'Nothing in this Brain has that link or id. Nothing was added.'

/** Why something that was found cannot be added here, in plain words. */
export function refusalOf(r: Resolved): string {
  const what = `That is ${kindOf(r) === 'File' ? `the file “${clip(r.label || 'with no name', 60)}”` : `a ${kindOf(r).toLowerCase()} (“${clip(r.label || 'no words', 60)}”)`}`
  const why = r.kind === 'file' && r.file?.state && r.file.state !== 'held'
    ? (r.file.state === 'purged' ? 'it was removed from this Brain' : 'its contents are not in this Brain now')
    : r.kind === 'file' && r.passage ? 'the passage it names is not in that file'
      : 'it was deleted or cannot be cited'
  return `${what}, but ${why}. Nothing was added.`
}

/** What pasted text is, asked of the server by exact id. Refused in words
 *  where it is no reference, names nothing held, or cannot be used. */
export async function resolvePasted(text: string): Promise<Ref> {
  const asked = parsePasted(text)
  if (!asked) throw new Error(NOT_A_REFERENCE)
  const got = await read<Resolved>(`/api/ladder/resolve${qs('ref' in asked ? { ref: asked.ref } : { conversation: asked.conversation, number: asked.number })}`)
  if (!got.found || !got.ref) throw new Error(NOT_HELD)
  if (got.usable === false) throw new Error(refusalOf(got))
  return refOf(got)
}
