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
/** THE SOURCES RAIL IS NOT A SEPARATE VIEW ANY MORE (owner ent-24beca915507):
 *  the Collection place is one split surface and the rail is always part of it,
 *  so what used to be reached by writing `sources: true` is simply the same
 *  render. The flag still exists and the shell's own entry still writes it --
 *  it means "take me to the rail" now -- and writing it must not change what
 *  the surface holds. */
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

test('Collection is ONE split surface: the place heading, then sources and filters, then the collected results', async () => {
  store()
  const r = resource()
  await r.read()
  const html = browse(r)
  // The document order IS the stacking order (owner ent-24beca915507: "let
  // them stack responsively at narrow widths"): the heading, then what is
  // being looked at, then what was found. `collection.css` places the two
  // columns side by side at a width that holds both; it never reorders the
  // document to do it.
  order(html, [
    'q2-magnet-collection-split',
    'mgd-eyebrow', 'Collection',
    'mgd-h2', 'Collected items', '<span class="mgd-subtle"> 1</span>',
    'q2-magnet-collection-rail',
    'Search collected items',
    'mgd-pill', 'Everything', 'Posts', 'Files', 'Images',
    '>Sources</h3>',
    'mgd-source', 'Remove',
    'mgd-button mgd-secondary', '＋ Add source',
    'What to collect', 'Posts, files, images and attachments', 'Change',
    'Collect manually', 'Collect now',
    'Limits and dates ▾',
    'q2-magnet-collection-main',
    'q2-magnet-evidence-row',
    'Collected ',
  ])
  // The type filters are the ones the places model already had; the selected
  // one carries the design's own active state.
  assert.ok(html.includes('class="mgd-pill mgd-active"'), 'the showing filter is the active pill')
  // FOUR, AS THE MOCKUP SHOWS. `04-browse.png` shows All / Posts / Files /
  // Images; Part 4 gave the lens state and the place keys behind it the
  // fourth filter (`places.ts` `MAGNET_COLLECTION_TABS`, `contract.ts`
  // `MAGNET_TABS`), closing the seam this file used to report
  // (`opr-937e911eadcd`). One pill per filter, and no second filter row.
  assert.equal((html.match(/mgd-pill/g) ?? []).length, 4, 'one pill per filter that exists, and no second filter row')
  // NOTHING IS SAID TWICE ACROSS THE TWO COLUMNS. The links the two surfaces
  // used to carry to each other pointed at the column beside them and are
  // gone; collecting is offered once, on the rail's own row, which is where
  // the cadence is said.
  assert.equal((html.match(/Sources ·/g) ?? []).length, 0, 'no link to the column that is already on screen')
  assert.equal((html.match(/Collected items →/g) ?? []).length, 0, 'and none back the other way')
  assert.equal((html.match(/Collect now/g) ?? []).length, 1, 'collecting is offered once on this surface')
  assert.equal((html.match(/id="view-title"/g) ?? []).length, 1, 'one heading, over both columns')
  assert.equal((html.match(/Search collected items/g) ?? []).length, 2, 'one search box: its label and its placeholder')
  saysNothingRemoved(html, 'Collection')
})

test('the place’s own Sources flag takes the reader to the rail, and changes nothing on the surface', async () => {
  store()
  const r = resource()
  await r.read()
  assert.equal(sourcesView(r), browse(r),
    'both columns are on screen either way: the flag is a destination, not a second view')
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

test('the Sources rail keeps the approved body, in the approved order and nothing else', () => {
  store()
  const html = sourcesView(resource())
  order(html, [
    '>Sources</h3>',
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
  // The rail contributes no second heading of the place's: the split surface
  // says where the reader is once.
  assert.ok(!html.includes('>Sources</h2>'), 'the rail is a section of the Collection place, not a view of its own')
  saysNothingRemoved(html, 'Sources')
})

test('a source row never titles itself from a raw storage key', () => {
  store()
  const held = config()
  // How a held web page or feed entry is stored: the path IS the key it was
  // written under. The owner read source rows headed
  // "www-nasa-gov/0033172620276ee1" (ent-24beca915507: ids and raw collection
  // mechanics stay secondary, never the name of a thing).
  held.sources = [{ kind: 'file', collection: 'col-held', path: 'www-nasa-gov/0033172620276ee1' },
    { kind: 'file', collection: 'col-held', path: 'nested/notes.txt' }]
  const r = createMagnetResource({ id: 'qm-keys', brainKey, saved: { id: 'mag-design', name: 'Deployment learning', config: held },
    get: async () => ({ status: 200, body: { magnet: 'mag-design', config: held, activation: null, page: null } }) })
  const html = renderToStaticMarkup(createElement(EvidenceViews, { resource: r, lens: 'All', onPost: () => {}, onFile: () => {}, canWrite: may }))
  assert.ok(!html.includes('<b>www-nasa-gov/0033172620276ee1</b>'), 'the storage key is not the row’s name')
  assert.ok(html.includes('One held item of this collection'), 'the row says what it is instead')
  // A real filename is still exactly what it was.
  assert.ok(html.includes('<b>nested/notes.txt</b>'), 'a path a reader recognises is kept as it is')
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
