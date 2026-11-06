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

const { isImage, formatSize } = await import('../src/quiet/media/MediaPart.tsx')

test('a part the server verified as a picture is an image, whatever it was claimed as', () => {
  assert.equal(isImage({ type: 'image', ref: 'ent-1' }), true)
  assert.equal(isImage({ type: 'file', ref: 'ent-1', artifact: { ref: 'ent-1', state: 'held', treatment: { view: 'image', content_type: 'image/png', claimed: null, agrees: false } } }), true)
})
test('a claimed image media type is believed only when nothing stronger says otherwise', () => {
  assert.equal(isImage({ type: 'file', ref: 'ent-1', media_type: 'image/jpeg' }), true)
  assert.equal(isImage({ type: 'file', ref: 'ent-1', artifact: { ref: 'ent-1', state: 'held', claimed_media_type: 'IMAGE/PNG' } }), true)
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
