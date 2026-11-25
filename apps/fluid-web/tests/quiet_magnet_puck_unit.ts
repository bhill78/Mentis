import assert from 'node:assert/strict'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import Magnet, { activityWords, cardGeometry, clampPuck } from '../src/quiet2/magnets/Magnet'
import { isCollectedFile, resultPreview, resultTitle } from '../src/quiet2/magnets/EvidenceViews'
import SettingsView from '../src/quiet2/magnets/SettingsView'
import { emptyPlaces } from '../src/quiet2/magnets/places'
import type { MagnetResource, MagnetSnapshot } from '../src/quiet2/magnets/contract'

let checks = 0
const eq = (a: unknown, b: unknown, why: string) => { assert.deepEqual(a, b, why); checks++ }
const ok = (a: unknown, why: string) => { assert.ok(a, why); checks++ }
eq(clampPuck(-20, -50, 900, 700), { x: 12, y: 12 }, 'negative positions clamp inside canvas')
eq(clampPuck(1000, 800, 900, 700), { x: 824, y: 624 }, 'bottom and right positions clamp')
eq(clampPuck(NaN, Infinity, 10, 10), { x: 12, y: 12 }, 'invalid positions never propagate')
for (const [width, height] of [[390, 720], [768, 500], [1440, 900]]) {
  for (const [x, y] of [[12, 12], [width - 76, 12], [12, height - 76], [width - 76, height - 76]]) {
    for (const wide of [false, true]) {
    const card = cardGeometry(x, y, width, height, wide)
    ok(x + card.left >= 12 && x + card.left + card.width <= width - 12, 'quick card fits horizontally at every edge')
    ok(y + card.top >= 12 && card.maxHeight <= height - 24, 'quick card is vertically bounded')
    ok(card.left <= 64 && card.left + card.width >= 0, 'quick card remains physically joined to puck')
    }
  }
}
eq(resultTitle({ kind: 'post', id: 'post', number: 22 }), 'Post #22', 'no fabricated post preview when routed page gives identity only')
eq(resultTitle({ kind: 'file', id: 'file', value: { title: 'retained-notes.md' } }), 'retained-notes.md', 'file title uses routed value')
eq(resultPreview({ kind: 'post', id: 'post', value: { text: 'a\n b'.repeat(100) } }).length, 180, 'plain preview bounded')
eq(isCollectedFile({ kind: 'attachment', id: 'attachment' }), true, 'attachment grouped with files')
eq(isCollectedFile({ kind: 'form', id: 'form' }), false, 'interactive blocks excluded')
eq(activityWords(undefined, 1000), 'Source activity unavailable.', 'missing activity never becomes zero')
eq(activityWords(2, 1000), 'Source activity is newer than this tab’s last-open time.', 'activity is qualified by local tab baseline')
eq(activityWords(2), 'Source activity reported; no last-open baseline in this tab yet.', 'missing baseline is explicit')
const s: MagnetSnapshot = { title: 'Colony fixture', loading: false, results: [], x: 12, y: 12, tab: 'Perspectives',
  open: true, wide: false, overlay: null, places: emptyPlaces(), query: '', searchType: 'All', searchTarget: null,
  searchListScroll: 0, lens: null, returnRoute: null, settingsReturn: null, context: null, contextSuppressed: false,
  carried: null }
const resource = { id: 'qm1', brainKey: 'fixture', saved: { id: 'mag-fixture', name: 'Colony fixture', config: { id: 'mag-fixture', sources: [{ kind: 'conversation', conversation: 'ent-source123' }], selection: {} } }, snapshot: () => s, subscribe: () => () => {}, update: () => {}, read: async () => {}, cancel: () => {}, dispose: () => {} } as unknown as MagnetResource
/** The approved card: tabs always present, and the one composer slot pinned
 *  under Conversation -- the only place any approved round-3 mockup gives a
 *  standing compose box. */
const conversing = { ...resource, snapshot: () => ({ ...s, tab: 'Conversation' }) } as unknown as MagnetResource
const html = renderToStaticMarkup(createElement(Magnet, { resource: conversing, onExpand: () => {}, onCollapse: () => {},
  footerComposer: createElement('form', null, createElement('textarea', { 'aria-label': 'Message inside this Magnet' })) }))
ok(html.includes('Perspectives'), 'Perspective tab remains available')
ok(!html.includes('50 new') && !html.includes('6 changed'), 'reference mockup totals absent')
ok(!html.includes('Collect now'), 'the frame draws no Collect now: collecting is Collection’s Collect manually row')
eq((html.match(/<textarea/g) ?? []).length, 1, 'the card renders exactly one composer textarea, in the footer slot')
ok(html.indexOf('<textarea') > html.indexOf('q2-magnet-view'), 'the one composer is below the view, in the footer slot')
for (const tab of ['Summary', 'All', 'Posts', 'Files', 'Perspectives']) {
  const each = renderToStaticMarkup(createElement(Magnet, { resource: { ...resource, snapshot: () => ({ ...s, tab }) } as unknown as MagnetResource,
    onExpand: () => {}, onCollapse: () => {}, footerComposer: createElement('form', null, createElement('textarea', null)) }))
  ok(!each.includes('<textarea'), `no composer is pinned under ${tab}`)
}
/** Workspace navigation lives in the Settings overlay, disclosed, with the
 *  removal relabelled: it is asked for explicitly and never stands in a view. */
const settings = renderToStaticMarkup(createElement(SettingsView, { resource, hasOwnConversation: true, canReset: true,
  onReset: () => {}, onRemove: () => {}, onSource: () => {}, onConversation: () => {}, onOrigin: () => {} }))
ok(settings.includes('<summary>Open outside this Magnet</summary>'), 'external navigation is disclosed, not standing')
ok(settings.includes('Source Conversation') && settings.includes('Full Conversation'), 'source and own navigation are explicitly labeled')
ok(settings.includes('Remove this Magnet from the workspace'), 'removal says it removes the Magnet, not that it closes the card')
ok(html.includes('aria-label="Close Magnet"') && !html.includes('Remove this Magnet'), 'the header × closes the card only')
console.log(`Quiet Magnet puck: ${checks} passed, 0 failed, 0 skipped, 0 errors`)
