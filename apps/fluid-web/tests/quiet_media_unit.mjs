import { registerHooks } from 'node:module'
import { readFileSync, existsSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import assert from 'node:assert/strict'
import test from 'node:test'
import ts from '../node_modules/typescript/lib/typescript.js'

/* The same TS loader as the other client unit suites, plus stylesheets:
   MediaPart.tsx imports its own CSS, which node cannot read and which this
   suite is not about. */
registerHooks({
  resolve(specifier, context, next) {
    if (specifier.startsWith('.')) {
      if (/\.css$/.test(specifier)) {
        return { url: new URL(specifier, context.parentURL).href, shortCircuit: true }
      }
      for (const suffix of ['.ts', '.tsx', '/index.ts']) {
        const url = new URL(specifier + suffix, context.parentURL)
        if (existsSync(fileURLToPath(url))) return { url: url.href, shortCircuit: true }
      }
    }
    return next(specifier, context)
  },
  load(url, context, next) {
    if (/\.css$/.test(url)) return { format: 'module', shortCircuit: true, source: 'export {}' }
    if (/\.tsx?$/.test(url)) return {
      format: 'module', shortCircuit: true,
      source: ts.transpileModule(readFileSync(fileURLToPath(url), 'utf8'), {
        compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX },
      }).outputText,
    }
    return next(url, context)
  },
})

import { readFileSync as readSource } from 'node:fs'

const { isImage, formatSize } = await import('../src/quiet/media/MediaPart.tsx')
const { viewKindOf, itemOf, kindWords } = await import('../src/quiet/media/view.ts')

const src = (file) => readSource(fileURLToPath(new URL('../src/' + file, import.meta.url)), 'utf8')

test('a part the server verified as a picture is an image, whatever it was claimed as', () => {
  assert.equal(isImage({ type: 'image', ref: 'ent-1' }), true)
  assert.equal(isImage({ type: 'file', ref: 'ent-1', artifact: { ref: 'ent-1', state: 'held', treatment: { view: 'image', content_type: 'image/png', claimed: null, agrees: false } } }), true)
})
test('a claimed image media type is believed only when nothing stronger says otherwise', () => {
  assert.equal(isImage({ type: 'file', ref: 'ent-1', media_type: 'image/jpeg' }), false)
  assert.equal(isImage({ type: 'file', ref: 'ent-1', artifact: { ref: 'ent-1', state: 'held', claimed_media_type: 'IMAGE/PNG' } }), false)
})
test('a plain file is never read as an image', () => {
  assert.equal(isImage({ type: 'image', ref: 'ent-1', artifact: { treatment: { view: 'file' }, claimed_media_type: 'image/png' } }), false)
  assert.equal(isImage({ type: 'file', ref: 'ent-1', media_type: 'application/pdf' }), false)
  assert.equal(isImage({ type: 'file', ref: 'ent-1' }), false)
})
test('size is read at the scale a person would, with nothing shown for an unknown size', () => {
  assert.equal(formatSize(null), null)
  assert.equal(formatSize(undefined), null)
  assert.equal(formatSize(512), '512 B')
  assert.equal(formatSize(2048), '2.0 KB')
  assert.equal(formatSize(5 * 1024 * 1024), '5.0 MB')
})

/* -- ROUND 4: what the in-app viewer draws it as --------------------------- */

const held = (treatment, extra = {}) => ({
  type: 'file', ref: 'ent-1',
  artifact: { ref: 'adm-1', state: 'held', url: '/api/artifacts/adm-1', ...extra, ...(treatment ? { treatment: { view: treatment, content_type: 'text/plain; charset=utf-8', claimed: null, agrees: true } } : {}) },
})

test("the server's own word for the bytes decides how they are drawn", () => {
  assert.equal(viewKindOf(held('html')), 'html')
  assert.equal(viewKindOf(held('markdown')), 'markdown')
  assert.equal(viewKindOf(held('text')), 'text')
  assert.equal(viewKindOf(held('image')), 'image')
  // A PDF viewer is a program; the server serves one as an attachment.
  assert.equal(viewKindOf(held('pdf')), 'file')
  assert.equal(viewKindOf(held('download')), 'file')
})

