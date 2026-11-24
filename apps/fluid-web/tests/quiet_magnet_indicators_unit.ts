import assert from 'node:assert/strict'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import Magnet from '../src/quiet2/magnets/Magnet'
import { emptyPlaces } from '../src/quiet2/magnets/places'
import { filesIndicator, magnetIndicators, newInformationIndicator, perspectivesIndicator, postsIndicator } from '../src/quiet2/magnets/indicators'
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

snap = { ...snap, open: true }
const openHtml = renderToStaticMarkup(createElement(Magnet, { resource, onExpand: () => {}, onCollapse: () => {} }))
ok(openHtml.includes('q2-magnet-indicators'), 'the open card shows the indicator ring')
ok(openHtml.includes('Posts: 19 posts retained in the most recent bounded batch'), 'retained posts tally names its batch scope')
ok(openHtml.includes('Files: 1 retained, batch partial'), 'files indicator names the retained partial batch')
ok(openHtml.includes('Perspectives unavailable'), 'Perspectives indicator names its unavailable explanation')
ok(openHtml.includes('New-item'), 'new-item indicator names its unavailable explanation')
ok(!/50 new|6 changed|\bunread\b/i.test(openHtml), 'no fabricated unread/new counts appear anywhere in the rendered card')

console.log(`Quiet Magnet indicators: ${checks} passed, 0 failed, 0 skipped, 0 errors`)
