/** H5: the focused Settings overlay and the question-first Perspectives panel.
 *
 *  Proves the focused overlay and the controls relocated into it, the three-way
 *  Save / Cancel / Escape semantics of the staged configuration, the three
 *  validation rules in their approved wording, the honest supported-vs-proposed
 *  source model, question-first creation with no name field, the five
 *  independent draft slots across a lens switch, a tab switch and a reload, and
 *  `perspectiveSource.complete()` reaching an earlier wording on a second
 *  history page -- with the no-advance guard proven. */
import assert from 'node:assert/strict'
import { test } from 'node:test'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import Magnet from '../src/quiet2/magnets/Magnet'
import SettingsView from '../src/quiet2/magnets/SettingsView'
import CollectionConfiguration from '../src/quiet2/magnets/CollectionConfiguration'
import Perspectives from '../src/quiet2/magnets/InquiryPanel'
import { createMagnetResource } from '../src/quiet2/magnets/state'
import { goTab, leaveSettings, openOverlay, place, setOpen } from '../src/quiet2/magnets/places'
import { collectionIssue, configurationFacts, PROPOSED_SOURCES, settingsSource, SUPPORTED_SOURCES } from '../src/quiet2/magnets/configuration'
import {
  discardStagedSettings, forgetPanelDrafts, panelAt, panelDrafts, requestSettingsReturn,
  setQuestionDraft, setRenameDraft, setRevisionDraft, stageSettings, takeSettingsReturn, type StagedSettings,
} from '../src/quiet2/magnets/panelDrafts'
import { derivedPerspectiveName, perspectiveSource, perspectivesOf } from '../src/quiet2/magnets/perspectives'
import { miniComposerDraft, saveMiniComposer } from '../src/quiet2/magnets/conversation'
import { page as binding } from '../src/brainBinding'
import type { MagnetConfig } from '../src/fluid/surface/magnet/types'
import type { MagnetResource } from '../src/quiet2/magnets/contract'

const SOURCE = 'ent-source111111'
const A = 'ent-topicaaaaaa', B = 'ent-topicbbbbbb'
const brainKey = 'origin|fixture|brain-h5'
const store = () => {
  const mem = new Map<string, string>()
  Object.defineProperty(globalThis, 'localStorage', { configurable: true, value: {
    getItem: (k: string) => mem.get(k) ?? null, setItem: (k: string, v: string) => mem.set(k, v),
    removeItem: (k: string) => mem.delete(k), clear: () => mem.clear() } })
  binding.saw('brain-h5@instance-one')
  forgetPanelDrafts()
  return mem
}
const config = (id: `mag-${string}`, change: Partial<MagnetConfig> = {}): MagnetConfig => ({
  id, sources: [{ kind: 'conversation', conversation: SOURCE }],
  selection: { informationTypes: ['post', 'file'], dates: { after: '2026-01-01' } },
  conversation: 'ent-own111111', collection: { mode: 'one-time' }, synthesis: { mode: 'manual' },
  activation: { mode: 'manual' }, notifications: { newItems: false, changes: false, failures: false },
  presentation: { renderer: 'disc' }, ...change,
})
const resource = (id: `mag-${string}`, saved = config(id)) => createMagnetResource({
  id: `qm-${id}`, brainKey, saved: { id, name: 'Calibration inquiry', config: saved },
  get: async () => ({ status: 200, body: { magnet: id, config: saved, activation: null, page: null } }),
})
const settings = (resource: MagnetResource) => renderToStaticMarkup(createElement(SettingsView, {
  resource, canReset: true, hasOwnConversation: true,
  onReset: () => {}, onRemove: () => {}, onSource: () => {}, onConversation: () => {}, onOrigin: () => {},
  collectionConfiguration: createElement(CollectionConfiguration, {
    magnet: resource.saved.id, config: resource.saved.config!, brainKey,
    canWrite: () => true, onSaved: () => {},
  }),
}))
const staged = (change: Partial<StagedSettings> = {}): StagedSettings =>
  ({ sources: [{ kind: 'conversation', conversation: SOURCE }], types: ['post'], after: '', before: '', manual: false, ...change })

