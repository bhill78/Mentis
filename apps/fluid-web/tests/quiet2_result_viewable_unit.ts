/* WHICH VIEWER A FILE OPENS IN, AND WHAT IS SAID OF A BOUNDED READING,
 * checked without a browser (src/quiet2/viewer/viewableOfItem.ts,
 * src/quiet/media/view.ts).
 *
 * The rows are the navigation review's V1-V3: a PDF reaches pdf.js and a
 * picture its collection from EVERY path (a post, the dock, a result), the
 * server's verified word outranks a misleading file name, nothing gains a
 * renderer on a claim that did not already have one, and a truncated or
 * script-bearing file says what is drawn and what the frame refuses. */
import assert from 'node:assert/strict'
import { DRAWN_BYTES, FRAME_REFUSES, cutWords, itemOf, returnedItemOf, viewKindOf, type ViewerItem } from '../src/quiet/media/view'
import { isPdf, viewableOfItem } from '../src/quiet2/viewer/viewableOfItem'
import type { ViewImage } from '../src/quiet2/viewer/types'
import type { Part } from '../src/api'

let checks = 0
const eq = (a: unknown, b: unknown, what: string) => { assert.deepEqual(a, b, what); checks++ }
const ok = (a: unknown, what: string) => { assert.ok(a, what); checks++ }
const no = (a: unknown, what: string) => { assert.ok(!a, what); checks++ }

const item = (over: Partial<ViewerItem> = {}): ViewerItem => ({
  url: '/api/artifacts/adm-667a23eb07a8', name: 'report.md', alt: 'report', kind: 'markdown',
  ref: 'adm-667a23eb07a8', mediaType: 'text/markdown', size: 1024, ...over,
})
const PDF = item({ name: 'spec.pdf', kind: 'file', mediaType: 'application/pdf', treatment: 'pdf', url: '/api/artifacts/adm-pdf' })
const PICTURE = item({ name: 'shot.png', alt: 'a screenshot', kind: 'image', mediaType: 'image/png', treatment: 'image', url: '/api/artifacts/adm-png' })
const SIBLINGS: ViewImage[] = [
  { url: '/api/artifacts/adm-a', name: 'a.png', alt: 'a' },
  { url: '/api/artifacts/adm-png', name: 'shot.png', alt: 'a screenshot' },
  { url: '/api/artifacts/adm-c', name: 'c.png', alt: 'c' },
]

/* -- the server's verified word reaches the dispatcher ---------------------- */
{
  const part = { type: 'file', alt: 'spec.pdf', media_type: 'application/pdf', ref: 'adm-pdf',
    artifact: { ref: 'adm-pdf', url: '/api/artifacts/adm-pdf', name: 'spec.pdf', size: 99, claimed_media_type: 'application/pdf', treatment: { view: 'pdf' } } } as unknown as Part
  eq(viewKindOf(part), 'file', 'a PDF is still DRAWN as a file: a PDF viewer is a program (unchanged)')
  eq(itemOf(part)?.treatment, 'pdf', 'and the server’s own word is carried through, so the renderer can be chosen from it')
  const unread = { type: 'file', alt: 'notes.md', media_type: 'text/markdown', ref: 'adm-md',
    artifact: { ref: 'adm-md', url: '/u', name: 'notes.md', claimed_media_type: 'text/markdown' } } as unknown as Part
  eq(itemOf(unread)?.treatment, null, 'a conversation read verifies nothing, and absence is said as absence')
  eq(returnedItemOf({ ref: 'adm-x', state: 'held', url: '/u', name: 'x.html', treatment: { view: 'html' } })?.treatment, 'html', 'a returned artifact carries it too')
  eq(returnedItemOf({ ref: 'adm-x', state: 'not-held', url: '/u' }), null, 'and bytes that are not held are not an item at all')
}

