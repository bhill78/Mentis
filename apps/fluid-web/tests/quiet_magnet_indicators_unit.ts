import assert from 'node:assert/strict'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import Magnet from '../src/quiet2/magnets/Magnet'
import { emptyPlaces } from '../src/quiet2/magnets/places'
import { filesIndicator, magnetIndicators, newInformationIndicator, perspectivesIndicator, postsIndicator, restingCount } from '../src/quiet2/magnets/indicators'
import { createMagnetResource } from '../src/quiet2/magnets/state'
import { loadShownBatch } from '../src/quiet2/magnets/workingState'
import { page as binding } from '../src/brainBinding'
import type { MagnetResource, MagnetSnapshot } from '../src/quiet2/magnets/contract'
import type { MagnetConfig } from '../src/fluid/surface/magnet/types'

let checks = 0
const eq = (a: unknown, b: unknown, why: string) => { assert.deepEqual(a, b, why); checks++ }
const ok = (a: unknown, why: string) => { assert.ok(a, why); checks++ }

// Pure indicator logic: truthful counts, no fabricated zero.
eq(postsIndicator(42).value, '42', 'known source-wide tally shown verbatim')
ok(postsIndicator(42).detail.includes('source-wide'), 'posts indicator names its scope as source-wide, not the loaded selection')
eq(postsIndicator(null).value, null, 'missing source tally never becomes zero')
eq(postsIndicator(undefined).value, null, 'undefined source tally stays unavailable')
ok(postsIndicator(null).detail.toLowerCase().includes('unavailable'), 'unknown posts tally says unavailable')
eq(postsIndicator(0).value, '0', 'an actually-reported zero source tally is shown, not hidden')

eq(filesIndicator(3, true, false).value, '3', 'known loaded file count shown')
ok(filesIndicator(3, true, false).detail.includes('loaded'), 'files indicator is labelled loaded')
ok(filesIndicator(5, true, true).detail.includes('partial'), 'partial page is named, not silently merged into the total')
eq(filesIndicator(0, false, false).value, null, 'unread files never render as a bare zero')
ok(filesIndicator(0, false, false).detail.toLowerCase().includes('unavailable'), 'unread files say unavailable, not 0')
eq(filesIndicator(0, true, false).value, '0', 'an actually-read empty page reports 0 truthfully')

eq(perspectivesIndicator().value, null, 'Perspectives has no supported type or count')
ok(perspectivesIndicator().detail.toLowerCase().includes('unavailable'), 'Perspectives indicator states unavailable')
eq(perspectivesIndicator().tab, 'Perspectives', 'Perspectives indicator opens the Perspectives explanation')

// The new-item indicator carries a real count: the rows in the latest batch
// absent from the batch this viewer was last shown. Unknown stays unavailable.
eq(newInformationIndicator(4).value, '4', 'a true new-item count is shown')
ok(newInformationIndicator(4).detail.includes('4 new items since this Magnet was last opened'), 'the new-item indicator explains what its number counts and since when')
ok(newInformationIndicator(1).detail.includes('1 new item since'), 'one new item is said in the singular')
eq(newInformationIndicator(0).value, '0', 'an actually-read empty new-item count is shown, not hidden')
ok(newInformationIndicator(0).detail.toLowerCase().includes('nothing new'), 'nothing new says so')
eq(newInformationIndicator(null).value, null, 'without a baseline no new-item count is invented')
ok(newInformationIndicator(null).detail.toLowerCase().includes('unavailable'), 'an absent new-item count states unavailable')
eq(newInformationIndicator(undefined).value, null, 'an undefined new-item count stays unavailable')
ok(!newInformationIndicator(null).detail.toLowerCase().includes('unread'), 'new-item indicator never speaks of unread, only an absent total')
ok(!/not supported|yet/i.test(newInformationIndicator(null).detail + newInformationIndicator(3).detail), 'nothing apologises for a capability that now exists')

// The resting puck's one count (the owner's alternative, ent-cdfc682f62eb, to
// the mockup's satellite ring at rest). The new-item total is a real read of
// the record and wins whenever there is one; with no baseline to count from the
// badge falls back to what is actually held and says so. Nothing is ever
// invented, and nothing is drawn when there is nothing to report.
eq(restingCount(5, 40).value, '5', 'a new-item total is what the resting badge shows')
eq(restingCount(5, 40).kind, 'new', 'the badge names the new-item total as the thing it counts')
ok(restingCount(5, 40).detail.includes('5 new items'), 'the new-item badge explains its number in full')
eq(restingCount(1, 40).value, '1', 'a single new item still counts')
ok(restingCount(1, 40).detail.includes('1 new item '), 'one new item is said in the singular')
eq(restingCount(0, 40).value, null, 'nothing new draws no badge, rather than a 0 on the puck')
eq(restingCount(0, 40).kind, 'new', 'a known-empty new-item total is still a new-item answer, not a fallback')
ok(restingCount(0, 40).detail.toLowerCase().includes('nothing new'), 'an empty new-item total says so for a reader')
eq(restingCount(120, null).value, '99+', 'a long count is capped so it cannot widen the puck')
ok(restingCount(120, null).detail.includes('120 new items'), 'the capped badge keeps the exact number in its explanation')

