/* ------------------------------------------------------------------------ *
 * WHAT AN OBJECT IS: ONE ANSWER (Fluid, the object-kind registry).
 *
 * Four places used to decide this each for itself, and they disagreed: the
 * post card's chip (mentis/fluid/objects.py `chip_kind`) called a Markdown
 * attachment a "doc" while the list called it a "file"; a `.png` with no
 * media type was an "image" on the chip and a file card in the zone; a
 * video was "video" in a list, "file" under Only some kinds, and media under
 * Show Media. Now `kindOf` decides once:
 *
 *   ./postobjects.ts   puts it on every object it keys (`is`), so the
 *                      server's extraction carries it;
 *   objects.py         names the chip from `is.chip`;
 *   the Fluid client   (workspace/hooks.ts, present/Present.tsx,
 *                      workspace/ObjectBody.tsx) reads `is`, and asks
 *                      `kindOf` itself for an object read before it was
 *                      carried.
 *
 * PURE: no React, no DOM, no `URL`. The server runs this in its embedded
 * engine (QuickJS) through dist/render-check.js.
 * ------------------------------------------------------------------------ */
import { readBlock } from './spec/core'
import type { TableData } from './spec/table'

/** Which part of the Show menu an object answers to.
 *  text      the post's own words (Everything only)
 *  section   a block its author wrote (Its sections)
 *  media     what is seen or heard: pictures, film, sound, video links
 *  file      any other attachment or returned file (Files)
 *  link      a link the post makes */
export type Family = 'text' | 'section' | 'media' | 'file' | 'link'

/** Where it came from, for the card's quiet source line. */
export type Source = 'text' | 'block' | 'figure' | 'attachment' | 'returned' | 'link'

export interface ObjectIs {
  /** one word for what it is: a block's type as the chip names it, or
   *  image, video, audio, doc, file, link, text */
  word: string
  /** what the post card's chip calls it; null where the chip names nothing
   *  (the post's own words, or an object inside another) */
  chip: string | null
  family: Family
  /** the "Only some kinds" choice it answers to (KINDS' ids) */
  filter: string
  /** drawn as its words: through the Markdown renderer, as written, or not */
  doc: 'markdown' | 'plain' | null
  source: Source
  /** something the reader fills in: a form, a checklist, a table with
   *  editable columns or rows to choose, a pad (`fillableOf`). Only blocks
   *  carry it; a block's `is` without it came from an older bundle, and is
   *  asked again. */
  fillable?: boolean
  /** a file's badge (its extension, upper case) and the badge's tone */
  badge?: string
  tone?: string
}

/** What `kindOf` reads of an object: the fields every keyed object has. */
export interface Kindable {
  kind: string
  type: string
  title?: string | null
  media_type?: string | null
  parent?: string | null
  link?: { video?: string | null } | null
  /** a block's fence line and body, which say whether a table may be filled in */
  block?: { info?: string; body?: string; closed?: boolean } | null
  is?: ObjectIs
}

/** What the chip calls a block type where it is not the type's own name
 *  (the demo's "doc"). objects.py's CHIP_NAME is this. */
export const CHIP_NAME: Readonly<Record<string, string>> = { pad: 'note', ref: 'reference', markdown: 'doc' }

/** The "Only some kinds" choices, in the order the zone sheet offers them. */
export const KINDS: readonly { id: string; name: string }[] = [
  { id: 'table', name: 'Tables' }, { id: 'chart', name: 'Charts' }, { id: 'diagram', name: 'Diagrams' },
  { id: 'timeline', name: 'Timelines' }, { id: 'checklist', name: 'Checklists' }, { id: 'form', name: 'Forms' },
  { id: 'image', name: 'Images' },
  { id: 'video', name: 'Videos' }, { id: 'file', name: 'Files' }, { id: 'link', name: 'Links' },
  { id: 'other', name: 'Other blocks' },
]
const NAMED_KINDS = new Set(['table', 'chart', 'diagram', 'timeline', 'checklist', 'form'])

/** Is a block one the reader fills in? Forms, checklists and pads always
 *  are; a table is when, read by the table's own rules, it names editable
 *  columns or lets rows be chosen. A table those rules refuse (an editable
 *  column it lacks, the key made editable) is drawn as source, so it is
 *  never fillable. The other blocks a person marks (compare, review) are
 *  not, yet: the design's fillable blocks are these four (forms revision 3,
 *  F6). */
export function fillableOf(type: string, block?: { info?: string; body?: string; closed?: boolean } | null): boolean {
  const t = type.toLowerCase()
  if (t === 'form' || t === 'checklist' || t === 'pad') return true
  if (t !== 'table' || !block?.info) return false
  const r = readBlock({ type: 'table', info: block.info, body: block.body ?? '', closed: block.closed ?? true })
  const data = r.data as TableData | null
  return r.ok && !!data && (data.editable.length > 0 || data.select !== 'none')
}

