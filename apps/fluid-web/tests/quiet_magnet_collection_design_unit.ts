/** PART B: COLLECTION, REBUILT TO THE APPROVED ROUND-3 DESIGN.
 *
 *  The owner's judgement was that the Magnet still read as the administrative
 *  forms it began as, and another restyle of those forms was ruled out
 *  (ent-a24ec84c8176). `magnet-design-round3/03-sources.png` and `04-browse.png`
 *  are the specification; this file pins what they show, in the order they show
 *  it, and pins that what they replaced is no longer said anywhere on these two
 *  surfaces.
 *
 *  It is a presentation test on purpose. What is NOT presentation -- the staged
 *  copy, `collectionChange`, `saveCollection`, the `canWrite` gate and
 *  `resource.collect()` -- is unchanged behind it, and is pinned where it
 *  already was (`quiet_magnet_configuration_unit.ts`,
 *  `quiet_magnet_collection_authority_unit.ts`, `quiet_magnet_part_b_unit.ts`).
 *  The two assertions here that are about authority rather than appearance --
 *  that neither Collect now nor Save is offered where the supplied capability
 *  refuses it -- are kept because the design moved both controls. */
import assert from 'node:assert/strict'
import { test } from 'node:test'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import EvidenceViews from '../src/quiet2/magnets/EvidenceViews'
import CollectionConfiguration, { whatIsCollected } from '../src/quiet2/magnets/CollectionConfiguration'
import { createMagnetResource } from '../src/quiet2/magnets/state'
import { goTab, writePlace } from '../src/quiet2/magnets/places'
import { forgetPanelDrafts, stageSettings } from '../src/quiet2/magnets/panelDrafts'
import { page as binding } from '../src/brainBinding'
import type { MagnetConfig } from '../src/fluid/surface/magnet/types'

const SOURCE = 'ent-source111111'
const brainKey = 'origin|fixture|brain-design'
const digest = 'a'.repeat(64)

const store = () => {
  const mem = new Map<string, string>()
  Object.defineProperty(globalThis, 'localStorage', { configurable: true, value: {
    getItem: (k: string) => mem.get(k) ?? null, setItem: (k: string, v: string) => mem.set(k, v),
    removeItem: (k: string) => mem.delete(k), clear: () => mem.clear() } })
  binding.saw('brain-design@instance-one')
  forgetPanelDrafts()
}

const config = (): MagnetConfig => ({ id: 'mag-design',
  sources: [{ kind: 'conversation', conversation: SOURCE }, { kind: 'file', collection: 'col-held', path: 'nested/notes.txt' }],
  selection: { informationTypes: ['post', 'file', 'image', 'attachment'], dates: {} },
  collection: { mode: 'one-time' }, synthesis: { mode: 'manual' }, activation: { mode: 'manual' },
  processing: { operations: [{ op: 'extract' }] },
  notifications: { newItems: false, changes: false, failures: false }, presentation: { renderer: 'disc' } })

const POST = { kind: 'post', id: 'ent-post111111', number: 12, version: 'ent-version111111', conversation: SOURCE,
  author: 'Alex', via: 'home', at: 1764000300, value: { parts: [{ type: 'text', text: 'We had to wait for the release tool again.' }] } }
const ACTIVATION = { post: 'ent-activation111', artifact: { ref: 'adm-batch111111', digest, size: 2048, media_type: 'application/json' }, at: 1764000500, state: 'recorded' }
const page = (c: MagnetConfig) => ({ sources: [
  { source: c.sources[0], key: `conversation:${SOURCE}`, status: 'ok', results: [POST] },
  { source: c.sources[1], key: 'file:col-held:nested/notes.txt', status: 'ok', results: [] },
] })

function resource() {
  const c = config()
  return createMagnetResource({ id: 'qm-design', brainKey, saved: { id: 'mag-design', name: 'Deployment learning', config: c },
    get: async () => ({ status: 200, body: { magnet: 'mag-design', config: c, activation: ACTIVATION, page: page(c) } }) })
}
const may = (key: string) => key === 'home'
const browse = (r: ReturnType<typeof resource>, canWrite = may) =>
  renderToStaticMarkup(createElement(EvidenceViews, { resource: r, lens: 'All', onPost: () => {}, onFile: () => {}, canWrite }))
const sourcesView = (r: ReturnType<typeof resource>, canWrite = may) => {
  goTab(r, 'All'); writePlace(r, 'All', { sources: true })
  return renderToStaticMarkup(createElement(EvidenceViews, { resource: r, lens: 'All', onPost: () => {}, onFile: () => {}, canWrite }))
}

/** The order the mockup puts things in, checked as positions in the markup
 *  rather than as a fixed string: what is pinned is the sequence the approved
 *  picture shows, not one build's attribute spelling. */
const order = (html: string, parts: string[]) => {
  let last = -1
  for (const part of parts) {
    const at = html.indexOf(part, last + 1)
    assert.ok(at >= 0, `the approved surface says "${part}", after what the mockup puts before it`)
    last = at
  }
}

/** Everything the owner asked to be gone from these two surfaces. None of it
 *  may come back on either one, in any state. */