test('the settings overlay is focused, and holds every control the frame extraction moved here', () => {
  store()
  const r = resource('mag-h5focus')
  setOpen(r, true)
  openOverlay(r, 'settings')
  const html = settings(r)
  // The same controls, in the owner's order (ent-3191baeb33d2 §4): configuration
  // first, the advanced material disclosed, external navigation only on request.
  for (const control of ['Source Conversation', 'Full Conversation', 'Where this was opened from',
    'Collection history', 'Reset position', 'Remove this Magnet from the workspace']) {
    assert.ok(html.includes(control), `the overlay holds ${control}`)
  }
  for (const gone of ['Navigate to source Conversation', 'Navigate back to opening workspace',
    'Earlier retained batches', 'Returning here, like Escape']) {
    assert.ok(!html.includes(gone), `${gone} no longer takes the first screen`)
  }
  // Configuration is what Settings opens on: B's slot comes before the rest.
  const configuration = html.indexOf('q2-magnet-config')
  for (const later of ['Collection history', 'Open outside this Magnet', 'Remove from the workspace']) {
    assert.ok(configuration > 0 && html.indexOf(later) > configuration, `${later} comes after the configuration controls`)
  }
  assert.ok(html.includes('aria-label="Close settings and return to Summary"'), 'the way back is one compact control')
  for (const disclosed of ['Collection history', 'Open outside this Magnet', 'Remove from the workspace']) {
    assert.ok(html.includes(`<summary>${disclosed}</summary>`), `${disclosed} is disclosed, not stacked open`)
  }
  // The frame keeps the Summary out of the way while this is open.
  const card = renderToStaticMarkup(createElement(Magnet, { resource: r, onExpand: () => {}, onCollapse: () => {},
    views: { settings: createElement('p', null, 'overlay'), Summary: createElement('p', null, 'summary beneath') },
    footerComposer: createElement('form', { id: 'composer' }), searchToolbar: createElement('div', { id: 'toolbar' }) }))
  assert.ok(card.includes('overlay'))
  assert.ok(!card.includes('summary beneath'), 'the Summary is not visible beneath the overlay')
  assert.ok(!card.includes('id="composer"'), 'the composer is hidden')
  assert.ok(!card.includes('id="toolbar"'), 'the search toolbar is hidden')
  assert.match(card, /disabled=""[^>]*>Collect now<\/button>/, 'Collect now is disabled')
})

test('the gear is icon-only, and the two closes are different controls with different words', () => {
  store()
  const r = resource('mag-h5closes')
  setOpen(r, true)
  const card = renderToStaticMarkup(createElement(Magnet, { resource: r, onExpand: () => {}, onCollapse: () => {} }))
  assert.ok(card.includes('aria-label="Magnet settings"'), 'the gear has an accessible name')
  assert.ok(!card.includes('>Settings<'), 'the gear carries no visible text')
  assert.ok(card.includes('aria-label="Close Magnet"'), 'the card close says it closes the card')
  assert.ok(!card.includes('Remove this Magnet'), 'the card close never removes the Magnet')
  const html = settings(r)
  assert.ok(html.includes('Remove this Magnet from the workspace'))
  assert.ok(!html.includes('Close Magnet'), 'the overlay holds no second card-close')
  assert.ok(html.includes('Removes this Magnet from the canvas.'), 'removal describes its effect briefly')
  assert.ok(html.includes('Position controls'), 'position guidance is available on demand')
})

test('Save commits and returns, Cancel discards the staged copy only, Escape keeps it', () => {
  store()
  const r = resource('mag-h5stage')
  const at = panelAt(r)
  setOpen(r, true)
  goTab(r, 'Files')
  saveMiniComposer(r, { ...miniComposerDraft(r), text: 'words not yet sent' })
  setQuestionDraft(at, 'Does the calibration drift?')
  setRevisionDraft(at, A, 'An edited wording')
  openOverlay(r, 'settings')
  stageSettings(at, staged({ types: ['post', 'image'] }))
  // Escape (and the Return link) leave the overlay and keep the staged copy.
  leaveSettings(r)
  assert.equal(r.snapshot().overlay, null)
  assert.equal(r.snapshot().tab, 'Files', 'leaving returns exactly where the gear was pressed')
  assert.deepEqual(panelDrafts(at).settings?.types, ['post', 'image'], 'Escape suspends; it does not discard')
  // Cancel discards the staged copy entirely, and nothing else.
  openOverlay(r, 'settings')
  discardStagedSettings(at)
  assert.equal(panelDrafts(at).settings, null)
  assert.equal(miniComposerDraft(r).text, 'words not yet sent', 'Cancel never touches the message draft')
  assert.equal(panelDrafts(at).question, 'Does the calibration drift?', 'Cancel never touches the new-question draft')
  assert.equal(panelDrafts(at).revisions[A], 'An edited wording', 'Cancel never touches a revision draft')
  // A committed save clears the stage and asks the overlay to return, once.
  stageSettings(at, staged())
  requestSettingsReturn(at)
  assert.equal(panelDrafts(at).settings, null, 'what was saved is no longer unsaved')
  assert.equal(takeSettingsReturn(at), true)
  assert.equal(takeSettingsReturn(at), false, 'the return is consumed once, not on every render')
  assert.equal(miniComposerDraft(r).text, 'words not yet sent')
})

