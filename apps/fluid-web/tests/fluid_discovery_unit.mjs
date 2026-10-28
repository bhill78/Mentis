import { registerHooks } from 'node:module'
import { readFileSync, existsSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import assert from 'node:assert/strict'
import ts from '../node_modules/typescript/lib/typescript.js'

registerHooks({
  resolve(specifier, context, next) {
    if (specifier.startsWith('.')) {
      for (const suffix of ['.ts', '.tsx', '/index.ts']) {
        const url = new URL(specifier + suffix, context.parentURL)
        if (existsSync(fileURLToPath(url))) return { url: url.href, shortCircuit: true }
      }
    }
    return next(specifier, context)
  },
  load(url, context, next) {
    if (/\.tsx?$/.test(url)) return { format: 'module', shortCircuit: true,
      source: ts.transpileModule(readFileSync(fileURLToPath(url), 'utf8'), {
        compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX },
      }).outputText }
    return next(url, context)
  },
})

const { groupDiscovery, navigatorIndex, postSubtree, readContentsScope, summaryRow } = await import('../src/fluid/conversation/discovery.ts')

assert.equal(navigatorIndex(0, 'ArrowLeft', 3), 2, 'left wraps to the final object')
assert.equal(navigatorIndex(2, 'ArrowDown', 3), 0, 'down wraps to the first object')
assert.equal(navigatorIndex(1, 'Enter', 3), null, 'only arrows move the navigator')

const rows = [
  { address: 'a', post: 'p2', number: 2, replyTo: 1, kind: 'chart', title: 'A' },
  { address: 'b', post: 'p2', number: 2, replyTo: 1, kind: 'file', title: 'B' },
  { address: 'c', post: 'p4', number: 4, replyTo: 3, kind: 'form', title: 'C' },
]
assert.deepEqual(groupDiscovery(rows, ['p1', 'p2', 'p3', 'p4']).map((g) => [g.post, g.items.map((x) => x.address)]),
  [['p2', ['a', 'b']], ['p4', ['c']]], 'By reply omits posts with no objects')

assert.deepEqual(summaryRow({ address: 'live:p2:k', exact: 'exact:v:0:k', post: 'p2', number: 2,
  reply_to_number: 1, kind: 'chart', title: 'Ambush', home: 'c' }),
{ address: 'live:p2:k', exact: 'exact:v:0:k', post: 'p2', number: 2, replyTo: 1, kind: 'chart', title: 'Ambush' })

const posts = ['top', 'reply', 'nested', 'sibling', 'other']
const parents = new Map([['top', null], ['reply', 'top'], ['nested', 'reply'], ['sibling', 'top'], ['other', null]])
const subtree = (root) => [...postSubtree(root, posts, (post) => parents.get(post))]
assert.deepEqual(subtree('top'), ['top', 'reply', 'nested', 'sibling'], 'a top-level post includes all replies at every depth')
assert.deepEqual(subtree('reply'), ['reply', 'nested'], 'a reply includes only its own subtree')
assert.deepEqual(subtree('nested'), ['nested'], 'a nested reply includes itself when it has no replies')

assert.equal(readContentsScope('post'), 'post', 'a saved post scope is retained')
assert.equal(readContentsScope(undefined), 'conversation', 'an older saved layout remains conversation-scoped')
assert.equal(readContentsScope('unexpected'), 'conversation', 'an invalid saved scope safely reads as the default')

console.log('fluid discovery: navigator, grouping, Contents subtree and scope passed')
