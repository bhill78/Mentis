// The independent review's five failing probes (adm-f3244dbc4bae R1, R1b, R2,
// R3, R4), re-run against the corrected code. R3 and R4 are the reviewer's own
// probe code, byte for byte. R1, R1b and R2 keep the reviewer's observations
// and assertions, and call what the REVISED hand-off says to call -- their
// original form asserted the presence of the defective snippet text, which is
// the thing that was removed.
import { registerHooks } from 'node:module'
import { readFileSync, existsSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import test from 'node:test'
import assert from 'node:assert/strict'
import ts from '../node_modules/typescript/lib/typescript.js'
registerHooks({
  resolve(specifier, context, next) {
    if (specifier.startsWith('.')) for (const suffix of ['.ts', '.tsx', '/index.ts']) {
      const url = new URL(specifier + suffix, context.parentURL)
      if (existsSync(fileURLToPath(url))) return { url: url.href, shortCircuit: true }
    }
    return next(specifier, context)
  },
  load(url, context, next) {
    if (url.endsWith('.css')) return { format: 'module', source: '', shortCircuit: true }
    if (/\.tsx?$/.test(url)) return { format: 'module', shortCircuit: true, source: ts.transpileModule(readFileSync(fileURLToPath(url), 'utf8'), { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX } }).outputText }
    return next(url, context)
  },
})
globalThis.localStorage = { getItem: () => null, setItem: () => {}, removeItem: () => {} }
const { heldItem } = await import('../src/quiet2/brain/logic.ts')
// the actual picturesOf declaration alone, as the reviewer extracted it
const postCode = readFileSync(new URL('../src/quiet2/Post.tsx', import.meta.url), 'utf8')
const picturesCode = postCode.slice(postCode.indexOf('export function picturesOf(')).split('\n}')[0] + '\n}'
const picturesJs = ts.transpileModule(picturesCode.replace('export function', 'function'), { compilerOptions: { target: ts.ScriptTarget.ES2022 } }).outputText
const picturesOf = new Function('imageOf', picturesJs + '; return picturesOf')(x => x)
const { viewableOfItem } = await import('../src/quiet2/viewer/viewableOfItem.ts')
const { destinationOfRef } = await import('../src/quiet2/results/targets.ts')
const { clearLaunches, beginOpening, holdLaunch, launchOf, historyOf, restoreOf } = await import('../src/quiet2/results/launch.ts')
const { openResultTarget, leaves } = await import('../src/quiet2/results/opener.ts')
const { fileContent, siblingsOf } = await import('../src/quiet2/results/hostOpen.ts')
const handoff = readFileSync(new URL('../src/quiet2/results/HOST-INTEGRATION.md', import.meta.url), 'utf8')
const brain = 'fixture-corpus@instance-1'
const ref = 'adm-123456789abc'
const launch = () => holdLaunch({ opening: beginOpening(), brainKey: brain, place: { conversation: 'ent-111111111111', centre: null }, thread: null, reading: { scroll: 417, offset: 12 }, reply: 'ent-222222222222', draft: 'fixture-draft-key', focus: { control: 'fixture-control', fallback: { kind: 'conversation' } } })
const dest = () => destinationOfRef({ id: ref, type: 'file', state: 'ok', available: true, opens: 'file', file: { state: 'held', name: 'notes.md', size: 18, claimed_media_type: 'text/markdown' } })
const open = (over = {}) => ({ ref, item: null, file: dest().file, source: { kind: 'brain', brainKey: brain }, launch: launch(), settled: () => {}, ...over })

test('R1: the requested Admission survives the file adapter', () => {
  // the defective call is no longer instructed anywhere: the one line that
  // still shows it is the findings table, saying it was the defect
  const shows = handoff.split('\n').filter((l) => /heldItem\(\/\* ref \*\/ '', file as never\)/.test(l))
  console.log('R1 defect quoted on', shows.length, 'line(s), all in the findings table:', shows.every((l) => l.startsWith('| **B1** |')))
  assert.ok(shows.every((l) => l.startsWith('| **B1** |')))
  assert.match(handoff, /fileContent\(o, \{ item: heldItem, post: postOf, pictures: picturesOf \}\)/)
  const read = fileContent(open(), { item: heldItem })
  console.log('R1 observed:', JSON.stringify(read.content?.item ?? read))
  assert.equal(read.content.item.ref, ref)
  assert.equal(read.content.item.url, '/api/artifacts/' + ref)
})
test('R1b: a Brain-sourced file opens without a source post', () => {
  assert.equal(/picturesOf\(postOf\(postSource\(source!\)\?\.post \?\? ''\) \?\? undefined\)/.test(handoff), false)
  // postOf answers undefined for a ref with no post; the real picturesOf throws on it
  const postOf = () => undefined
  const page = { item: heldItem, post: postOf, pictures: picturesOf }
  assert.doesNotThrow(() => fileContent(open(), page))
  assert.equal(siblingsOf({ kind: 'brain', brainKey: brain }, page), undefined)
  assert.equal(siblingsOf({ kind: 'post', conversation: 'ent-c', post: 'ent-88' }, page), undefined)
})
test('R2: the file host is given the caller launch', () => {
  clearLaunches(); const supplied = launch(); let received
  const onView = (_content, _source, l = launch()) => { received = l; return 'max' }
  const d = { ...dest(), item: heldItem(ref, dest().file) }
  openResultTarget(d, supplied, { brainKey: brain, origin: 'https://mentis.test', file: (o) => onView(viewableOfItem(o.item), o.source, o.launch) })
  console.log('R2 observed:', JSON.stringify({ supplied: supplied.opening, received: received.opening, stillHeld: !!launchOf(supplied.opening) }))
  assert.equal(received.opening, supplied.opening)
})
test('R3: opening a second side viewer retains the first live return', () => {
  clearLaunches(); const first = launch(); const mark = historyOf(first); launch()
  const result = restoreOf(mark, { brainKey: brain, launch: launchOf })
  console.log('R3 observed:', JSON.stringify(result))
  assert.equal(result.how, 'live')
})
test('R4: a navigation that has only begun is not a departure', () => {
  clearLaunches(); const l = launch(); let moved = false
  const now = { current: { goToPost: () => { moved = false } } }
  const result = openResultTarget({ ...dest(), target: { kind: 'post', conversation: 'ent-333333333333', post: 'ent-444444444444' }, opens: 'post' }, l,
    { brainKey: brain, origin: 'https://mentis.test', post: (c, p) => { now.current.goToPost(c, p); return true } })
  console.log('R4 observed:', JSON.stringify({ moved, result, leaves: leaves(result) }))
  assert.equal(leaves(result), false)
})