const IMAGE_NAME = /\.(png|jpe?g|gif|webp|svg)$/i
/** Text drawn as its words (the server's `is_text`; Markdown apart). */
const TEXT_NAME = /\.(txt|py|json|jsonl|ts|tsx|js|jsx|mjs|cjs|css|scss|xml|ya?ml|toml|ini|cfg|conf|sh|ps1|bat|sql|csv|tsv|log|rs|go|java|kt|c|h|cpp|hpp|cs|rb|php|swift|diff|patch|env|gitignore|dockerfile)$/i
const TEXT_TYPES = new Set(['application/json', 'application/xml', 'application/javascript', 'application/x-python',
  'application/x-sh', 'application/yaml', 'application/x-yaml', 'application/toml', 'application/sql', 'application/x-ndjson'])

/** A file's badge tone, by its badge (Classic's TurnMedia `TONE`). */
const TONE: Readonly<Record<string, string>> = {
  MD: 'md', MARKDOWN: 'md', HTML: 'html', HTM: 'html', PDF: 'pdf',
  CSV: 'data', TSV: 'data', JSON: 'data', JSONL: 'data', XLSX: 'data', XML: 'data',
  CSS: 'code', JS: 'code', TS: 'code', TSX: 'code', JSX: 'code', PY: 'code', SH: 'code',
  PS1: 'code', SQL: 'code', YAML: 'code', YML: 'code', TOML: 'code',
}

/** 'markdown', 'plain' or null: is an attachment drawn as its words? Any
 *  text type but HTML (opened, not read as source), a structured text
 *  type, or a text file's name. */
export function docOf(mediaType: string | null | undefined, name: string | null | undefined): 'markdown' | 'plain' | null {
  const mt = (mediaType ?? '').toLowerCase().split(';')[0].trim(), nm = name ?? ''
  if (/^text\/(x-)?markdown$/.test(mt) || /\.(md|markdown)$/i.test(nm)) return 'markdown'
  if ((mt.startsWith('text/') && mt !== 'text/html') || TEXT_TYPES.has(mt) || /\+(json|xml)$/.test(mt) || TEXT_NAME.test(nm)) return 'plain'
  return null
}

/** What an object is. An object that already carries `is` (the server's
 *  extraction put it there) is answered from it. */
export function kindOf(o: Kindable): ObjectIs {
  if (o.is && (o.kind !== 'block' || o.is.fillable !== undefined)) return o.is
  const top = o.parent === null || o.parent === undefined
  if (o.kind === 'post-text') return { word: 'text', chip: null, family: 'text', filter: 'text', doc: null, source: 'text' }
  if (o.kind === 'link') {
    const video = !!o.link?.video
    return { word: video ? 'video' : 'link', chip: top ? (video ? 'video' : 'link') : null, family: video ? 'media' : 'link',
      filter: video ? 'video' : 'link', doc: null, source: 'link' }
  }
  if (o.kind === 'block') {
    const t = String(o.type || 'block').toLowerCase()
    const word = CHIP_NAME[t] ?? t
    return { word, chip: top ? word : null, family: 'section', filter: NAMED_KINDS.has(o.type) ? o.type : 'other', doc: null, source: 'block',
      fillable: fillableOf(t, o.block) }
  }
  const mt = (o.media_type ?? '').toLowerCase()
  const name = o.title ?? ''
  const source: Source = o.kind === 'figure' ? 'figure' : o.type === 'returned' ? 'returned' : 'attachment'
  if (o.kind === 'figure' || mt.startsWith('image/') || IMAGE_NAME.test(name))
    return { word: 'image', chip: top ? 'image' : null, family: 'media', filter: 'image', doc: null, source }
  const ext = /\.([a-z0-9]{1,5})$/i.exec(name)?.[1]?.toUpperCase()
  if (mt.startsWith('video/') || mt.startsWith('audio/')) {
    const word = mt.startsWith('video/') ? 'video' : 'audio'
    return { word, chip: top ? 'file' : null, family: 'media', filter: word === 'video' ? 'video' : 'file', doc: null, source,
      badge: ext ?? word.toUpperCase(), tone: 'txt' }
  }
  const doc = docOf(mt, name)
  const badge = ext ?? (doc ? 'TXT' : 'FILE')
  return { word: doc ? 'doc' : 'file', chip: top ? (doc ? 'doc' : 'file') : null, family: 'file', filter: 'file', doc, source,
    badge, tone: TONE[badge] ?? 'txt' }
}
