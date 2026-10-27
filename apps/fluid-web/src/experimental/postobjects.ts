import { namesFor, objectsIn, turnPartScope } from './objects'
import { readBlock, type RBlock } from './spec/core'
import { csvRows } from './util'
import { linksOf } from './links'
import { kindOf, type ObjectIs } from './objectkinds'

/* ------------------------------------------------------------------------ *
 * EXPERIMENTAL: A POST'S OBJECTS, KEYED ONCE (Fluid Workspace, F1).
 *
 * ONE SOURCE OF OBJECT IDENTITY. The server bundles this file into
 * dist/render-check.js (through ./spec/check.ts) and runs it in its embedded
 * engine; the Fluid client imports it. So both key a post's objects with the
 * same function, and that function is the one the conversation already keys
 * blocks with: `objectsIn` (./objects.ts) over each text part, scoped by
 * `turnPartScope`. Attachments and what a run returned are keyed exactly as
 * the media reader keys them (../media.ts, `attachmentsOf`, `mediaOf`), and a
 * placed figure that is also an attachment is one object, the figure -- the
 * Workspace Lab's rule (../lab/items.ts, `objectsOfTurn`). The Lab keeps its
 * own composition of those readers for now; tests hold the two equal.
 *
 * PURE: no React, no DOM, nothing from node_modules -- the bundle refuses it.
 *
 * IDENTITY. A block that declares a usable `name=` unambiguous in its Turn
 * part is keyed by that name and is `stable`: it keeps its key through an
 * edit that moves it. Every other key is a position -- the n-th table, the
 * n-th run of words, the i-th part -- and says so (`stable: false`). What a
 * run returned is keyed by the artifact it names (`reference`, stable).
 *
 * LINKS (B5/B6). Every http(s) link the post's prose makes is an object of
 * its own, `kind: 'link'`, keyed by the URL as written
 * (`<root>:link:<url>`, `reference`, stable: an edit that moves the link
 * keeps it): its words and its domain (./links.ts), and the YouTube video
 * it is, if it is one. A URL too long for its address to fit the server's
 * cap (300 characters, `live:<root>:<key>`) is keyed by its start and a
 * digest of the whole instead (`linkKey`); every key that fitted is
 * unchanged. Nothing is fetched. They come last, after the media,
 * and only Fluid has them: the Workspace Lab keys none (tests hold the rest
 * equal).
 *
 * WHAT EACH IS (`is`): the one answer ./objectkinds.ts gives, carried on
 * every object so the server and the client read the same.
 * ------------------------------------------------------------------------ */

export interface PostPart {
  type: string
  text?: string
  ref?: string | null
  media_type?: string | null
  alt?: string | null
  /** what the server says stands behind the ref (mentis/artifacts.py `annotate_part`) */
  artifact?: unknown
  [k: string]: unknown
}

export interface Returned {
  ref: string
  name?: string | null
  claimed_media_type?: string | null
  [k: string]: unknown
}

/** A post as keyed: its ROOT id (what every key hangs from), its parts as
 *  the reader sees them, and what the run that posted it returned. */
export interface PostInput {
  id: string
  parts: PostPart[]
  returned_with?: Returned[]
}

export type Identity = 'declared' | 'reference' | 'positional'

export interface PostObject {
  /** exactly the key the conversation and the Lab hold its state under */
  key: string
  /** the index in `parts`; null for what a run returned */
  part: number | null
  kind: 'block' | 'figure' | 'post-text' | 'media' | 'link'
  /** a block's type; `figure`; `text`; `attachment` or `returned` for media;
   *  `link` or `video` for a link */
  type: string
  title: string | null
  /** the declared name the key uses; null when none or ambiguous */
  name: string | null
  /** a name declared but shared with another block, so not used */
  duplicate?: string
  identity: Identity
  stable: boolean
  /** the enclosing object's key; null at the top of the post */
  parent: string | null
  page: string | null
  /** lines in the part's text, counted from 1; null for media */
  line: number | null
  end: number | null
  /** a figure's or a medium's artifact */
  ref?: string | null
  media_type?: string | null
  /** a block's own Markdown, as the readers hold it */
  block?: RBlock
  /** a link: the URL as written, the author's words for it (null where the
   *  link was bare), its domain, and the YouTube video it is */
  link?: { url: string; label: string | null; domain: string; video: string | null }
  /** what it is (./objectkinds.ts) */
  is: ObjectIs
}

/** An object before `is` is put on it. */
type Keyed = Omit<PostObject, 'is'>