/* -- a PDF, from every path (V1) -------------------------------------------- */
{
  ok(isPdf(PDF), 'the server read these bytes as a PDF')
  eq(viewableOfItem(PDF), { kind: 'pdf', url: '/api/artifacts/adm-pdf', name: 'spec.pdf', size: 1024 }, 'so it reaches pdf.js')
  eq(viewableOfItem(PDF, SIBLINGS).kind, 'pdf', 'siblings do not turn a document into a picture')
  ok(isPdf(item({ name: 'spec.pdf', kind: 'file', mediaType: 'application/pdf' })), 'with nothing verified, the claim and the name decide, exactly as before')
  ok(isPdf(item({ name: 'spec.PDF', kind: 'file', mediaType: '' })), 'including by name alone, as before')
  no(isPdf(item({ name: 'spec.pdf', kind: 'html', mediaType: 'text/html', treatment: 'html' })),
    'BUT A VERIFIED WORD OUTRANKS THE NAME: bytes the server read as HTML never reach the PDF program')
  no(isPdf(item({ name: 'notes.md', kind: 'markdown', mediaType: 'text/markdown', treatment: 'markdown' })), 'and a document stays a document')
  no(isPdf(item({ name: 'x', kind: 'file', mediaType: 'application/pdf-ish' })), 'a media type that merely contains "pdf" is not one')
  ok(isPdf(item({ name: 'x', kind: 'file', mediaType: 'application/x-pdf' })), 'the other spelling is')
}

/* -- a picture, in its collection (V1) -------------------------------------- */
{
  const v = viewableOfItem(PICTURE, SIBLINGS)
  eq(v.kind, 'gallery', 'a picture opens the collection viewer')
  eq(v.kind === 'gallery' && v.start, 1, 'with itself selected among its post’s pictures')
  eq(v.kind === 'gallery' && v.images.length, 3, 'and its siblings kept')
  const alone = viewableOfItem(PICTURE)
  eq(alone.kind === 'gallery' && alone.images, [{ url: '/api/artifacts/adm-png', name: 'shot.png', alt: 'a screenshot' }],
    'from the dock or a Brain record, where there are no siblings, a collection of one -- never a download-only row')
  const stranger = viewableOfItem(PICTURE, [SIBLINGS[0]])
  eq(stranger.kind === 'gallery' && stranger.start, 0, 'a picture that is not among the siblings given opens as itself')
  eq(stranger.kind === 'gallery' && stranger.images.length, 1, 'and not inside a collection it does not belong to')
  no(viewableOfItem(item({ name: 'mislabelled.txt', kind: 'file', mediaType: 'image/png' })).kind === 'gallery',
    'a claim never promotes a file the server called a file to a picture (view.ts’s own rule, unchanged)')
}

/* -- everything else keeps the existing body and its refusals (V2) ---------- */
{
  for (const k of ['markdown', 'text', 'html', 'video', 'audio', 'file'] as const) {
    const v = viewableOfItem(item({ kind: k, name: `x.${k}`, mediaType: '', treatment: k === 'file' ? 'download' : k }))
    eq(v.kind, 'file', `drawn by the existing viewer body, or offered: ${k}`)
    eq(v.kind === 'file' && v.item.kind, k, 'with its kind unchanged')
  }
  const unknown = viewableOfItem(item({ kind: 'file', name: 'archive.zip', mediaType: 'application/zip', treatment: 'download' }))
  eq(unknown.kind, 'file', 'an archive is the existing download offer, and no new renderer')
}

/* -- what a bounded reading says (V3, NB2) ---------------------------------- */
{
  eq(DRAWN_BYTES, 262144, 'the viewer draws the first 256 KB (`/fluid/api/document`), stated')
  const words = cutWords(639715)
  ok(/256\.0 KB/.test(words), 'a truncated reading says how much is drawn')
  ok(/624\.7 KB/.test(words), 'and how big the file actually is')
  ok(/[Dd]ownload/.test(words), 'with the whole file beside it')
  ok(!/\bNaN\b|undefined|null/.test(cutWords(null)), 'an unknown size says nothing false')
  for (const w of ['script', 'form', 'network', 'nested frame']) ok(new RegExp(w, 'i').test(FRAME_REFUSES), `the frame says it refuses: ${w}`)
  ok(/preview/i.test(FRAME_REFUSES), 'and that it is a preview, not a working page')
}

console.log(`quiet2 result viewable: ${checks} checks ok`)