test('the three validation rules refuse in order, in their approved wording, and commit nothing', () => {
  // No source is no longer a refusal: a Magnet may be saved with none and told
  // what to collect later (owner request ent-3191baeb33d2 §4).
  assert.equal(collectionIssue(staged({ sources: [] })), null)
  assert.equal(collectionIssue(staged({ types: [] })), 'Choose a Conversation content type.')
  assert.equal(collectionIssue(staged({ after: '2026-03-02', before: '2026-03-01' })), 'After date must be before the before date.')
  // With no source there is no Conversation content type to require either.
  assert.equal(collectionIssue(staged({ sources: [], types: [] })), null)
  // A held file without a Conversation needs no Conversation content type.
  assert.equal(collectionIssue(staged({ sources: [{ kind: 'file', collection: 'col-held', path: 'a.txt' }], types: [] })), null)
  assert.equal(collectionIssue(staged({ after: '2026-03-01', before: '2026-03-02' })), null)
  assert.equal(collectionIssue(staged()), null)
})

test('a refused rule takes focus in an alert, and the panel keeps its live source count', () => {
  store()
  const r = resource('mag-h5alert')
  const at = panelAt(r)
  stageSettings(at, staged({ sources: [{ kind: 'conversation', conversation: SOURCE }, { kind: 'file', collection: 'col-held', path: 'a.txt' }] }))
  const html = settings(r)
  assert.ok(html.includes('2 of 20 sources chosen'), 'the source count follows the staged selection')
  assert.ok(html.includes('role="status"'), 'the count is announced without rebuilding the choices')
  // The alert element is rendered only when a rule has failed, and it is focusable.
  assert.ok(!html.includes('role="alert"'))
  const source = renderToStaticMarkup(createElement(CollectionConfiguration, { magnet: r.saved.id, config: r.saved.config!, brainKey, canWrite: () => true, onSaved: () => {} }))
  assert.ok(source.includes('Save collection configuration'))
  assert.ok(source.includes('Cancel configuration edits'))
})

test('the source model is presented honestly: supported and actionable, proposed and not offered', () => {
  store()
  const r = resource('mag-h5sources')
  const html = settings(r)
  for (const s of SUPPORTED_SOURCES) assert.ok(html.includes(s.words.slice(0, 40)), `supported: ${s.kind}`)
  for (const s of PROPOSED_SOURCES) assert.ok(html.includes(s.words), `proposed: ${s.words}`)
  assert.ok(html.includes('Proposed only, and not interactive here'))
  assert.ok(html.includes('An existing connector does not enable a Magnet adapter.'))
  assert.ok(html.includes('Collection limits'), 'unsupported filters and source kinds remain available as contextual help')
  // Only the two supported kinds are offered as choices.
  assert.ok(html.includes('Add Conversations') && html.includes('Add files'))
  for (const s of PROPOSED_SOURCES) assert.ok(!html.includes(`Add ${s.words}`), `${s.words} is not offered as a choice`)
})

test('settingsSource indexes the committed configuration and the source wording, and is already complete', () => {
  store()
  const r = resource('mag-h5index')
  const source = settingsSource(r)
  const entries = source.entries()
  assert.equal(source.complete, undefined, 'nothing is paginated, so nothing is owed')
  assert.equal(source.queryDependent, false)
  assert.ok(entries.every((e) => e.kind === 'Settings'))
  const text = entries.map((e) => e.text).join('\n')
  assert.ok(text.includes(`conversation:${SOURCE}`), 'the configured source is searchable')
  assert.ok(text.includes('post, file'), 'the selected content types are searchable')
  assert.ok(text.includes('2026-01-01'), 'the date limit is searchable')
  assert.ok(PROPOSED_SOURCES.every((s) => text.includes(s.words)), 'the proposed kinds are searchable')
  assert.deepEqual(configurationFacts(r.saved.config!)[1], `Configured sources: conversation:${SOURCE}`)
  // Opening a settings result opens the overlay as a place of its own.
  setOpen(r, true)
  goTab(r, 'Posts')
  entries[0].open()
  assert.equal(r.snapshot().overlay, 'settings')
  assert.equal(r.snapshot().settingsReturn?.tab, 'Posts')
})

