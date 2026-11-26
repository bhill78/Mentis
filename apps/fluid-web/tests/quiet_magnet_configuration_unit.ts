/** Part B: source-free identity and practical configuration.
 *
 *  Proves what the owner asked for in request ent-3191baeb33d2 §4, at the seams
 *  this part owns: a Magnet exists without configured sources, the last source
 *  can be removed, its name is its own and travels with its definition rather
 *  than with where it is drawn, Collect with nothing configured is a stated
 *  no-op and never a wider read, and the bounds, repeats and unsupported kinds
 *  are all still told the truth about. */
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { test } from 'node:test'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import CollectionConfiguration from '../src/quiet2/magnets/CollectionConfiguration'
import {
  canonicalDefinition, collectionChange, collectionIssue, collectionRhythm, configurationDigest, configurationFacts,
  dayOf, durableDefinition, findConfigurationLocation, findHoldingArrangement, identityChange, magnetName,
  MAGNET_NAME_MOST, nameIssue, NO_SAVED_PLACE, NO_SOURCE_TO_COLLECT, PROPOSED_REASON, PROPOSED_SOURCES,
  savedPlace, saveCollection, sourceIdentity, SUPPORTED_REASON, SUPPORTED_SOURCES, withDay,
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

/** PART C: WHAT THE "NO ADAPTER" LIST MAY STILL SAY.
 *
 *  A `file` source now reads one exact path, everything under a path prefix, or
 *  a whole acquired collection, and a Git repository collection reads the same
 *  way -- its tree and its recent commits are rows alike
 *  (`mentis/magnet/activation.py` `file_choice`,
 *  `crates/mentis-ops/src/magnet/collection_files.rs`). So "Repositories" has
 *  left the proposed list, because it works; nothing else has, because nothing
 *  else does yet. Web pages and Web searches stay listed until Part W's
 *  connectors land, and the Magnet kinds that nothing reads -- Topics,
 *  Databases, Connected services -- stay listed with their reason unchanged. */
test('the no-adapter list has lost exactly what now works, and kept the rest', () => {
  const proposed: string[] = PROPOSED_SOURCES.map((s) => s.words)
  assert.ok(!proposed.includes('Repositories'), 'a Git repository collection is read by a file source now')
  assert.deepEqual(proposed, ['Topics', 'Web pages', 'Web searches', 'Databases', 'Connected services'],
    'nothing else was lifted: Part W owns the two web entries and tells this file when they move')
  // The reason the remaining entries carry is unchanged: it is the server's own.
  assert.match(PROPOSED_REASON, /^Proposed only, and not interactive here/)
  assert.match(PROPOSED_REASON, /this build has no adapter for them/)
  // The supported list says the three things a file source may now name, and
  // still says that opening, saving and collecting never scan a folder.
  const file = SUPPORTED_SOURCES.find((s) => s.kind === 'file')!
  for (const said of ['one exact path', 'path prefix', 'the whole collection', 'Git repository']) {
    assert.ok(file.words.includes(said), `the supported wording says "${said}": ${file.words}`)
  }
  assert.ok(!SUPPORTED_SOURCES.some((s) => /one exact path at a time/.test(s.words)),
    'the exact-file-only wording is gone, not merely reworded around')
  assert.match(SUPPORTED_REASON, /No folder is scanned or refreshed/)
  // Each kind the proposed list names is one the Magnet schema has, and none of
  // them is a kind the supported list claims.
  const supported = new Set(SUPPORTED_SOURCES.map((s) => s.kind as string))
  for (const s of PROPOSED_SOURCES) {
    assert.ok(['brain', 'web', 'database', 'other', 'connector'].includes(s.kind), s.kind)
    assert.ok(!supported.has(s.kind), `${s.kind} cannot be both supported and proposed`)
  }
})

/** The configured-source line and the identity of a collection-scoped source.
 *  `sourceIdentity` is what the panel lists and what `collectionChange` refuses
 *  twice over, so a whole-collection source and an exact one under it are two
 *  different sources and both may be configured. */
test('a collection-scoped file source has an identity of its own', () => {
  const whole: MagnetSource = { kind: 'file', collection: 'col-held' }
  const prefix: MagnetSource = { kind: 'file', collection: 'col-held', path: 'notes/' }
  assert.equal(sourceIdentity(whole), 'file:col-held:')
  assert.equal(sourceIdentity(prefix), 'file:col-held:notes/')
  assert.notEqual(sourceIdentity(whole), sourceIdentity(prefix))
  assert.notEqual(sourceIdentity(prefix), sourceIdentity(HELD))
  assert.match(configurationFacts(config({ sources: [whole, HELD] }))[1],
    /^Configured sources: file:col-held: · file:col-held:notes\/a\.txt$/)
})

/** THE CANONICAL FORM AND DIGEST, against the one file both halves are held to
 *  (revised contract adm-c5c73679ac1e §3). Python's half is checked against the
 *  same vectors in `tests/test_magnet_snapshot.py`; neither generates them. */
const VECTORS = JSON.parse(readFileSync(new URL('../../../tests/fixtures/magnet-definition-digest/vectors.json', import.meta.url), 'utf8')) as {
  vectors: { name: string; definition: MagnetConfig; canonical: string; digest: string }[]
  refused: { name: string; definition: MagnetConfig; because: string }[]
}

test('the canonical definition and its digest are the same bytes in both halves', async () => {
  assert.ok(VECTORS.vectors.length >= 9 && VECTORS.refused.length >= 1)
  for (const v of VECTORS.vectors) {
    assert.equal(canonicalDefinition(v.definition), v.canonical, v.name)
    assert.equal(await configurationDigest(v.definition), v.digest, v.name)
    assert.match(v.digest, /^[0-9a-f]{64}$/)
  }
  for (const r of VECTORS.refused) assert.throws(() => canonicalDefinition(r.definition), new RegExp(r.because), r.name)
  // The whole durable definition, and not the mirror: the two vectors that
  // differ only by `conversation` and `schema_version` share one digest.
  const named = VECTORS.vectors.find((v) => v.name === 'source-free, named in its own definition')!
  const mirrored = VECTORS.vectors.find((v) => v.name.startsWith('the own-Conversation mirror'))!
  assert.equal(mirrored.digest, named.digest)
  assert.ok('conversation' in (mirrored.definition as object) && !('conversation' in durableDefinition(mirrored.definition)))
  assert.ok(!('schema_version' in durableDefinition(mirrored.definition)))
  // Every facet moves it, and a source-free definition is digested like any other.
  const base = config()
  assert.notEqual(canonicalDefinition(base), canonicalDefinition(config({ identity: { name: 'Tide study' } })))
  assert.notEqual(canonicalDefinition(base), canonicalDefinition(config({ sources: [HELD] })))
  assert.ok(canonicalDefinition(base).includes('"sources":[]'))
  // Canonical: sorted keys, no whitespace, and still the same definition.
  const body = canonicalDefinition(base)
  const keys = Object.keys(JSON.parse(body) as object)
  assert.deepEqual(keys, [...keys].sort(), 'object keys are sorted')
  assert.ok(!/\s|: |, /.test(body))
  assert.deepEqual(JSON.parse(body), durableDefinition(base))
})

test('a Magnet nothing holds is still configured through a saved location', async () => {
  // Owner request §4: identity and configuration do not depend on where a
  // Magnet is displayed -- including nowhere. The save is addressed through a
  // saved location, which need not hold it and gains nothing by carrying it.
  store()
  const asked: { path: string; body?: string }[] = []
  const holder = 'ent-workspace11'
  globalThis.fetch = (async (path: string, init?: RequestInit) => {
    asked.push({ path: String(path), body: typeof init?.body === 'string' ? init.body : undefined })
    const at = String(path)
    if (at.includes('needs-you/brain')) return new Response(JSON.stringify({ brain: { corpus_id: 'brain-partb', instance: 'instance-one' } }), { status: 200 })
    if (at.endsWith('/reconfigure')) return new Response(JSON.stringify({ magnet: config({ identity: { name: 'An idea' } }) }), { status: 200 })
    // Brain Home is saved and holds nothing; the workspace keeps nothing at all.
    if (at.endsWith('/home')) return new Response(JSON.stringify({ layout: { format: 'mentis.fluid-arrangement', version: 3 } }), { status: 200 })
    return new Response(JSON.stringify({ layout: null }), { status: 200 })
  }) as typeof fetch

  assert.deepEqual(await savedPlace('home', 'mag-partb'), { arrangement: 'home', holds: false })
  await assert.rejects(savedPlace(holder, 'mag-partb'), new RegExp(NO_SAVED_PLACE.slice(0, 40)))
  assert.deepEqual(await findConfigurationLocation('mag-partb', ['home', holder]), { arrangement: 'home', holds: false },
    'a saved location that holds nothing still carries the save')
  // The save goes through it, and asks for nothing but the definition's change.
  const saved = await saveCollection({ brainKey, arrangement: 'home', magnet: 'mag-partb', change: identityChange('An idea'), op: 'op-one' })
  assert.deepEqual(saved.identity, { name: 'An idea' })
  const post = asked.find((a) => a.path.endsWith('/reconfigure'))!
  assert.equal(post.path, '/fluid/api/arrangements/home/magnets/mag-partb/reconfigure')
  assert.deepEqual(JSON.parse(post.body!), { change: { identity: { name: 'An idea' } }, op: 'op-one' })
  assert.ok(!asked.some((a) => a.path.includes('/magnets') && !a.path.endsWith('/reconfigure') && a.body),
    'nothing was attached, created or placed to make the save possible')
})

test('a location that holds the Magnet is preferred, and none saved at all is said', async () => {
  const holder = 'ent-workspace11'
  globalThis.fetch = (async (path: string) => {
    const at = String(path)
    if (at.endsWith(holder)) return new Response(JSON.stringify({ layout: { format: 'mentis.fluid-arrangement', version: 3, magnets: { 'mag-partb': config() } } }), { status: 200 })
    if (at.endsWith('/home')) return new Response(JSON.stringify({ layout: { format: 'mentis.fluid-arrangement', version: 3 } }), { status: 200 })
    return new Response(JSON.stringify({ layout: null }), { status: 200 })
  }) as typeof fetch
  assert.deepEqual(await findConfigurationLocation('mag-partb', ['home', holder]), { arrangement: holder, holds: true },
    'the holding one wins, so its own projection is kept current by the same write')
  globalThis.fetch = (async () => new Response(JSON.stringify({ layout: null }), { status: 200 })) as typeof fetch
  assert.equal(await findConfigurationLocation('mag-partb', ['home', holder]), null, 'no saved location at all is said, not guessed')
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

/** THE PANEL IS ONE BODY NOW, NOT TWO (owner request: "Simplify collection
 *  configuration substantially. Consolidate duplicated settings").
 *
 *  Settings used to draw a second, older form for the same settings, with its
 *  own source list, its own add-a-source controls, its own standing Save and
 *  Cancel and its own count out of twenty. It now draws the approved round-3
 *  body (`quiet_magnet_collection_design_unit.ts` is that surface's test) plus
 *  the two things only Settings has. So the strings this test used to pin --
 *  'Add Conversations', 'Add files', '1 of 20 sources chosen', a Save standing
 *  on an unedited panel -- are the duplication that was asked to go, and what
 *  is pinned here instead is what Settings is FOR: the name first, the sources,
 *  what no source means, and the saved location disclosed rather than demanded. */
test('the panel opens on the name and the sources, and says what no source means', () => {
  store()
  const html = renderToStaticMarkup(createElement(CollectionConfiguration, {
    magnet: 'mag-partb', config: config(), brainKey, canWrite: () => true, onSaved: () => {},
  }))
  assert.ok(html.indexOf('>Name') < html.indexOf('>Sources<'), 'the name comes first')
  assert.ok(html.includes('does not change where it is shown'))
  assert.ok(html.includes(NO_SOURCE_TO_COLLECT), 'the empty state says what it means for Collect')
  // Adding a source is the approved one-way editor, in Settings as in Collection.
  assert.ok(html.includes('＋ Add source'), 'one way to add a source, shared with the approved surface')
  assert.ok(!html.includes('Add Conversations') && !html.includes('Add files'),
    'the second set of add-a-source controls is gone, not restyled')
  // At rest nothing is unsaved, so there is no commit and no form standing on
  // the panel -- the same rule the approved surface follows.
  assert.ok(!html.includes('Unsaved changes'), 'opening Settings announces nothing')
  assert.ok(!html.includes('aria-label="Save collection configuration"'), 'the commit follows an edit, not the slot')
  assert.ok(!html.includes('of 20 sources chosen'), 'the rows are the count; the bound is stated where it bites')
  // WHICH SAVED LOCATION THE SAVE GOES THROUGH IS NEITHER ASKED NOR DISCLOSED
  // (Part G2, #802 and amendment §4). It used to be a "Saved location" select
  // over every saved arrangement AND every Conversation, behind a disclosure.
  // It was never a choice about the Magnet -- the definition belongs to no
  // arrangement, and the right location is already found read-only -- so both
  // the select and the disclosure that housed it are gone, not restyled.
  assert.ok(!html.includes('Saved location'), 'the select is gone')
  assert.ok(!html.includes('Where this configuration is saved through'), 'and so is the disclosure around it')
  assert.ok(!html.includes('Location containing this Magnet'))
  assert.ok(!html.includes('(not applied)'), 'and the JSON of an unapplied selection key with it')
  const withSources = renderToStaticMarkup(createElement(CollectionConfiguration, {
    magnet: 'mag-partb', config: config({ sources: [HELD], identity: { name: 'Tide study' } }), brainKey, canWrite: () => true, onSaved: () => {},
  }))
  assert.ok(withSources.includes('notes/a.txt'), 'the configured source is a row of its own')
  assert.ok(withSources.includes('>Remove<'), 'each configured source carries its own Remove')
  assert.ok(withSources.includes('value="Tide study"'))
  assert.ok(!withSources.includes(NO_SOURCE_TO_COLLECT))
})

/** THE DATE LIMITS ARE PICKED, NOT TYPED (owner request: "use appropriate
 *  controls such as date pickers"). The schema still accepts a full ISO
 *  timestamp, so a stored limit that carries a time of day must survive a visit
 *  to a control that can only show days. */
test('a date limit is a day a picker can show, and a stored time of day survives it', () => {
  assert.equal(dayOf('2026-01-01'), '2026-01-01')
  assert.equal(dayOf('2026-01-01T12:00:00Z'), '2026-01-01', 'the picker shows the day a timestamp falls on')
  assert.equal(dayOf(''), '')
  assert.equal(dayOf('whenever'), '', 'a limit no day can be read from shows empty, never a misread date')
  // Unchanged day: the stored limit is kept exactly, time and all.
  assert.equal(withDay('2026-01-01T12:00:00Z', '2026-01-01'), '2026-01-01T12:00:00Z')
  // A genuine change of day replaces it with the day that was picked.
  assert.equal(withDay('2026-01-01T12:00:00Z', '2026-01-02'), '2026-01-02')
  assert.equal(withDay('', '2026-01-02'), '2026-01-02')
  // Clearing the picker clears the limit.
  assert.equal(withDay('2026-01-01T12:00:00Z', ''), '')
  // Whatever the picker produces is a limit `collectionChange` accepts.
  const before = config()
  for (const day of ['2026-01-01', '2026-12-31']) {
    assert.deepEqual(collectionChange(before, [], [], day, '', false).selection.dates, { after: day })
  }
  assert.throws(() => collectionChange(before, [], [], '2026-03-02', '2026-03-01', false), /end date is before the start date/)
})

/** The panel draws the design's own controls, so it must be styled where the
 *  design's stylesheet does not reach: every `mgd-` rule in `design.css` is
 *  scoped `.q2-magnet-card …`, and Magnet Management draws this panel on a page
 *  instead. `configuration.css` carries one-class base rules for exactly those
 *  primitives; being one class each, they can never outrank the approved design
 *  inside the card. */
test('the design primitives the panel composes from are styled outside the card too', () => {
  const css = readFileSync(new URL('../src/quiet2/magnets/configuration.css', import.meta.url), 'utf8')
  const design = readFileSync(new URL('../src/quiet2/magnets/design.css', import.meta.url), 'utf8')
  for (const c of ['mgd-row', 'mgd-spread', 'mgd-grow', 'mgd-divider', 'mgd-source', 'mgd-subtle', 'mgd-small',
    'mgd-muted', 'mgd-h3', 'mgd-button', 'mgd-link', 'mgd-pill', 'mgd-space']) {
    assert.ok(new RegExp(`^\\.${c}[\\s,.:{]`, 'm').test(css), `${c} has a base rule of one class`)
    assert.ok(!new RegExp(`^\\.q2-magnet-card .*\\.${c}\\b`, 'm').test(css), `${c} is not restated at the card's reach`)
  }
  // Every mgd- rule in the approved design carries at least two classes, so it
  // wins inside the card whichever stylesheet loaded last.
  for (const line of design.split('\n')) {
    if (!line.startsWith('.')) continue
    for (const selector of line.slice(0, line.indexOf('{') < 0 ? undefined : line.indexOf('{')).split(',')) {
      if (!selector.includes('.mgd-')) continue
      assert.ok((selector.match(/\./g) ?? []).length >= 2, `the design's "${selector.trim()}" outranks a one-class base rule`)
    }
  }
})

/* -- PART G2: NO INTERNAL MODE WORD, AND NO JSON --------------------------------
 *
 * #802 and amendment §4. `configurationFacts` used to end in "Collection:
 * one-time · synthesis: manual · activation: manual" and a `JSON.stringify` per
 * saved-but-unapplied selection key. Both are gone: how often it collects is
 * said in ordinary words, and an unapplied filter is named without its value. */
test('the configuration facts say how often it collects, not which modes are saved', () => {
  const manual = config()
  const facts = configurationFacts(manual)
  const text = facts.join('\n')
  for (const gone of ['one-time', 'on-new-information', 'scheduled', 'JSON', '{', '}']) {
    assert.ok(!text.includes(gone), gone + ' still appears in the configuration facts')
  }
  assert.ok(facts.some((f) => f.startsWith('How often it collects: ')), text)
  // The sentence the Magnet was made from is a fact the owner recognises.
  const followed = configurationFacts(config({ selection: { criteria: 'the tide work' } }))
  assert.equal(followed[1], 'What it follows: the tide work')
  assert.ok(!followed.join('\n').includes('criteria'), 'said as what it is, not by its schema key')
})

test('a cadence is said as what it is, never as its ISO duration', () => {
  assert.equal(collectionRhythm(config({ collection: { mode: 'scheduled', schedule: 'P1D' } })), 'Every day, on its own')
  assert.equal(collectionRhythm(config({ collection: { mode: 'scheduled', schedule: 'PT6H' } })), 'Every six hours, on its own')
  assert.equal(collectionRhythm(config({ collection: { mode: 'scheduled', schedule: 'PT1H' } })), 'Every hour, on its own')
  assert.equal(collectionRhythm(config({ collection: { mode: 'scheduled', schedule: 'P1W' } })), 'Every week, on its own')
  // A cadence nothing here has words for is still never read out raw.
  const odd = collectionRhythm(config({ collection: { mode: 'scheduled', schedule: '*/5 * * * *' } }))
  assert.equal(odd, 'On a schedule, on its own')
  assert.equal(collectionRhythm(config({ collection: { mode: 'paused' } })), 'Paused — it is not collecting')
  assert.ok(!collectionRhythm(config()).includes('one-time'))
})

test('a saved filter this build does not apply is named without its value', () => {
  const facts = configurationFacts(config({ selection: { phrases: ['tide', 'harbour'], topics: ['ent-aaaaaaaaaaaa'] } }))
  const text = facts.join('\n')
  assert.ok(text.includes('Saved here but not applied by this build: phrases'), text)
  assert.ok(text.includes('Saved here but not applied by this build: topics'), text)
  assert.ok(!text.includes('tide') && !text.includes('ent-aaaaaaaaaaaa'), 'the value is in the record, not on screen')
  assert.ok(!text.includes('['), 'and never as its wire format')
})
