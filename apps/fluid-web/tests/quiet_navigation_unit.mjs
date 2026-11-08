// Real React rendering at the navigation/chrome seam. No browser claims.
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

const { default: NavigationRail, NavigationFilter } = await import('../src/quiet/navigation/NavigationRail.tsx')
const { ConversationNav } = await import('../src/quiet/chrome/Chrome.tsx')
const { TopicsNav, RailTools } = await import('../src/quiet/rail/Rail.tsx')

test('desktop rails have independent named disclosures and content targets', () => {
  const html = render(h('div', null,
    h(NavigationRail, { side: 'left', title: 'Conversations' }, 'Left reading navigation'),
    h(NavigationRail, { side: 'right', title: 'Topics' }, 'Right reading navigation')))
  for (const side of ['left', 'right']) {
    assert.match(html, new RegExp(`aria-controls="qc-navigation-${side}"`))
    assert.match(html, new RegExp(`id="qc-navigation-${side}"`))
  }
  assert.equal((html.match(/aria-expanded="true"/g) ?? []).length, 2)
  assert.match(html, /aria-label="Hide conversations"/)
  assert.match(html, /aria-label="Hide topics"/)
})

test('narrow first render keeps navigation contents hidden behind labelled tabs', () => {
  globalThis.window = { innerWidth: 390 }
  try {
    const html = render(h(NavigationRail, { side: 'left', title: 'Conversations' }, 'Navigation contents'))
    assert.match(html, /aria-label="Show conversations"/)
    assert.match(html, /aria-expanded="false"/)
    assert.match(html, /class="qc-navigation-content" hidden=""/)
  } finally { delete globalThis.window }
})

test('conversation and topic navigation retain addresses, names and current selection', () => {
  const choices = [1, 2].map((n) => ({ id: `ent-c${n}`, name: `Conversation ${n} & notes`, about: '',
    turns: n, awaiting: 0, live_executions: 0, last_activity: n }))
  const conversations = { choices, loaded: true, loading: false, error: null, reload() {} }
  const left = render(h(ConversationNav, { conversation: 'ent-c1', conversations }))
  assert.match(left, /href="#\/c\/ent-c1"[^>]*aria-current="page"/)
  assert.match(left, /Conversation 1 &amp; notes/)
  const facts = { topics: [{ id: 'ent-topic', name: 'A long topic & notes', about: '', turns: 12 }] }
  const right = render(h(TopicsNav, { conversation: 'ent-c1', topic: 'ent-topic', facts }))
  assert.match(right, /href="#\/c\/ent-c1\/t\/ent-topic"[^>]*aria-current="page"/)
  assert.match(right, /A long topic &amp; notes/)
  assert.match(right, /href="#\/c\/ent-c1"[^>]*><span>All posts<\/span>/)
  for (const [html, label] of [[left, 'Find a conversation'], [right, 'Find a topic']]) {
    assert.match(html, new RegExp(`aria-label="${label}"`))
    assert.match(html, />Filter<\/button>/)
  }
})

test('working readings keep their existing controls without a second Topics selector', () => {
  const html = render(h(RailTools, { rail: 'carried', choose() {} }))
  assert.match(html, />Brief<\/button>/)
  assert.match(html, />Activity<\/button>/)
  assert.match(html, /aria-expanded="true"[^>]*>Carried<\/button>/)
  assert.doesNotMatch(html, />Topics<\/button>/)
  const filter = render(h(NavigationFilter, { id: 'example-filter', label: 'Find a topic', query: '', change() {} }))
  assert.match(filter, /aria-controls="example-filter"/)
  assert.match(filter, /aria-expanded="false"/)
})