test('a Perspective is created from the question alone, and its name is derived from it', () => {
  store()
  const r = resource('mag-h5create')
  const html = renderToStaticMarkup(createElement(Perspectives, { resource: r, canWrite: true, onEvidence: () => {} }))
  assert.ok(html.includes('New question or hypothesis'))
  assert.ok(!html.includes('aria-label="Perspective name"'), 'creation asks for no name')
  assert.ok(html.includes('Its name is taken from the question when you create it.'))
  // The approved rule: unchanged through 52 characters, else the first 49 plus an ellipsis.
  const short = 'Does the calibration drift between batches?'
  assert.equal(derivedPerspectiveName(short), short)
  const fifty2 = 'a'.repeat(52), fifty3 = 'b'.repeat(53)
  assert.equal(derivedPerspectiveName(fifty2), fifty2)
  assert.equal(derivedPerspectiveName(fifty3), 'b'.repeat(49) + '…')
  assert.equal(Array.from(derivedPerspectiveName(fifty3)).length, 50)
  // Characters, not code units: an emoji is one character and is never halved.
  const emoji = '\u{1f642}'.repeat(60)
  assert.equal(Array.from(derivedPerspectiveName(emoji)).length, 50)
  assert.ok(derivedPerspectiveName(emoji).endsWith('…'))
  assert.equal(derivedPerspectiveName('  spaced   out  '), 'spaced out')
})

test('the five draft slots are independent and survive a lens switch, a tab switch and a reload', () => {
  store()
  const r = resource('mag-h5drafts')
  const at = panelAt(r)
  setOpen(r, true)
  saveMiniComposer(r, { ...miniComposerDraft(r), text: 'unsent message' })
  setQuestionDraft(at, 'A new question')
  setRevisionDraft(at, A, 'A revision of A')
  setRevisionDraft(at, B, 'A revision of B')
  setRenameDraft(at, A, 'A better name for A')
  setRenameDraft(at, B, 'A better name for B')
  stageSettings(at, staged({ after: '2026-02-02' }))
  // A lens switch, a tab switch, and an overlay opening and closing.
  const inquiry = perspectivesOf(r)
  inquiry.update({ selected: B })
  r.update({ lens: B })
  goTab(r, 'Perspectives')
  goTab(r, 'Conversation')
  openOverlay(r, 'settings')
  leaveSettings(r)
  // And a reload: the page's copy is gone and the words come back from storage.
  forgetPanelDrafts()
  const after = panelDrafts(at)
  assert.equal(after.question, 'A new question')
  assert.equal(after.revisions[A], 'A revision of A')
  assert.equal(after.revisions[B], 'A revision of B', 'one Perspective\'s revision never clobbers another')
  assert.equal(after.renames[A], 'A better name for A')
  assert.equal(after.renames[B], 'A better name for B')
  assert.equal(after.settings?.after, '2026-02-02')
  assert.equal(miniComposerDraft(r).text, 'unsent message', 'the message draft is its own slot and nothing here touched it')
  // Another Magnet never sees them.
  const other = resource('mag-h5other')
  assert.deepEqual(panelDrafts(panelAt(other)), { question: '', reason: '', revisions: {}, renames: {}, settings: null, returned: 0 })
})

test('an earlier rename draft survives creation and selection', () => {
  store()
  const r = resource('mag-h5rename')
  const at = panelAt(r)
  setRenameDraft(at, A, 'An unsaved name')
  const inquiry = perspectivesOf(r)
  inquiry.update({ rows: [{ perspective: A, name: 'Original', retired: false, question: null, events: 1 }], selected: A, viewed: A })
  inquiry.update({ selected: B, viewed: B })      // a creation selects the new Perspective
  forgetPanelDrafts()
  assert.equal(panelDrafts(at).renames[A], 'An unsaved name')
})

/** A paged fake: two Perspectives, each with two pages of wording history. The
 *  wording that matters is on the second page, which is exactly what a search
 *  over "whatever was loaded" would miss. */
