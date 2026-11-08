// Real React rendering at the Track B navigation seam. No browser claims.
import { registerHooks } from 'node:module'
import { readFileSync, existsSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import assert from 'node:assert/strict'
import test from 'node:test'
import { createElement as h } from 'react'
import { renderToStaticMarkup as render } from 'react-dom/server'
import ts from '../node_modules/typescript/lib/typescript.js'

registerHooks({
  resolve(specifier, context, next) {
    if (specifier.startsWith('.')) {
      if (/\.css$/.test(specifier)) return { url: new URL(specifier, context.parentURL).href, shortCircuit: true }
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

const { default: ConversationsRail } = await import('../src/quiet/floatnav/ConversationsRail.tsx')
const { default: TopicsFloat, TopicsToggle } = await import('../src/quiet/floatnav/TopicsFloat.tsx')
const { RailTools } = await import('../src/quiet/rail/Rail.tsx')

test('the Conversations rail opens on desktop and names its toggle and content', () => {
  const html = render(h(ConversationsRail, null, 'Conversation navigation'))
  assert.match(html, /aria-label="Hide conversations"/)
  assert.match(html, /aria-expanded="true"/)
  assert.match(html, /id="qc-conversations-content"/)
  assert.match(html, /Conversation navigation/)
})

test('the Conversations rail starts closed behind a labelled tab on a narrow first render', () => {
  globalThis.window = { innerWidth: 390 }
  try {
    const html = render(h(ConversationsRail, null, 'Conversation navigation'))
    assert.match(html, /aria-label="Show conversations"/)
    assert.match(html, /aria-expanded="false"/)
    assert.match(html, /class="qc-conversations-content" hidden=""/)
  } finally { delete globalThis.window }
})

test('closed, the Conversations rail still exports a function that mounts (seam compat)', () => {
  assert.equal(typeof ConversationsRail, 'function')
})

test('the Topics toggle names the floating panel it controls, and the panel renders only while open', () => {
  const toggle = render(h(TopicsToggle, { open: false, setOpen() {} }))
  assert.match(toggle, /aria-controls="qc-topics-float"/)
  assert.match(toggle, /aria-expanded="false"/)
  assert.match(toggle, />Topics<\/button>/)

  const facts = { topics: [{ id: 'ent-topic', name: 'A long topic & notes', about: '', turns: 12 }] }
  const closed = render(h(TopicsFloat, { open: false, close() {}, conversation: 'ent-c1', topic: null, facts }))
  assert.equal(closed, '')

  const open = render(h(TopicsFloat, { open: true, close() {}, conversation: 'ent-c1', topic: 'ent-topic', facts }))
  assert.match(open, /role="dialog"/)
  assert.match(open, /href="#\/c\/ent-c1\/t\/ent-topic"[^>]*aria-current="page"/)
  assert.match(open, /A long topic &amp; notes/)
  assert.match(open, /href="#\/c\/ent-c1"[^>]*><span>All posts<\/span>/)
})

test('working readings (Brief/Activity/Carried) keep their own controls; Topics is not one of them', () => {
  const html = render(h(RailTools, { rail: 'carried', choose() {} }))
  assert.match(html, />Brief<\/button>/)
  assert.match(html, />Activity<\/button>/)
  assert.match(html, /aria-expanded="true"[^>]*>Carried<\/button>/)
  assert.doesNotMatch(html, />Topics<\/button>/)
})
