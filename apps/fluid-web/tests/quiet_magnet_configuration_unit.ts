/** Part B: source-free identity and practical configuration.
 *
 *  Proves what the owner asked for in request ent-3191baeb33d2 §4, at the seams
 *  this part owns: a Magnet exists without configured sources, the last source
 *  can be removed, its name is its own and travels with its definition rather
 *  than with where it is drawn, Collect with nothing configured is a stated
 *  no-op and never a wider read, and the bounds, repeats and unsupported kinds
 *  are all still told the truth about. */
import assert from 'node:assert/strict'
import { test } from 'node:test'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import CollectionConfiguration from '../src/quiet2/magnets/CollectionConfiguration'
import {
  collectionChange, collectionIssue, configurationFacts, findHoldingArrangement, identityChange,
  magnetName, MAGNET_NAME_MOST, nameIssue, NO_SOURCE_TO_COLLECT, sourceIdentity,
} from '../src/quiet2/magnets/configuration'
import { createMagnetResource } from '../src/quiet2/magnets/state'
import { unsupportedMagnet } from '../src/quiet2/magnets/read'
import { forgetPanelDrafts } from '../src/quiet2/magnets/panelDrafts'
import { page as binding } from '../src/brainBinding'
import type { MagnetConfig, MagnetSource } from '../src/fluid/surface/magnet/types'

const SOURCE = 'ent-source111111'
const HELD: MagnetSource = { kind: 'file', collection: 'col-held', path: 'notes/a.txt' }
const brainKey = 'origin|fixture|brain-partb'
const store = () => {
  const mem = new Map<string, string>()
  Object.defineProperty(globalThis, 'localStorage', { configurable: true, value: {
    getItem: (k: string) => mem.get(k) ?? null, setItem: (k: string, v: string) => mem.set(k, v),
    removeItem: (k: string) => mem.delete(k), clear: () => mem.clear() } })
  binding.saw('brain-partb@instance-one')
  forgetPanelDrafts()
}
const config = (change: Partial<MagnetConfig> = {}): MagnetConfig => ({
  id: 'mag-partb', sources: [], selection: {}, collection: { mode: 'one-time' },
  synthesis: { mode: 'manual' }, activation: { mode: 'manual' },
  processing: { operations: [{ op: 'extract' }] },
  notifications: { newItems: false, changes: false, failures: false },
  presentation: { renderer: 'disc' }, ...change,
})

test('a Magnet with no configured source is readable, openable and conversable', () => {
  store()
  const saved = config()
  assert.equal(unsupportedMagnet(saved, 'mag-partb'), undefined, 'none is not a broken definition')
  const r = createMagnetResource({
    id: 'qm-partb', brainKey, saved: { id: 'mag-partb', name: 'An idea', config: saved },
    get: async () => ({ status: 200, body: { magnet: 'mag-partb', config: saved, activation: null, page: null } }),
  })
  assert.equal(r.saved.config!.sources.length, 0)
  // Twenty-one is still refused, and so is a definition that names no list at all.
  const many = Array.from({ length: 21 }, (_, i) => ({ kind: 'conversation' as const, conversation: `ent-many${i}` }))
  assert.match(unsupportedMagnet(config({ sources: many }), 'mag-partb')!, /up to 20/)
  assert.match(unsupportedMagnet({ ...config(), sources: undefined }, 'mag-partb')!, /up to 20/)
})

test('Collect with nothing configured says so and sends no request', async () => {
  store()
  const saved = config()
  const asked: string[] = []
  const r = createMagnetResource({
    id: 'qm-partb-collect', brainKey, saved: { id: 'mag-partb', name: 'An idea', config: saved },
    get: async (path) => { asked.push(path); return { status: 200, body: { magnet: 'mag-partb', config: saved, activation: null, page: null } } },
  })
  await r.collect!()
  assert.equal(r.snapshot().collectionMessage, NO_SOURCE_TO_COLLECT)
  assert.ok(!r.snapshot().collecting, 'nothing was ever started, so nothing has to finish')
  assert.deepEqual(asked, [], 'nothing was asked of the server, so nothing was read in their place')
  assert.match(NO_SOURCE_TO_COLLECT, /nothing else is read in their place/)
})