eq(restingCount(null, 7).value, '7', 'with no new-item total the badge falls back to what is held')
eq(restingCount(null, 7).kind, 'collected', 'the fallback names itself collected, never new')
ok(restingCount(null, 7).detail.includes('7 collected items'), 'the fallback says what its number counts')
ok(restingCount(null, 7).detail.includes('not known on this device'), 'the fallback states why it is not a new-item count, without apologising for a missing capability')
ok(!/\byet\b/i.test(restingCount(null, 7).detail), 'the fallback no longer promises a count that now exists')
eq(restingCount(undefined, 1).detail.includes('1 collected item'), true, 'one collected item is said in the singular')
eq(restingCount(null, 0).value, null, 'an empty collection draws no badge')
ok(restingCount(null, 0).detail.includes('0 collected items'), 'an actually-read empty collection reports 0 truthfully')
eq(restingCount(null, null).value, null, 'an unread Magnet draws no badge')
ok(!restingCount(null, null).detail.includes('collected items'), 'before a read the count is unknown and is not invented as 0')
ok(![restingCount(null, null), restingCount(null, 7), restingCount(0, 40)].some((r) => /\bunread\b/i.test(r.detail)), 'the resting badge never speaks of unread')

const built = magnetIndicators({ postsSourceTally: 7, filesLoaded: 2, filesKnown: true, filesPartial: false, newItems: 3 })
eq(built.map((i) => i.key), ['posts', 'files', 'perspectives', 'new'], 'indicator set is exactly posts, files, perspectives, new')
ok(built.every((i) => i.tab === 'Posts' || i.tab === 'Files' || i.tab === 'Perspectives' || i.tab === 'All'), 'every indicator names an existing tab to open')
eq(built[3].value, '3', 'the ring carries the new-item count it was given, not a placeholder')
eq(magnetIndicators({ postsSourceTally: 7, filesLoaded: 2, filesKnown: true, filesPartial: false, newItems: null })[3].value, null, 'an unknown new-item count stays unavailable in the ring')

// Rendered presentation: indicators appear with the open card, stay off the resting puck.
let snap: MagnetSnapshot = {
  title: 'Colony fixture', loading: false, results: [{ kind: 'post', id: 'p1', number: 1 }, { kind: 'file', id: 'f1', value: { title: 'a.txt' } }],
  x: 12, y: 12, tab: 'All', open: false, wide: false, overlay: null, places: emptyPlaces(),
  query: '', searchType: 'All', searchTarget: null, searchListScroll: 0, lens: null,
  returnRoute: null, settingsReturn: null, context: null, contextSuppressed: false, carried: null,
  status: 'partial', next: 'more', summary: { key: 'conversation:ent-source', status: 'partial', summary: { posts: 19 } },
}
const calls: string[] = []
const resource = {
  id: 'qm-ind', brainKey: 'fixture', saved: { id: 'mag-fixture', name: 'Colony fixture', config: { id: 'mag-fixture', sources: [{ kind: 'conversation', conversation: 'ent-source' }], selection: {} } },
  snapshot: () => snap, subscribe: () => () => {}, update: (c: Partial<MagnetSnapshot>) => { snap = { ...snap, ...c }; calls.push(JSON.stringify(c)) },
  read: async () => {}, cancel: () => {}, dispose: () => {},
} as unknown as MagnetResource
const restHtml = renderToStaticMarkup(createElement(Magnet, { resource, onExpand: () => {}, onCollapse: () => {} }))
ok(!restHtml.includes('q2-magnet-indicators'), 'resting puck stays compact: the ring appears only with the open card')
ok(!restHtml.includes('q2-magnet-count'), 'an unread Magnet puts no count on its puck')
ok(restHtml.includes('Nothing has been read into this Magnet yet'), 'the unread puck says so in its own accessible name, rather than showing 0')

// The resting puck carries one count once a read has returned: the badge, and
// the same number explained in the puck's accessible name. Still no ring.
snap = { ...snap, activation: null }
const countedHtml = renderToStaticMarkup(createElement(Magnet, { resource, onExpand: () => {}, onCollapse: () => {} }))
ok(countedHtml.includes('q2-magnet-count'), 'a read Magnet shows one count badge on the resting puck')
ok(countedHtml.includes('q2-magnet-count-collected'), 'the badge names what it counts, so a collected total is not read as a new-item one')
ok(!countedHtml.includes('q2-magnet-count-new'), 'with no baseline recorded for this viewer, nothing is claimed as new')
ok(countedHtml.includes('>2</span>'), 'the badge is the count of what this Magnet holds')
ok(countedHtml.includes('2 collected items; how many of them are new is not known on this device'), 'the resting puck explains its number and why it is not a new-item count')
ok(!countedHtml.includes('q2-magnet-indicators'), 'the one count replaces the ring at rest; the ring still waits for the open card')
ok(!/\bunread\b|\bnew items\b/i.test(countedHtml), 'no new-item count is fabricated on the resting puck')