function paged(r: MagnetResource, options: { stall?: boolean } = {}) {
  const inquiry = perspectivesOf(r)
  const calls: string[] = []
  const rows = [
    { perspective: A, name: 'First', retired: false, question: null, current_question: { text: 'Current A', revision: 'adm-a' }, events: 4 },
    { perspective: B, name: 'Second', retired: false, question: null, current_question: { text: 'Current B', revision: 'adm-b' }, events: 2 },
  ]
  const history: Record<string, Record<string, { events: unknown[]; next: string | null }>> = {
    [A]: {
      first: { events: [{ seq: 1, post: 'ent-a1', event: 'created', perspective: A, snapshot: { ref: 'adm-s1', digest: 'a' }, data: { name: 'First' } }], next: 'a-page2' },
      'a-page2': { events: [{ seq: 2, post: 'ent-a2', event: 'question', perspective: A, snapshot: { ref: 'adm-s2', digest: 'a' }, data: { text: 'An earlier wording on the second page' } }], next: options.stall ? 'a-page2' : null },
    },
    [B]: { first: { events: [{ seq: 1, post: 'ent-b1', event: 'rename', perspective: B, snapshot: { ref: 'adm-s3', digest: 'b' }, data: { name: 'An earlier name' } }], next: null } },
  }
  inquiry.get = async (tail = '') => {
    calls.push(tail)
    if (tail.startsWith('?')) {
      const cursor = new URLSearchParams(tail.slice(1)).get('cursor')
      return cursor === 'list-page2'
        ? { perspectives: [rows[1]], selected: A, next: null }
        : { perspectives: [rows[0]], selected: A, next: 'list-page2' }
    }
    const [, topic, rest] = tail.split('/')
    const row = rows.find((v) => v.perspective === topic)
    if (!rest) return { ...row, magnet: r.saved.id, selected: A, question: { ref: row!.current_question.revision } }
    const cursor = new URLSearchParams(rest.split('?')[1] ?? '').get('cursor') ?? 'first'
    const paging = history[topic]?.[cursor]
    if (!paging) throw new Error(`no page ${cursor} for ${topic}`)
    return { magnet: r.saved.id, perspective: topic, events: paging.events, next: paging.next }
  }
  return { inquiry, calls, rows }
}

test('perspectiveSource.complete() walks every Perspective and every earlier wording to exhaustion', async () => {
  store()
  const r = resource('mag-h5search')
  const { calls } = paged(r)
  const source = perspectiveSource(r)
  assert.equal(source.queryDependent, false)
  const entries = await source.complete!('wording')
  assert.equal(source.bound!(), null, 'nothing stopped it, so it claims nothing')
  const text = entries.map((e) => e.text)
  assert.ok(text.includes('An earlier wording on the second page'), 'a wording on a second history page is reached')
  assert.ok(text.includes('An earlier name'), 'a Perspective found only on the second list page is reached')
  assert.ok(entries.some((e) => e.title.startsWith('Earlier wording')))
  assert.ok(entries.some((e) => e.title.startsWith('Earlier name')))
  assert.ok(entries.every((e) => e.kind === 'Perspectives'))
  assert.equal(new Set(entries.map((e) => e.key)).size, entries.length, 'the index holds each wording once')
  assert.ok(calls.some((c) => c.includes('cursor=list-page2')) && calls.some((c) => c.includes('cursor=a-page2')))
  assert.ok(calls.every((c) => !/prepare|reconcile|finalize|collection/.test(c)), 'searching prepares nothing')
  // Opening a wording result goes to the Perspectives tab with that lens.
  setOpen(r, true)
  goTab(r, 'Files')
  entries.find((e) => e.text === 'An earlier wording on the second page')!.open()
  assert.equal(r.snapshot().tab, 'Perspectives')
  assert.equal(r.snapshot().searchTarget?.lens, A)
  assert.equal(r.snapshot().searchTarget?.item, 'ent-a2')
  assert.equal(place({ ...r.snapshot(), tab: 'Files', overlay: null }).scroll, 0)
})

test('a cursor that does not advance is reported as a bound, never looped on', async () => {
  store()
  const r = resource('mag-h5stall')
  paged(r, { stall: true })
  const source = perspectiveSource(r)
  const entries = await source.complete!('wording')
  const bound = source.bound!()
  assert.match(bound!, /searched only as far as they could be read/)
  assert.match(bound!, /did not advance/)
  assert.ok(entries.some((e) => e.text === 'An earlier wording on the second page'), 'what was read is still returned')
  // entries() alone stays what the panel has in hand, and says nothing more.
  const inHand = perspectiveSource(r).entries()
  assert.ok(inHand.every((e) => e.kind === 'Perspectives'))
})

test('entries() covers the Perspectives and wording the panel has already read', async () => {
  store()
  const r = resource('mag-h5inhand')
  const { inquiry } = paged(r)
  await inquiry.read()
  await inquiry.view(A)
  const entries = perspectiveSource(r).entries()
  assert.ok(entries.some((e) => e.text.includes('Current A')))
  assert.ok(entries.some((e) => e.title.includes('First')))
  assert.ok(entries.some((e) => e.text === 'First'), 'the created name already read is in hand')
})