test('bytes verified as text are text, whatever the sender claimed they were', () => {
  // The browser suite's `mislabelled.txt`: claimed image/png, read as text.
  assert.equal(viewKindOf(held('text', { claimed_media_type: 'image/png' })), 'text')
  assert.equal(isImage(held('text', { claimed_media_type: 'image/png' })), false)
})

test('a turn read carries no treatment, so the claim and the name read the rest', () => {
  // What a conversation read actually sends: state, size, name, claim.
  const sent = (name, claim) => ({
    type: 'file', ref: 'ent-1', alt: name, media_type: claim,
    artifact: { ref: 'adm-1', state: 'held', url: '/api/artifacts/adm-1', name, size: 9, claimed_media_type: claim },
  })
  assert.equal(viewKindOf(sent('mockup.html', 'text/html')), 'html')
  assert.equal(viewKindOf(sent('notes.txt', 'text/plain')), 'text')
  assert.equal(viewKindOf(sent('plan.md', 'text/markdown')), 'markdown')
  // The name answers where the sender claimed nothing usable.
  assert.equal(viewKindOf(sent('mockup.html', 'application/octet-stream')), 'html')
  assert.equal(viewKindOf(sent('archive.zip', 'application/zip')), 'file')
  // AND NEVER A PICTURE ON A CLAIM: the server decided that from the bytes
  // and wrote it into the part's type.
  assert.equal(viewKindOf(sent('mislabelled.txt', 'image/png')), 'file')
  assert.equal(isImage(sent('mislabelled.txt', 'image/png')), false)
})

test('film and sound have no signature to read, so the claim is all there is', () => {
  assert.equal(viewKindOf(held('download', { claimed_media_type: 'video/mp4' })), 'video')
  assert.equal(viewKindOf(held('download', { claimed_media_type: 'audio/mpeg' })), 'audio')
  assert.equal(viewKindOf({ type: 'file', ref: 'ent-1', media_type: 'video/webm' }), 'video')
})

test('the viewer is handed a reading of the part, or nothing where there are no bytes', () => {
  assert.equal(itemOf({ type: 'file', ref: 'ent-1' }), null)
  const item = itemOf({
    type: 'file', ref: 'ent-1', alt: 'mockup.html',
    artifact: { ref: 'adm-9', state: 'held', url: '/api/artifacts/adm-9', name: 'mockup.html', size: 2048, claimed_media_type: 'text/html', treatment: { view: 'html', content_type: 'text/plain; charset=utf-8', claimed: 'text/html', agrees: true } },
  })
  assert.deepEqual(item, {
    url: '/api/artifacts/adm-9', name: 'mockup.html', alt: 'mockup.html', kind: 'html',
    ref: 'adm-9', mediaType: 'text/html', size: 2048,
  })
  assert.equal(kindWords[item.kind], 'html mockup')
})

/* -- ROUND 4: nothing leaves the page to read an attachment ---------------- */

test('a file row is the control that opens it here, not a link out of the page', () => {
  const part = src('quiet/media/MediaPart.tsx')
  const code = part.replace(/\/\*[\s\S]*?\*\//g, '').replace(/^\s*\/\/.*$/gm, '')
  assert.match(part, /qc-media-file-open/, 'the row is its own control')
  assert.doesNotMatch(code, /<a\s/, 'no anchor in a part: a row no longer navigates')
  assert.match(part, /openViewer\(/, 'activating a row opens the in-app viewer')
  assert.match(part, /data-src-skip/, "an attachment's words are not the post's stored text")
})

test('the bytes stay reachable: the download link is inside the viewer', () => {
  const layer = src('quiet/media/MediaLayer.tsx')
  assert.match(layer, /href=\{item\.url\} download=\{item\.name\}/,
    'the viewer offers the artifact URL as a download')
  assert.match(layer, /HtmlFrame/, 'written html is drawn in the one guarded frame')
  assert.match(layer, /useDocument/, 'a document is read bounded, not fetched whole')
  assert.match(layer, /aria-modal="true"/, 'the viewer is still a modal dialog with its own focus trap')
})
