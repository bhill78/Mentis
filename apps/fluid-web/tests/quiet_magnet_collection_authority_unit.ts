/** THE EMBEDDED SOURCES AUTHORITY SEAM (Caretaker request ent-d9afe6fc6027).
 *
 *  Collection's own inline Sources view (`EvidenceViews.tsx`) used to hand its
 *  embedded `CollectionConfiguration` a permissive `canWrite={() => true}`
 *  stub instead of Host's own `writes.arrangement`-derived gate -- a save a
 *  reader may not actually make looked offered from inside Collection, where
 *  Settings' own copy of the same panel correctly refused it. This checks
 *  that the real capability now reaches the embedded panel unchanged, and
 *  that it fails closed -- refuses, not permits -- when none is supplied.
 *
 *  `CollectionConfiguration` resolves its own saved location only through an
 *  effect (`findConfigurationLocation`), which a static render never runs, so
 *  its own `Save` gating is exercised separately
 *  (`quiet_magnet_configuration_unit.ts`). This file checks the seam one
 *  level up: the exact `canWrite` `EvidenceViews` constructs and hands down,
 *  with a probe standing in for the real panel (substituted by this file's
 *  own `.mjs` loader) so what is authorised is observable without a browser
 *  and without waiting on that effect.
 *
 *  It also checks the second half of the same request: the shell's own
 *  "Sources" entry (`Magnet.tsx`'s filter-bar link, `showSourcesInline`) and
 *  Collection's inline toggle now disclose through the one place-state flag
 *  (`contract.ts` `MagnetPlace.sources`), so the shell's entry actually opens
 *  the approved inline view instead of the Settings overlay. */
import assert from 'node:assert/strict'
import { test } from 'node:test'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import EvidenceViews from '../src/quiet2/magnets/EvidenceViews'
import { createMagnetResource } from '../src/quiet2/magnets/state'
import { goTab, place, showSourcesInline, writePlace } from '../src/quiet2/magnets/places'
import { page as binding } from '../src/brainBinding'
import type { MagnetConfig } from '../src/fluid/surface/magnet/types'

const brainKey = 'origin|fixture|brain-authority'
const store = () => {
  const mem = new Map<string, string>()
  Object.defineProperty(globalThis, 'localStorage', { configurable: true, value: {
    getItem: (k: string) => mem.get(k) ?? null, setItem: (k: string, v: string) => mem.set(k, v),
    removeItem: (k: string) => mem.delete(k), clear: () => mem.clear() } })
  binding.saw('brain-authority@instance-one')
}
const config: MagnetConfig = {
  id: 'mag-authority', sources: [{ kind: 'conversation', conversation: 'ent-source111111' }], selection: {},
  collection: { mode: 'one-time' }, synthesis: { mode: 'manual' }, activation: { mode: 'manual' },
  processing: { operations: [{ op: 'extract' }] },
  notifications: { newItems: false, changes: false, failures: false },
  presentation: { renderer: 'disc' },
}
const magnetResource = () => createMagnetResource({
  id: 'qm-authority', brainKey, saved: { id: 'mag-authority', name: 'Authority check', config },
  get: async () => ({ status: 200, body: { magnet: 'mag-authority', config, activation: null, page: null } }),
})
const probe = (globalThis as { __ccProbe__?: { calls: { canWrite(key: string): boolean }[] } }).__ccProbe__!
const render = (r: ReturnType<typeof magnetResource>, canWrite?: (key: string) => boolean) =>
  renderToStaticMarkup(createElement(EvidenceViews, { resource: r, lens: 'All', onPost: () => {}, onFile: () => {}, canWrite }))
/** The probe's one rendered button, whichever order its attributes land in. */
const saveButton = (html: string): string => html.match(/<button[^>]*data-probe-save=""[^>]*>[^<]*<\/button>/)?.[0] ?? ''
const refused = (html: string) => { const b = saveButton(html); return b !== '' && b.includes('disabled=""') }
/** The place `EvidenceViews` reads is keyed by the resource's current tab, not
 *  by the `lens` prop alone -- Host only ever mounts the one instance that
 *  matches `s.tab`, so a test has to put the resource on `All` the same way. */
const showingSources = (r: ReturnType<typeof magnetResource>) => { goTab(r, 'All'); writePlace(r, 'All', { sources: true }) }

let checks = 0
const ok = (a: unknown, what: string) => { assert.ok(a, what); checks++ }
const eq = (a: unknown, b: unknown, what: string) => { assert.equal(a, b, what); checks++ }

test('with no canWrite supplied, the embedded panel fails closed', () => {
  store()
  probe.calls.length = 0
  const r = magnetResource()
  showingSources(r)
  const html = render(r)
  eq(probe.calls.length, 1, 'the embedded panel rendered once')
  eq(probe.calls[0].canWrite('home'), false, 'with nothing authorised, nothing is writable')
  eq(probe.calls[0].canWrite('any-other-arrangement'), false, 'the default refuses every arrangement, not just one')
  ok(refused(html), 'the save affordance itself is refused, not merely unauthorised underneath')
})

test('the real arrangement capability Host supplies reaches the embedded panel unchanged, and authorises', () => {
  store()
  probe.calls.length = 0
  const writesArrangement = (key: string) => key === 'home'
  const r = magnetResource()
  showingSources(r)
  const html = render(r, writesArrangement)
  eq(probe.calls[0].canWrite, writesArrangement, 'the exact function Host would supply is handed down, not a rewritten copy')
  eq(probe.calls[0].canWrite('home'), true, 'an arrangement the real gate authorises is writable here too')
  ok(!refused(html), 'an authorised save is actually offered')
})

test('a real refusal from the supplied capability still disables the save, not only the omitted-prop default', () => {
  store()
  probe.calls.length = 0
  const r = magnetResource()
  showingSources(r)
  const html = render(r, () => false)
  eq(probe.calls[0].canWrite('home'), false, 'the supplied gate refuses this arrangement')
  ok(refused(html), 'the embedded save is refused exactly as Settings’ own copy would refuse it')
})

/** THE SPLIT COLLECTION SURFACE (owner ent-24beca915507) changed what the flag
 *  MEANS, not where authority goes. Sources is a column of the Collection place
 *  now, always on screen beside the collected items, so the flag is a
 *  destination ("take me to the rail") rather than a switch between two views.
 *  What this file exists to pin is unchanged: ONE embedded panel, handed the
 *  exact capability Host supplies, failing closed when none is. */
test('the shell’s "Sources" entry lands on the Collection place and still writes the one place flag', () => {
  store()
  const r = magnetResource()
  eq(place(r.snapshot()).sources, false, 'closed by default')
  showSourcesInline(r)
  eq(r.snapshot().tab, 'All', 'the shell entry lands on the Collection place the rail lives in')
  eq(place(r.snapshot()).sources, true, 'and writes the same flag the shell and the rail share')
  probe.calls.length = 0
  render(r)
  eq(probe.calls.length, 1, 'one embedded panel, never a second overlay copy')
  // Flag or no flag, the split surface holds both columns: one panel, and the
  // collected items beside it.
  writePlace(r, 'All', { sources: false })
  probe.calls.length = 0
  const html = render(r)
  eq(probe.calls.length, 1, 'the rail is part of the surface, not something the flag turns on')
  ok(html.includes('view-title'), 'and the collected items are on it too, under the place’s one heading')
})