/** Which parts carry bytes: the media reader's rule (../media.ts `isAttachment`). */
export const isAttachmentPart = (p: PostPart) =>
  p.type === 'image' || p.type === 'file' || !!p.media_type || !!p.artifact

const fileName = (ref: string | null | undefined) => ref?.split('/').pop() ?? ''

/* `mediaOf` orders a Turn's media by key, numerically (`part:10` after
   `part:2`). localeCompare's numeric option is not in every engine the
   bundle runs in, so the same order is spelled out: digit runs compared as
   numbers, everything else as text. */
function naturalCompare(a: string, b: string): number {
  const ra = a.match(/\d+|\D+/g) ?? [], rb = b.match(/\d+|\D+/g) ?? []
  for (let i = 0; i < Math.min(ra.length, rb.length); i++) {
    const x = ra[i], y = rb[i]
    if (x === y) continue
    const nx = /^\d/.test(x), ny = /^\d/.test(y)
    if (nx && ny) return Number(x) - Number(y) || x.length - y.length
    return x < y ? -1 : 1
  }
  return ra.length - rb.length
}

/** The longest object address the server keeps (mentis/lab_workspaces.py
 *  `MAX_KEY`): a kept object's `live:<root>:<key>`. */
const MAX_ADDRESS = 300

/** A stable digest of a string: two FNV-1a lanes, 16 hex digits. Pure
 *  arithmetic, so the server's engine and the browser give the same. */
export function digest(s: string): string {
  let a = 0x811c9dc5, b = 0x01000193 ^ 0x5bd1e995
  for (let i = 0; i < s.length; i++) {
    const c = s.charCodeAt(i)
    a = Math.imul(a ^ c, 0x01000193)
    b = Math.imul(b ^ c, 0x01000193) ^ (b >>> 15)
  }
  return (a >>> 0).toString(16).padStart(8, '0') + (b >>> 0).toString(16).padStart(8, '0')
}

/** A link's key: `<root>:link:<url>` while its address fits the server's
 *  cap -- every key that ever fitted stays what it was -- and otherwise the
 *  URL's start, `…`, and a digest of the whole URL, so the address always
 *  fits and still says where it goes. */
export function linkKey(root: string, url: string): string {
  const whole = `${root}:link:${url}`
  const room = MAX_ADDRESS - `live:${root}:`.length
  if (whole.length <= room) return whole
  const tail = '…' + digest(url)
  /* never half a surrogate pair: the server stores the key as UTF-8 */
  const start = url.slice(0, Math.max(0, room - `${root}:link:`.length - tail.length)).replace(/[\uD800-\uDBFF]$/, '')
  return `${root}:link:${start}${tail}`
}

/** Every object of a post, in the Lab's order: each text part's objects
 *  (parents before their children), then its media. */
export function objectsOfPost(post: PostInput): PostObject[] {
  const out: Keyed[] = []
  const placed = new Set<string>()
  const parts = post.parts ?? []
  parts.forEach((p, i) => {
    if (p.type !== 'text' || !p.text) return
    const scope = turnPartScope(post.id, i)
    const names = namesFor(p.text, scope)
    for (const d of objectsIn(p.text, scope, names)) {
      if (d.ref) placed.add(d.ref)
      const declared = d.kind === 'block' && !!d.name
      out.push({
        key: d.key, part: i, kind: d.kind, type: d.type,
        title: d.label ?? (d.kind === 'post-text' ? 'Post text' : d.kind === 'figure' ? d.ref ?? 'figure' : d.type),
        name: d.name, ...(d.duplicate ? { duplicate: d.duplicate } : {}),
        identity: declared ? 'declared' : 'positional', stable: declared,
        parent: d.parent, page: d.page, line: d.line, end: d.end,
        ...(d.ref ? { ref: d.ref } : {}), ...(d.block ? { block: d.block } : {}),
      })
    }
  })
  const media: Keyed[] = []
  parts.forEach((p, i) => {
    if (!isAttachmentPart(p)) return
    const ref = p.ref ?? null
    media.push({
      key: `${post.id}:part:${i}`, part: i, kind: 'media', type: 'attachment',
      title: p.alt || fileName(p.ref) || p.type, name: null, identity: 'positional', stable: false,
      parent: null, page: null, line: null, end: null, ref, media_type: p.media_type ?? null,
    })
  })
  for (const a of post.returned_with ?? []) {
    media.push({
      key: `${post.id}:returned:${a.ref}`, part: null, kind: 'media', type: 'returned',
      title: a.name || a.ref, name: null, identity: 'reference', stable: true,
      parent: null, page: null, line: null, end: null, ref: a.ref, media_type: a.claimed_media_type ?? null,
    })
  }
  media.sort((x, y) => naturalCompare(x.key, y.key))
  for (const m of media) if (!(m.ref && placed.has(m.ref))) out.push(m)
  const seen = new Set<string>()
  parts.forEach((p, i) => {
    if (p.type !== 'text' || !p.text) return
    for (const l of linksOf(p.text)) {
      if (seen.has(l.url)) continue
      seen.add(l.url)
      out.push({
        key: linkKey(post.id, l.url), part: i, kind: 'link', type: l.video ? 'video' : 'link',
        title: l.label ?? l.domain, name: null, identity: 'reference', stable: true,
        parent: null, page: null, line: l.line, end: l.end,
        link: { url: l.url, label: l.label, domain: l.domain, video: l.video },
      })
    }
  })
  return out.map((o) => ({ ...o, is: kindOf(o) }))
}

