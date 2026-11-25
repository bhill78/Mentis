/** NO RAW IDENTIFIER ON THE RESTING SURFACE (owner request ent-1e82a8786c37).
 *
 *  The owner asked for "the clean Collection rows shown in the mockups, without
 *  raw identifiers or unnecessary technical symbols", and the round-three
 *  mockup's own row reads "Alex · today, 10:31 AM". The glyphs and the row's
 *  `evidenceOrigin` byline went in `e8c70cdf`, but two raw identities were still
 *  reaching the reader on the deployed candidate `9eb60efd`:
 *
 *    - a collected post's byline printed `author` straight from the collection
 *      read, which states the participant's recorded ENTRY ID, so a row read
 *      "ent-5936369158a8 · Nov 23";
 *    - the Summary's excerpts carried `evidenceOrigin`, so each quote read
 *      "Conversation ent-a1d2c5e714ea" or "Held file col-5260ed8d10f2 / README.md".
 *
 *  Provenance is NOT what is being removed: the owner kept it ("History,
 *  provenance and lineage remain accessible when needed"), so `evidenceOrigin`
 *  and `sourceLabel` still state the exact captured key, and the inspection's
 *  provenance disclosure still shows it. What this file pins is that the resting
 *  surface -- a row, an excerpt -- never does.
 *
 *  It also pins the third correction of the same round: the embedded Sources
 *  panel takes its staged copy the moment it opens, so the existence of that
 *  copy is not evidence of an edit, and "Unsaved changes. Save or cancel."
 *  must follow the comparison with what is saved instead. Inside Collection
 *  that panel is somewhere a reader simply looks. */
import assert from 'node:assert/strict'
import { test } from 'node:test'
import { rowByline } from '../src/quiet2/magnets/EvidenceViews'
import { evidenceOrigin, plainEvidenceOrigin, sourceLabel } from '../src/quiet2/magnets/Inspection'
import { committedSettings, settingsEdited } from '../src/quiet2/magnets/CollectionConfiguration'
import type { RouteResult } from '../src/fluid/surface/magnet/route'
import type { MagnetConfig } from '../src/fluid/surface/magnet/types'

const RAW = /ent-[a-z0-9]{6,}|col-[a-z0-9]{6,}|adm-[a-z0-9]{6,}/

const AUTHOR = 'ent-5936369158a8'
const WHEN = Date.parse('2026-11-23T17:08:00Z') / 1000

const post = (): RouteResult => ({ kind: 'post', id: 'ent-0d2c70c474ec', conversation: 'ent-a1d2c5e714ea',
  author: AUTHOR, at: WHEN, number: 1, value: { text: 'Synthetic retained acceptance post.' } })
const heldFile = (): RouteResult => ({ kind: 'file', id: 'held:col-5260ed8d10f2:README.md', at: WHEN,
  value: { collection: 'col-5260ed8d10f2', path: 'README.md', text: '# Disposable audit folder' },
  ...{ via: 'held-source' } } as RouteResult)

/* --- the row's byline ------------------------------------------------------- */

test('a collected post’s byline is the person’s name, and never the recorded participant id', () => {
  const named = new Map([[AUTHOR, 'brian']])
  const byline = rowByline(post(), named)
  assert.ok(byline.startsWith('brian · '), `the mockup's row names a person: got "${byline}"`)
  assert.ok(!RAW.test(byline), `no raw identifier in "${byline}"`)
})

test('an author nobody names says what the item is, not the id the read stated', () => {
  for (const named of [undefined, new Map<string, string>(), new Map([['ent-someone-else', 'Alex']])]) {
    const byline = rowByline(post(), named)
    assert.ok(!RAW.test(byline), `no raw identifier in "${byline}"`)
    assert.ok(byline.startsWith('Collected post'), `it still says what the row is: got "${byline}"`)
  }
})