test('the last source can be removed, and up to 20 chosen, through one change', () => {
  const before = config({ sources: [{ kind: 'conversation', conversation: SOURCE }, HELD] })
  // Removing the last source is an ordinary change, not a refusal.
  assert.equal(collectionIssue({ sources: [], types: [], after: '', before: '', manual: false }), null)
  const emptied = collectionChange(before, [], [], '', '', false)
  assert.deepEqual(emptied.sources, [])
  assert.deepEqual(emptied.selection.informationTypes, [])
  // A Conversation source still needs a content type; a held file alone does not.
  assert.throws(() => collectionChange(before, [{ kind: 'conversation', conversation: SOURCE }], [], '', '', false), /information types/)
  assert.deepEqual(collectionChange(before, [HELD], [], '', '', false).sources, [HELD])
  // The bound, repeats and unsupported kinds are unchanged.
  const many = Array.from({ length: 21 }, (_, i) => ({ kind: 'conversation' as const, conversation: `ent-many${i}` }))
  assert.throws(() => collectionChange(before, many, ['post'], '', '', false), /up to 20/)
  assert.throws(() => collectionChange(before, [HELD, { ...HELD }], ['post'], '', '', false), /once/)
  assert.throws(() => collectionChange(before, [{ kind: 'web', url: 'https://example.org/' }], ['post'], '', '', false), /unavailable in this milestone/)
  assert.equal(sourceIdentity(HELD), 'file:col-held:notes/a.txt')
})

test('a Magnet is named in its own definition, independently of where it is shown', () => {
  assert.equal(magnetName(config(), 'Field notes (Magnet)'), 'Field notes (Magnet)', 'with none of its own, what the catalogue worked out stands')
  assert.equal(magnetName(config({ identity: { name: '  Tide study  ' } }), 'Field notes (Magnet)'), 'Tide study')
  assert.deepEqual(identityChange('  Tide study  '), { identity: { name: 'Tide study' } })
  assert.equal(nameIssue('Tide study'), null)
  assert.equal(nameIssue('   '), 'Give the Magnet a name, or leave the saved name as it is.')
  assert.match(nameIssue('x'.repeat(MAGNET_NAME_MOST + 1))!, /at most 80/)
  assert.match(nameIssue('two\nlines')!, /control characters/)
  // The facts the settings index reads say which of the two it is.
  assert.match(configurationFacts(config({ identity: { name: 'Tide study' } }))[0], /^Name: Tide study \(this Magnet's own/)
  assert.match(configurationFacts(config())[0], /taken from where it is shown/)
  assert.match(configurationFacts(config())[1], /^Configured sources: none yet/)
})

test('the saved location a configuration is sent through is found, not asked for', async () => {
  const seen: string[] = []
  const holder = 'ent-workspace11'
  globalThis.fetch = (async (path: string) => {
    seen.push(String(path))
    const held = String(path).includes(holder)
    return new Response(JSON.stringify({ layout: { format: 'mentis.fluid-arrangement', version: 3, magnets: held ? { 'mag-partb': config() } : {} } }),
      { status: 200, headers: { 'Content-Type': 'application/json' } })
  }) as typeof fetch
  assert.equal(await findHoldingArrangement('mag-partb', ['home', holder]), holder)
  assert.deepEqual(seen.map((p) => p.split('/').pop()), ['home', holder], 'Brain Home first, then each saved workspace, stopping at the first that holds it')
  assert.equal(await findHoldingArrangement('mag-partb', ['home']), null, 'a Magnet no saved location holds is said, not guessed')
})

test('the panel opens on the name and the sources, and says what no source means', () => {
  store()
  const html = renderToStaticMarkup(createElement(CollectionConfiguration, {
    magnet: 'mag-partb', config: config(), brainKey, canWrite: () => true, onSaved: () => {},
  }))
  assert.ok(html.indexOf('>Name') < html.indexOf('>Sources<'), 'the name comes first')
  assert.ok(html.includes('does not change where it is shown'))
  assert.ok(html.includes(NO_SOURCE_TO_COLLECT), 'the empty state says what it means for Collect')
  assert.ok(html.includes('Add Conversations') && html.includes('Add held text files'))
  assert.ok(html.includes('Save collection configuration'))
  // Which saved location the save goes through is disclosed, not demanded.
  assert.ok(html.includes('Where this configuration is saved through'))
  assert.ok(!html.includes('Location containing this Magnet'))
  const withSources = renderToStaticMarkup(createElement(CollectionConfiguration, {
    magnet: 'mag-partb', config: config({ sources: [HELD], identity: { name: 'Tide study' } }), brainKey, canWrite: () => true, onSaved: () => {},
  }))
  assert.ok(withSources.includes('1 of 20 sources chosen'))
  assert.ok(withSources.includes('value="Tide study"'))
  assert.ok(!withSources.includes(NO_SOURCE_TO_COLLECT))
})