/* ---- export: what each object is, in the forms it can be had in ---- */

/** Types whose body is CSV, as their readers read it (./spec/*.ts). */
export const TABULAR: ReadonlySet<string> = new Set(['table', 'chart', 'timeline', 'calendar-heatmap', 'matrix-heatmap', 'gallery'])

const csvCell = (s: string) => (/[",\r\n]/.test(s) || s !== s.trim() ? `"${s.replace(/"/g, '""')}"` : s)

/** A CSV body re-read as the readers read it (`csvTable`'s rows), written back. */
export function csvOf(body: string): string {
  const rows = body.trim() ? csvRows(body.replace(/^\n+|\n+$/g, '')) : []
  return rows.map((r) => r.map(csvCell).join(',')).join('\n') + (rows.length ? '\n' : '')
}

export interface Extracted extends PostObject {
  /** the forms GET /fluid/api/objects/<address>?format= answers in */
  formats: ('json' | 'md' | 'csv')[]
  md?: string
  json: unknown
  csv?: string
}

/** Maps and Sets as JSON can carry them. */
const plain = (v: unknown): unknown => {
  if (v instanceof Map) return Object.fromEntries([...v].map(([k, x]) => [String(k), plain(x)]))
  if (v instanceof Set) return [...v].map(plain)
  if (Array.isArray(v)) return v.map(plain)
  if (v && typeof v === 'object') return Object.fromEntries(Object.entries(v).map(([k, x]) => [k, plain(x)]))
  return v
}

/** What the server serves of a post: every object with its own Markdown
 *  (the lines it occupies in its part), the reader's parsed form, and CSV
 *  where it is tabular. Media carry their reference, never bytes. */
export function extractPost(post: PostInput): { objects: Extracted[] } {
  const lines = (post.parts ?? []).map((p) => (p.type === 'text' && p.text ? p.text.replace(/\r\n?/g, '\n').split('\n') : []))
  const objects = objectsOfPost(post).map((o): Extracted => {
    if (o.kind === 'media')
      return { ...o, formats: ['json'], json: { ref: o.ref, media_type: o.media_type, title: o.title } }
    if (o.kind === 'link') {
      const l = o.link!
      return { ...o, formats: ['json', 'md'], md: `[${(l.label ?? l.url).replace(/[[\]]/g, '\\$&')}](${l.url})`,
        json: { url: l.url, title: o.title, label: l.label, domain: l.domain, video: l.video } }
    }
    const md = o.part !== null && o.line !== null && o.end !== null ? lines[o.part].slice(o.line - 1, o.end).join('\n') : ''
    if (o.kind === 'post-text') return { ...o, formats: ['json', 'md'], md, json: { text: md.trim() } }
    if (o.kind === 'figure') return { ...o, formats: ['json', 'md'], md, json: { ref: o.ref, title: o.title } }
    const r = readBlock(o.block!)
    const json = {
      type: o.type, attrs: r.attrs, extra: r.extra, shared: r.shared, ok: r.ok,
      problems: r.d.map((x) => ({ severity: x.sev, where: x.where, message: x.msg })), data: plain(r.data),
    }
    const tab = TABULAR.has(o.type)
    return { ...o, formats: tab ? ['json', 'md', 'csv'] : ['json', 'md'], md, json, ...(tab ? { csv: csvOf(o.block!.body) } : {}) }
  })
  return { objects }
}
