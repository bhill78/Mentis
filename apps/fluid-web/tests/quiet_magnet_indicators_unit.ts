import assert from 'node:assert/strict'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import Magnet from '../src/quiet2/magnets/Magnet'
import { emptyPlaces } from '../src/quiet2/magnets/places'
import { filesIndicator, magnetIndicators, newInformationIndicator, perspectivesIndicator, postsIndicator, restingCount } from '../src/quiet2/magnets/indicators'
import type { MagnetResource, MagnetSnapshot } from '../src/quiet2/magnets/contract'

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

eq(newInformationIndicator().value, null, 'no new-item total exists to show')
ok(newInformationIndicator().detail.toLowerCase().includes('unavailable'), 'new-item indicator states unavailable')
ok(!newInformationIndicator().detail.toLowerCase().includes('unread'), 'new-item indicator never speaks of unread, only an absent total')

// The resting puck's one count (the owner's alternative, ent-cdfc682f62eb, to
// the mockup's satellite ring at rest). A new-item total wins when one exists;
// until the framework supplies one the badge falls back to what is actually
// held and says so. Nothing is ever invented, and nothing is drawn when there
// is nothing to report.
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
ok(restingCount(null, 7).detail.includes('not available'), 'the fallback states that no new-item count exists yet')
eq(restingCount(undefined, 1).detail.includes('1 collected item'), true, 'one collected item is said in the singular')
eq(restingCount(null, 0).value, null, 'an empty collection draws no badge')
ok(restingCount(null, 0).detail.includes('0 collected items'), 'an actually-read empty collection reports 0 truthfully')
eq(restingCount(null, null).value, null, 'an unread Magnet draws no badge')
ok(!restingCount(null, null).detail.includes('collected items'), 'before a read the count is unknown and is not invented as 0')
ok(![restingCount(null, null), restingCount(null, 7), restingCount(0, 40)].some((r) => /\bunread\b/i.test(r.detail)), 'the resting badge never speaks of unread')

const built = magnetIndicators({ postsSourceTally: 7, filesLoaded: 2, filesKnown: true, filesPartial: false })
eq(built.map((i) => i.key), ['posts', 'files', 'perspectives', 'new'], 'indicator set is exactly posts, files, perspectives, new')
ok(built.every((i) => i.tab === 'Posts' || i.tab === 'Files' || i.tab === 'Perspectives' || i.tab === 'All'), 'every indicator names an existing tab to open')

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
ok(!countedHtml.includes('q2-magnet-count-new'), 'nothing supplies a new-item total yet, so none is claimed')
ok(countedHtml.includes('>2</span>'), 'the badge is the count of what this Magnet holds')
ok(countedHtml.includes('2 collected items; a new-item count is not available yet'), 'the resting puck explains its number and what is still unavailable')
ok(!countedHtml.includes('q2-magnet-indicators'), 'the one count replaces the ring at rest; the ring still waits for the open card')
ok(!/\bunread\b|\bnew items\b/i.test(countedHtml), 'no new-item count is fabricated on the resting puck')

snap = { ...snap, open: true }
const openHtml = renderToStaticMarkup(createElement(Magnet, { resource, onExpand: () => {}, onCollapse: () => {} }))
ok(openHtml.includes('q2-magnet-indicators'), 'the open card shows the indicator ring')
ok(openHtml.includes('Posts: 19 collected posts in the collection shown'), 'the posts tally names the collection it counted')
ok(openHtml.includes('Files: 1 collected '), 'the files indicator says the collection is partial')
ok(openHtml.includes('Perspectives unavailable'), 'Perspectives indicator names its unavailable explanation')
ok(openHtml.includes('New-item'), 'new-item indicator names its unavailable explanation')
ok(!/50 new|6 changed|\bunread\b/i.test(openHtml), 'no fabricated unread/new counts appear anywhere in the rendered card')

console.log(`Quiet Magnet indicators: ${checks} passed, 0 failed, 0 skipped, 0 errors`)