const GONE = [
  'of 20 sources chosen',
  'Add a source',
  'Add Conversations',
  'Add files',
  'Where this configuration is saved through',
  'Save collection configuration',
  'Cancel configuration edits',
  'No folder is scanned or refreshed',
  'Unsaved changes. Save or cancel.',
]
const saysNothingRemoved = (html: string, where: string) => {
  for (const words of GONE) assert.ok(!html.includes(words), `${where} no longer says "${words}"`)
}

/* -- Collected items (04-browse.png) ---------------------------------------- */

test('Collected items is the approved surface, in the approved order and nothing else', async () => {
  store()
  const r = resource()
  await r.read()
  const html = browse(r)
  order(html, [
    'mgd-eyebrow', 'Collection',
    'mgd-h2', 'Collected items', '<span class="mgd-subtle"> 1</span>',
    'Sources · 2 →',
    'Search collected items',
    'mgd-pill', 'All', 'Posts', 'Files',
    'q2-magnet-evidence-row',
    'Collected ',
  ])
  // The type filters are the ones the places model already had; the selected
  // one carries the design's own active state.
  assert.ok(html.includes('class="mgd-pill mgd-active"'), 'the showing filter is the active pill')
  // THREE, NOT THE MOCKUP'S FOUR. `04-browse.png` shows All / Posts / Files /
  // Images; the lens state this draws has three filters
  // (`places.ts` `MAGNET_COLLECTION_TABS`, `contract.ts` `MAGNET_TABS`), and
  // those files are not this part's to change. One pill per filter that exists
  // -- never a fourth pill with nothing behind it. Reported as a seam.
  assert.equal((html.match(/mgd-pill/g) ?? []).length, 3, 'one pill per filter that exists, and no second filter row')
  // Said once: the counterpart link is on the heading row, not floating above
  // it as well.
  assert.equal((html.match(/Sources ·/g) ?? []).length, 1)
  assert.equal((html.match(/Collect now/g) ?? []).length, 1, 'collecting is offered once on this surface')
  saysNothingRemoved(html, 'Collected items')
})

test('an unread collection states no count beside its heading, and fabricates none', () => {
  store()
  const html = browse(resource())
  assert.ok(html.includes('Collected items</h2>'), 'the heading stands alone until a read has returned')
  assert.ok(!/Collected items<span/.test(html))
})

test('Collect now on the browse line is refused where the supplied capability refuses it', async () => {
  store()
  const r = resource()
  await r.read()
  const offered = browse(r).match(/<button[^>]*>Collect now<\/button>/)![0]
  assert.ok(!offered.includes('disabled'), 'an authorised collection is offered')
  const refused = browse(r, () => false).match(/<button[^>]*>Collect now<\/button>/)![0]
  assert.ok(refused.includes('disabled=""'), 'a write the gate refuses is not offered')
})

/* -- Sources (03-sources.png) ------------------------------------------------ */

test('Sources is the approved surface, in the approved order and nothing else', () => {
  store()
  const html = sourcesView(resource())
  order(html, [
    'mgd-eyebrow', 'Collection',
    'mgd-h2', '>Sources</h2>',
    'Collected items →',
    'Choose where to look. Collect when you’re ready.',
    'mgd-source', 'Remove',
    'mgd-button mgd-secondary', '＋ Add source',
    'mgd-divider',
    'What to collect', 'Posts, files, images and attachments', 'Change',
    'mgd-divider',
    'Collect manually', 'Collect now',
    'Limits and dates ▾',
  ])
  assert.equal((html.match(/mgd-source/g) ?? []).length, 3, 'one ruled row per source, and one for Add source')
  assert.equal((html.match(/>Remove</g) ?? []).length, 2, 'each configured source carries its own Remove')
  saysNothingRemoved(html, 'Sources')
})

test('the configuration moved behind Change rather than being deleted', () => {
  store()
  const html = sourcesView(resource())
  // At rest: the current selection as a sentence, and no form.
  assert.ok(!html.includes('type="checkbox"'), 'the checkbox form is not standing on the surface')
  assert.ok(html.includes('aria-expanded="false"'), 'Change, Add source and Limits are closed disclosures')
  assert.equal(whatIsCollected(['post', 'file', 'image', 'attachment'], '', ''), 'Posts, files, images and attachments')
  assert.equal(whatIsCollected(['post'], '2026-01-01', ''), 'Posts · 2026-01-01 to any end')
  assert.equal(whatIsCollected([], '', ''), 'Nothing selected')
})

test('the commit appears only once something is unsaved, and never offers a write the gate refuses', () => {
  store()
  const r = resource()
  assert.ok(!sourcesView(r).includes('Unsaved changes'), 'looking at Sources announces nothing')
  // An actual edit -- staged exactly as the panel stages its own.
  stageSettings({ brainKey, magnet: 'mag-design' },
    { sources: [], types: ['post'], after: '', before: '', manual: false })
  const edited = sourcesView(r)
  assert.ok(edited.includes('Unsaved changes'), 'an edit that is not saved says so, where it was made')
  const save = edited.match(/<button[^>]*aria-label="Save collection configuration"[^>]*>/)![0]
  assert.ok(save.includes('disabled=""'),
    'the save is gated on the resolved saved location and the supplied capability, exactly as before')
  forgetPanelDrafts()
})