test('an author the read states as a name, not an id, is shown as it is', () => {
  // The collection read states an entry id on this build; one that states a
  // name is not second-guessed, and the row still carries no id either way.
  const stated: RouteResult = { ...post(), author: 'Alex' }
  assert.ok(rowByline(stated).startsWith('Alex · '), rowByline(stated))
  assert.ok(!RAW.test(rowByline(stated)))
})

test('an alias is shown as a name, without the @ the record writes it with', () => {
  assert.ok(rowByline(post(), new Map([[AUTHOR, 'brian']])).startsWith('brian'))
  assert.ok(!rowByline(post(), new Map([[AUTHOR, '@brian']])).includes('@'),
    'the participants read states aliases with @; a row is a byline, not a mention')
})

test('a held file’s row byline carries neither its collection key nor its digest', () => {
  const byline = rowByline(heldFile())
  assert.ok(byline.startsWith('Held file'), `got "${byline}"`)
  assert.ok(!RAW.test(byline), `no raw identifier in "${byline}"`)
})

/* --- the excerpt's origin --------------------------------------------------- */

test('the clean origin states the kind of record, and a held file’s own name', () => {
  assert.equal(plainEvidenceOrigin(post()), 'Collected post')
  assert.equal(plainEvidenceOrigin(heldFile()), 'Held file · README.md')
})

test('no resting-surface origin carries a raw identifier', () => {
  for (const r of [post(), heldFile(), { kind: 'attachment', id: 'x', post: 'ent-7ff105c9be05' } as RouteResult]) {
    const said = plainEvidenceOrigin(r)
    assert.ok(!RAW.test(said), `no raw identifier in "${said}"`)
  }
})

test('provenance is untouched: the exact captured key is still stated where lineage belongs', () => {
  // The owner kept provenance reachable, so these two must NOT be cleaned.
  assert.equal(sourceLabel('conversation:ent-a1d2c5e714ea'), 'Conversation ent-a1d2c5e714ea')
  assert.equal(evidenceOrigin(post()), 'Conversation ent-a1d2c5e714ea')
  assert.equal(evidenceOrigin(heldFile()), 'Held file col-5260ed8d10f2 / README.md')
})

/* --- the embedded panel's unsaved note -------------------------------------- */

const config = (): MagnetConfig => ({ id: 'mag-cda231ae0e0af873',
  sources: [{ kind: 'conversation', conversation: 'ent-a1d2c5e714ea' }],
  selection: { informationTypes: ['post', 'file', 'image', 'attachment'], dates: {} },
  collection: { mode: 'one-time' }, synthesis: { mode: 'manual' }, activation: { mode: 'manual' },
  processing: { operations: [{ op: 'extract' }] },
  notifications: { newItems: false, changes: false, failures: false },
  presentation: { renderer: 'disc' } })

test('the staged copy a freshly opened panel takes is not reported as an unsaved change', () => {
  const c = config()
  assert.equal(settingsEdited(committedSettings(c), c), false,
    'opening Sources to look at it announces nothing')
})

test('an actual edit is reported', () => {
  const c = config()
  const base = committedSettings(c)
  assert.equal(settingsEdited({ ...base, sources: [] }, c), true, 'a removed source')
  assert.equal(settingsEdited({ ...base, sources: [...base.sources, { kind: 'conversation', conversation: 'ent-5dce9d23f9d8' }] }, c), true, 'an added source')
  assert.equal(settingsEdited({ ...base, types: ['post'] }, c), true, 'a changed selection')
  assert.equal(settingsEdited({ ...base, after: '2026-01-01' }, c), true, 'a date')
  assert.equal(settingsEdited({ ...base, manual: true }, c), true, 'manual collection')
})

test('reordering nothing and restating the same selection is not an edit', () => {
  const c = config()
  const base = committedSettings(c)
  assert.equal(settingsEdited({ ...base, sources: [...base.sources], types: [...base.types] }, c), false,
    'the same selection, newly built, is still the saved one')
})