snap = { ...snap, open: true }
const openHtml = renderToStaticMarkup(createElement(Magnet, { resource, onExpand: () => {}, onCollapse: () => {} }))
ok(openHtml.includes('q2-magnet-indicators'), 'the open card shows the indicator ring')
ok(openHtml.includes('Posts: 19 collected posts in the collection shown'), 'the posts tally names the collection it counted')
ok(openHtml.includes('Files: 1 collected '), 'the files indicator says the collection is partial')
ok(openHtml.includes('No question kept for this Magnet yet'), 'Perspectives indicator reports the count read from its own store, wired like the other counts')
ok(openHtml.includes('New items unavailable'), 'with no baseline the new-item indicator says so, rather than showing a number')
ok(!/50 new|6 changed|\bunread\b/i.test(openHtml), 'no fabricated unread/new counts appear anywhere in the rendered card')

/* THE COUNT ITSELF, from the record (`collection/new`). A static render never
 * runs the frame's effects, so the read the frame takes is exercised here on the
 * resource that takes it: a baseline this viewer was shown, the server's own
 * diff, and -- the part that matters for a count nobody can check by eye -- a
 * refusal or a baseline-less Magnet staying UNKNOWN rather than becoming 0. */
const brainKey = 'origin|fixture|brain-indicators'
const mem = new Map<string, string>()
Object.defineProperty(globalThis, 'localStorage', { configurable: true, value: {
  getItem: (k: string) => mem.get(k) ?? null, setItem: (k: string, v: string) => mem.set(k, v),
  removeItem: (k: string) => mem.delete(k), clear: () => mem.clear() } })
binding.saw('brain-indicators@instance-one')
const config: MagnetConfig = {
  id: 'mag-counting', sources: [{ kind: 'conversation', conversation: 'ent-source111111' }], selection: {},
  collection: { mode: 'one-time' }, synthesis: { mode: 'manual' }, activation: { mode: 'manual' },
  processing: { operations: [{ op: 'extract' }] },
  notifications: { newItems: false, changes: false, failures: false },
  presentation: { renderer: 'disc' },
}
const asked: string[] = []
let answer: { status: number; body: unknown } = { status: 200, body: { magnet: 'mag-counting', batch: 'adm-bbbbbbbbbbbb', new_count: 4, new: ['ent-a', 'ent-b', 'ent-c', 'ent-d'] } }
const counting = createMagnetResource({ id: 'qm-counting', brainKey,
  saved: { id: 'mag-counting', name: 'Counting', config },
  get: async (path: string) => { asked.push(path); return answer } })
eq(counting.shownBatch(), null, 'a Magnet this viewer has never opened has no baseline')
eq(await counting.newItemCount(), null, 'with no baseline nothing is asked of the server and the count stays unknown')
eq(asked.length, 0, 'an absent baseline is answered here, not by asking the server to treat everything as new')
counting.markShown('not-a-batch')
eq(counting.shownBatch(), null, 'only a recorded batch reference becomes a baseline')
counting.markShown('adm-aaaaaaaaaaaa')
eq(counting.shownBatch(), 'adm-aaaaaaaaaaaa', 'the batch the card was opened on is the baseline')
eq(await counting.newItemCount(), 4, 'the badge is fed the server’s own new-item count')
eq(asked[0], '/fluid/api/magnets/mag-counting/collection/new?since=adm-aaaaaaaaaaaa', 'the count is asked for against that exact baseline')
answer = { status: 200, body: { magnet: 'mag-counting', batch: 'adm-bbbbbbbbbbbb', new_count: 0, new: [] } }
eq(await counting.newItemCount(), 0, 'nothing changed is a real zero, which the badge draws as no badge')
answer = { status: 404, body: { error: 'adm-aaaaaaaaaaaa' } }
eq(await counting.newItemCount(), null, 'a refused baseline is unknown, never zero')
answer = { status: 200, body: { magnet: 'mag-elsewhere', new_count: 9 } }
eq(await counting.newItemCount(), null, 'a count for another Magnet is not this Magnet’s')
answer = { status: 200, body: { magnet: 'mag-counting', new_count: -1 } }
eq(await counting.newItemCount(), null, 'an impossible count is refused rather than shown')
answer = { status: 200, body: { magnet: 'mag-counting', new_count: 2.5 } }
eq(await counting.newItemCount(), null, 'a count that is not a whole number is refused')
/* The baseline is this device's, kept beside the reading position, so the count
 * survives a reload without the server holding anything per viewer. */
eq(loadShownBatch(brainKey, 'mag-counting'), 'adm-aaaaaaaaaaaa', 'the baseline is persisted for this Brain and Magnet')
eq(createMagnetResource({ id: 'qm-counting-2', brainKey, saved: { id: 'mag-counting', name: 'Counting', config },
  get: async () => answer }).shownBatch(), 'adm-aaaaaaaaaaaa', 'a reopened card recovers the baseline it was shown')

console.log(`Quiet Magnet indicators: ${checks} passed, 0 failed, 0 skipped, 0 errors`)
