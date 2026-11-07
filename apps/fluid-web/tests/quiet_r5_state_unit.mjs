/* QUIET CHAT ROUND 5, PACKAGE S: BROWSER STATE AND DESTINATIONS.
 *
 * What this suite is for: S is the foundation eight other packages are
 * written against, and the two things that are expensive to repair once they
 * are depended on are the STORAGE CONTRACT and the DESTINATION CONTRACT. So
 * the cases here are the ones that would otherwise be found by somebody
 * losing an arrangement:
 *
 *  - one envelope per Brain AND per origin conversation, with no bleed;
 *  - a patch moves what it names and nothing else;
 *  - malformed, refused and unknown-version storage are harmless, and are
 *    NOT overwritten by merely starting up;
 *  - `touched` and the resolved-but-unnamed 'local' Brain both round-trip,
 *    and a PENDING Brain writes no key at all;
 *  - the address's Page suffix goes after every topic and turn pair, an
 *    explicit address beats a saved selection, and an absent Page cannot be
 *    selected;
 *  - inside Quiet's scope one destination change reports exactly ONE intent
 *    and pushes NOTHING onto Fluid's nav stack, and applying the hash back
 *    reports nothing at all;
 *  - with no options and no scope, Fluid behaves exactly as it did.
 *
 * F21: this is a .mjs suite and is deliberately not in the typechecked test
 * project. Holder precedence itself is W1's implementation: what is checked
 * here is the CHOICE S hands it (`chooseSnapshot`).
 */
import { registerHooks } from 'node:module'
import { readFileSync, existsSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import assert from 'node:assert/strict'
import test from 'node:test'
import ts from '../node_modules/typescript/lib/typescript.js'

registerHooks({
  resolve(specifier, context, next) {
    if (specifier.startsWith('.')) {
      if (/\.css$/.test(specifier)) {
        return { url: new URL(specifier, context.parentURL).href, shortCircuit: true }
      }
      for (const suffix of ['', '.ts', '.tsx', '/index.ts']) {
        const url = new URL(specifier + suffix, context.parentURL)
        if (suffix && existsSync(fileURLToPath(url))) return { url: url.href, shortCircuit: true }
      }
    }
    return next(specifier, context)
  },
  load(url, context, next) {
    if (/\.css$/.test(url)) return { format: 'module', shortCircuit: true, source: 'export {}' }
    if (/\.tsx?$/.test(url)) return {
      format: 'module', shortCircuit: true,
      source: ts.transpileModule(readFileSync(fileURLToPath(url), 'utf8'), {
        compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX },
      }).outputText,
    }
    return next(url, context)
  },
})

/* -- a browser's two stores, before anything that reads them is imported --- */

/** One storage, swappable, and able to refuse -- which is a real browser
 *  state (private mode, a quota, a policy) and not an error case. */
class Fake {
  constructor() { this.map = new Map(); this.refuse = false }
  getItem(k) { return this.map.has(k) ? this.map.get(k) : null }
  setItem(k, v) {
    if (this.refuse) throw new Error('refused')
    this.map.set(k, String(v))
  }
  removeItem(k) { this.map.delete(k) }
  keys() { return [...this.map.keys()] }
  clear() { this.map.clear(); this.refuse = false }
}

const localFake = new Fake()
const sessionFake = new Fake()
globalThis.localStorage = {
  getItem: (k) => localFake.getItem(k),
  setItem: (k, v) => localFake.setItem(k, v),
  removeItem: (k) => localFake.removeItem(k),
}
globalThis.sessionStorage = {
  getItem: (k) => sessionFake.getItem(k),
  setItem: (k, v) => sessionFake.setItem(k, v),
  removeItem: (k) => sessionFake.removeItem(k),
}

const bookmarks = await import('../src/quiet/workspace/bookmarks.ts')
const {
  LOCAL_BRAIN, chooseSnapshot, emptyEnvelope, flushWorkspace, forgetWorkspace,
  hasWorkspace, patchWorkspace, readEnvelope, readTravelBookmark, readWorkspace,
  travelKey, workspaceKey, writeTravelBookmark,
} = bookmarks
const { CONVERSATION_PAGE, readQuietLocation, resumeLocation, writeQuietLocation } =
  await import('../src/quiet/pages/location.ts')
const { href } = await import('../src/quiet/model.ts')
const { readAddress } = await import('../src/address.ts')
const { toLayout } = await import('../src/fluid/workspace/place.ts')
const { keepSlot } = await import('../src/fluid/workspace/tree.ts')
const nav = await import('../src/fluid/nav.ts')
const { toastSnapshot, dismissToast } = await import('../src/fluid/frame/toasts.ts')

/* -- fixtures -------------------------------------------------------------- */

const zone = (id, items = [], show = 'objects') =>
  ({ type: 'zone', id, show, name: id, slot: keepSlot(items) })

/** A layout Fluid's own `fromLayout` accepts, which is what S validates by. */
const LAYOUT = toLayout({ tree: zone('post'), pages: [{ id: 'page-1', title: 'One', tree: zone('p1') }] })

const reading = (post, offset, topic = null) => ({
  flow: { topic, batch: { before: 30 }, anchor: { post, offset } },
  thread: null,
  margin: { reading: 'topics', searchOpen: false, query: '', scrollByReading: { topics: 12 } },
})

const seed = () => ({
  ...emptyEnvelope(),
  touched: true,
  selectedPage: 'page-1',
  layout: LAYOUT,
  destinations: { 'page-1': { kind: 'workspace' } },
  readings: { 'this-post': reading('a1', -40), 'page-1': reading('b2', 12, 't1') },
  rooms: { 'page-1': { mode: 'panes', readingPx: 640 } },
})

const fresh = () => {
  forgetWorkspace()
  localFake.clear()
  sessionFake.clear()
}

const put = (brain, conversation, envelope) => {
  localFake.map.set(workspaceKey(brain, conversation), JSON.stringify(envelope))
}

/* -- the envelope, per Brain and per origin -------------------------------- */

test('an envelope belongs to one Brain and one origin conversation, and nothing bleeds', () => {
  fresh()
  patchWorkspace({ brain: 'b1', conversation: 'c1' }, { selectedPage: 'page-1' })
  patchWorkspace({ brain: 'b2', conversation: 'c1' }, { selectedPage: 'page-2' })
  patchWorkspace({ brain: 'b1', conversation: 'c2' }, { selectedPage: 'page-3' })

  assert.equal(readWorkspace({ brain: 'b1', conversation: 'c1' }).selectedPage, 'page-1')
  assert.equal(readWorkspace({ brain: 'b2', conversation: 'c1' }).selectedPage, 'page-2')
  assert.equal(readWorkspace({ brain: 'b1', conversation: 'c2' }).selectedPage, 'page-3')

  assert.deepEqual(localFake.keys().sort(), [
    workspaceKey('b1', 'c1'), workspaceKey('b1', 'c2'), workspaceKey('b2', 'c1'),
  ].sort())

  /* and read back from storage alone, as a new session would */
  forgetWorkspace()
  assert.equal(readWorkspace({ brain: 'b2', conversation: 'c1' }).selectedPage, 'page-2')
  assert.equal(readWorkspace({ brain: 'b1', conversation: 'c1' }).selectedPage, 'page-1')
})

test('the key separates a Brain and a conversation that hold a colon', () => {
  assert.equal(
    workspaceKey('a:b', 'c:d'),
    'mentis:quiet:workspace:v1:a%3Ab:c%3Ad',
    'an unencoded id could reach across into the next field',
  )
})

/* -- a patch moves what it names, and nothing else ------------------------- */

test('patching one reading leaves the layout, the Page list and the other readings alone', () => {
  fresh()
  const id = { brain: 'b1', conversation: 'c1' }
  put('b1', 'c1', seed())
  const before = readWorkspace(id)
  assert.ok(before, 'the seeded envelope is valid')

  const next = patchWorkspace(id, {
    readings: { 'page-1': { ...before.readings['page-1'], margin: { reading: 'carried', searchOpen: true, query: 'seals', scrollByReading: { carried: 90 } } } },
  })
  assert.deepEqual(next.layout, LAYOUT, 'the layout is untouched by a margin change')
  assert.deepEqual(next.readings['this-post'], before.readings['this-post'], "another Page's reading is untouched")
  assert.deepEqual(next.rooms, before.rooms, 'the rooms are untouched')
  assert.deepEqual(next.destinations, before.destinations, 'the destinations are untouched')
  assert.equal(next.selectedPage, 'page-1', 'the selected Page is untouched')
  assert.equal(next.touched, true, 'touched is untouched')
  assert.equal(next.readings['page-1'].margin.query, 'seals')
  assert.deepEqual(next.readings['page-1'].flow, before.readings['page-1'].flow, 'the flow is untouched by a margin change')
})

test('a room merges partially: changing the mode keeps the dragged width', () => {
  fresh()
  const id = { brain: 'b1', conversation: 'c1' }
  put('b1', 'c1', seed())
  const next = patchWorkspace(id, { rooms: { 'page-1': { mode: 'board' } } })
  assert.deepEqual(next.rooms['page-1'], { mode: 'board', readingPx: 640 })
})

test('an explicit null removes one map entry and leaves its neighbours', () => {
  fresh()
  const id = { brain: 'b1', conversation: 'c1' }
  put('b1', 'c1', seed())
  const next = patchWorkspace(id, { readings: { 'page-1': null } })
  assert.equal(next.readings['page-1'], undefined)
  assert.ok(next.readings['this-post'], 'the other reading stayed')
})

test('a patch merges against the latest stored copy, so another tab is not undone', () => {
  fresh()
  const id = { brain: 'b1', conversation: 'c1' }
  put('b1', 'c1', seed())
  readWorkspace(id)
  /* another tab wrote while this one held its copy */
  put('b1', 'c1', { ...seed(), selectedPage: 'page-9' })
  const next = patchWorkspace(id, { touched: false })
  assert.equal(next.selectedPage, 'page-9', "the other tab's field survived")
  assert.equal(next.touched, false, 'and this tab\'s own change holds for its own field')
})

test('touched round-trips, and is the only thing a touched patch changes', () => {
  fresh()
  const id = { brain: 'b1', conversation: 'c1' }
  patchWorkspace(id, { selectedPage: 'page-1', layout: LAYOUT })
  patchWorkspace(id, { touched: true })
  forgetWorkspace()
  const back = readWorkspace(id)
  assert.equal(back.touched, true)
  assert.equal(back.selectedPage, 'page-1')
  assert.deepEqual(back.layout, LAYOUT)
  patchWorkspace(id, { touched: false })
  forgetWorkspace()
  assert.equal(readWorkspace(id).touched, false)
})

test('a coalesced change is held until it is flushed', () => {
  fresh()
  const id = { brain: 'b1', conversation: 'c1' }
  patchWorkspace(id, { selectedPage: 'page-1' })
  patchWorkspace(id, { readings: { 'page-1': reading('b2', 300) } }, { coalesce: true })
  assert.equal(
    readEnvelope(localFake.getItem(workspaceKey('b1', 'c1'))).readings['page-1'],
    undefined,
    'a scroll is not written per pixel',
  )
  flushWorkspace(id)
  assert.equal(
    readEnvelope(localFake.getItem(workspaceKey('b1', 'c1'))).readings['page-1'].flow.anchor.offset,
    300,
    'leaving commits it',
  )
})

/* -- storage that cannot be read, or cannot be written --------------------- */

test('malformed storage reads as no snapshot and is NOT overwritten on initialisation', () => {
  fresh()
  const id = { brain: 'b1', conversation: 'c1' }
  const key = workspaceKey('b1', 'c1')
  localFake.map.set(key, '{not json at all')
  assert.equal(readWorkspace(id), null, 'nothing to resume from')
  assert.equal(hasWorkspace(id), false)
  assert.equal(localFake.getItem(key), '{not json at all',
    'a reader who comes back to a newer build still has their characters')
})

test('an unknown envelope version reads as no snapshot and is left alone', () => {
  fresh()
  const id = { brain: 'b1', conversation: 'c1' }
  const key = workspaceKey('b1', 'c1')
  const future = JSON.stringify({ version: 2, selectedPage: 'page-1', touched: true })
  localFake.map.set(key, future)
  assert.equal(readWorkspace(id), null)
  assert.equal(localFake.getItem(key), future)
})

test('an envelope whose layout alone cannot be read keeps the rest of itself', () => {
  fresh()
  const id = { brain: 'b1', conversation: 'c1' }
  put('b1', 'c1', { ...seed(), layout: { format: 'mentis.fluid-arrangement', version: 99, tree: zone('x') } })
  const got = readWorkspace(id)
  assert.ok(got, 'the envelope is still an envelope')
  assert.equal(got.layout, null, 'the arrangement it cannot read is absent, not guessed at')
  assert.equal(got.readings['page-1'].flow.anchor.post, 'b2', 'the reading is still theirs')
  assert.equal(got.rooms['page-1'].mode, 'panes')
})

test('a reading, a room and a destination that do not validate are left out, not defaulted', () => {
  fresh()
  const id = { brain: 'b1', conversation: 'c1' }
  put('b1', 'c1', {
    ...emptyEnvelope(),
    readings: {
      good: reading('a1', 10),
      'bad-offset': { flow: { topic: null, batch: {}, anchor: { post: 'a', offset: Infinity } }, thread: null, margin: {} },
      'bad-batch': { flow: { topic: null, batch: { before: 'lots' }, anchor: null }, thread: null, margin: {} },
      'half-thread': { flow: { topic: null, batch: {}, anchor: null }, thread: { root: 'r' }, margin: {} },
    },
    rooms: { good: { mode: 'panes', readingPx: 700 }, bad: { mode: 'flying', readingPx: 700 } },
    destinations: { good: { kind: 'workspace' }, bad: { kind: 'deep-dive', conversation: 'x' } },
  })
  const got = readWorkspace(id)
  assert.deepEqual(Object.keys(got.readings), ['good', 'bad-offset'],
    'a reading whose ANCHOR alone is unreadable is still a reading')
  assert.equal(got.readings['bad-offset'].anchor, undefined)
  assert.equal(got.readings['bad-offset'].flow.anchor, null,
    'an offset that is not a finite number is no anchor, and nothing is invented for it')
  assert.deepEqual(Object.keys(got.rooms), ['good'])
  assert.deepEqual(Object.keys(got.destinations), ['good'])
  assert.equal(got.readings.good.margin.reading, 'topics')
  assert.equal(got.readings.good.margin.scrollByReading.topics, 12)
})

test('a margin naming a reading that does not exist keeps no reading at all', () => {
  fresh()
  const id = { brain: 'b1', conversation: 'c1' }
  put('b1', 'c1', {
    ...emptyEnvelope(),
    readings: { p: { flow: { topic: null, batch: {}, anchor: null }, thread: null, margin: { reading: 'invented', query: 7, scrollByReading: { invented: 5, topics: 'far' } } } },
  })
  const margin = readWorkspace(id).readings.p.margin
  assert.equal(margin.reading, null)
  assert.equal(margin.query, '', 'a query that is not words is no query')
  assert.deepEqual(margin.scrollByReading, {})
})

test('refused storage leaves a usable session in memory', () => {
  fresh()
  const id = { brain: 'b1', conversation: 'c1' }
  localFake.refuse = true
  const next = patchWorkspace(id, { selectedPage: 'page-1', touched: true })
  assert.equal(next.selectedPage, 'page-1', 'the session still remembers')
  assert.equal(readWorkspace(id).touched, true)
  assert.equal(hasWorkspace(id), false, 'and does not claim to have been stored')
  assert.deepEqual(localFake.keys(), [], 'nothing was written')
  localFake.refuse = false
})

/* -- which Brain (F10) ----------------------------------------------------- */

test('a pending Brain writes no key, and what it held is replayed once the Brain is known', () => {
  fresh()
  const pending = { brain: null, conversation: 'c9' }
  patchWorkspace(pending, { selectedPage: 'page-1' })
  patchWorkspace(pending, { touched: true })
  assert.deepEqual(localFake.keys(), [], 'a key naming an unknown Brain belongs to nobody')
  assert.equal(readWorkspace(pending).selectedPage, 'page-1', 'but the session works')
  assert.equal(hasWorkspace(pending), false)

  const resolved = { brain: 'b1', conversation: 'c9' }
  const got = readWorkspace(resolved)
  assert.equal(got.selectedPage, 'page-1', 'what was done while pending is not lost')
  assert.equal(got.touched, true)
  assert.deepEqual(localFake.keys(), [workspaceKey('b1', 'c9')], 'and is written once, under the real Brain')
})

test("a Brain that resolved without a corpus_id is the literal 'local', which is not the pending one", () => {
  fresh()
  assert.equal(LOCAL_BRAIN, 'local')
  const unnamed = { brain: LOCAL_BRAIN, conversation: 'c1' }
  patchWorkspace(unnamed, { selectedPage: 'page-1', touched: true })
  assert.deepEqual(localFake.keys(), [workspaceKey('local', 'c1')])
  forgetWorkspace()
  const back = readWorkspace(unnamed)
  assert.equal(back.selectedPage, 'page-1')
  assert.equal(back.touched, true)
  assert.equal(
    readWorkspace({ brain: null, conversation: 'c1' }),
    null,
    "a pending identity does not read 'local''s envelope",
  )
})

/* -- the travelling floats, per Brain and per browser ---------------------- */

test('pinned travelling floats are mirrored per Brain, outside every envelope', () => {
  fresh()
  const float = { id: 'f1', zone: zone('object-zone', ['live:p:one'], 'objects'), x: 10, y: 20, w: 300, h: 200, pinned: true }
  writeTravelBookmark('b1', [float])
  assert.deepEqual(localFake.keys(), [travelKey('b1')], 'and not into any origin envelope')
  const back = readTravelBookmark('b1')
  assert.equal(back.length, 1)
  assert.equal(back[0].id, 'f1')
  assert.equal(back[0].pinned, true)
  assert.deepEqual(readTravelBookmark('b2'), [], 'another Brain has its own')
  writeTravelBookmark(null, [float])
  assert.deepEqual(localFake.keys(), [travelKey('b1')], 'a pending Brain writes nothing')
})

test('a travelling float this build cannot read is left out rather than guessed at', () => {
  fresh()
  localFake.map.set(travelKey('b1'), JSON.stringify([{ id: 'f1' }, 'nonsense']))
  assert.deepEqual(readTravelBookmark('b1'), [])
  localFake.map.set(travelKey('b1'), 'not json')
  assert.deepEqual(readTravelBookmark('b1'), [])
})

/* -- which browser copy the Holder enters (F9) ----------------------------- */

test('the same-tab session copy wins, with its own touched state', () => {
  fresh()
  const id = { brain: 'b1', conversation: 'c1' }
  const sessionLayout = toLayout({ tree: zone('session-post'), pages: [] })
  put('b1', 'c1', { ...seed(), touched: false })
  sessionFake.map.set('mentis.fluid.arr:c1', JSON.stringify(sessionLayout))
  sessionFake.map.set('mentis.fluid.arr:c1:changed', '1')
  const chose = chooseSnapshot(id)
  assert.equal(chose.from, 'session')
  assert.deepEqual(chose.layout, sessionLayout)
  assert.equal(chose.touched, true, "the session copy's own touched state, not the envelope's")
  assert.equal(chose.protect, true)
})

test('a new session with no tab copy enters the durable layout, protected even when untouched', () => {
  fresh()
  const id = { brain: 'b1', conversation: 'c1' }
  put('b1', 'c1', { ...seed(), touched: false })
  const chose = chooseSnapshot(id)
  assert.equal(chose.from, 'local')
  assert.deepEqual(chose.layout, LAYOUT)
  assert.equal(chose.touched, false)
  assert.equal(chose.protect, true,
    'a reader who changed nothing this time still chose this arrangement')
})

test('an unreadable session copy falls through to the durable one; neither, and there is no snapshot', () => {
  fresh()
  const id = { brain: 'b1', conversation: 'c1' }
  sessionFake.map.set('mentis.fluid.arr:c1', '{half')
  put('b1', 'c1', seed())
  assert.equal(chooseSnapshot(id).from, 'local')

  fresh()
  assert.equal(chooseSnapshot({ brain: 'b1', conversation: 'c1' }), null)
  put('b1', 'c1', { ...emptyEnvelope(), selectedPage: 'page-1' })
  forgetWorkspace()
  assert.equal(
    chooseSnapshot({ brain: 'b1', conversation: 'c1' }),
    null,
    'an envelope with no layout is a bookmark, not an arrangement to enter',
  )
})

/* -- the address ----------------------------------------------------------- */

test('the Page suffix is written after every topic and turn pair, and omitted for Conversation', () => {
  assert.equal(
    writeQuietLocation({ originConversation: 'c1', topic: 't1', turn: 'u1', page: 'page-2' }),
    '#/c/c1/t/t1/turn/u1/qpage/page-2',
  )
  assert.equal(
    writeQuietLocation({ originConversation: 'c1', topic: null, turn: null, page: 'page-2' }),
    '#/c/c1/qpage/page-2',
    'absent pairs are omitted',
  )
  assert.equal(
    writeQuietLocation({ originConversation: 'c1', topic: 't1', turn: null, page: CONVERSATION_PAGE }),
    '#/c/c1/t/t1',
    'Conversation adds no suffix, so every link already sent still reads the same',
  )
})

test('the suffix round-trips, and the shared reading of an address tolerates it unchanged', () => {
  const at = { originConversation: 'c1', topic: 't1', turn: 'u1', page: 'page-2' }
  const hash = writeQuietLocation(at)
  assert.deepEqual(readQuietLocation(hash), at)

  const shared = readAddress(hash)
  assert.equal(shared.conversation, 'c1')
  assert.equal(shared.topic, 't1')
  assert.equal(shared.turn, 'u1')
  assert.equal(shared.gov, null, 'a pair-aligned unknown suffix is skipped, not read as a lens')
})

test('ids literally spelled gov stay ids, with the Page suffix after them', () => {
  const hash = writeQuietLocation({ originConversation: 'gov', topic: 'gov', turn: 'gov', page: 'page-2' })
  assert.equal(hash, '#/c/gov/t/gov/turn/gov/qpage/page-2')
  assert.deepEqual(readQuietLocation(hash),
    { originConversation: 'gov', topic: 'gov', turn: 'gov', page: 'page-2' })
  assert.equal(readAddress(hash).gov, null, 'a Topic or a Turn spelled gov is an id, not a door')
  /* And in the suffix's own value position: Quiet mints `page-N`, so this is
     reachable only by hand, and the codec still reads it as the Page. */
  assert.equal(readQuietLocation('#/c/c1/qpage/gov').page, 'gov')
})

test('a hash naming no conversation names no Quiet destination', () => {
  assert.equal(readQuietLocation(''), null)
  assert.equal(readQuietLocation('#/brain'), null)
  assert.equal(readQuietLocation('#/c'), null)
  assert.deepEqual(readQuietLocation('#/c/c1'),
    { originConversation: 'c1', topic: null, turn: null, page: CONVERSATION_PAGE })
})

test('an explicit address beats the saved selection; a bare one resumes it', () => {
  const envelope = { ...emptyEnvelope(), selectedPage: 'page-1' }
  const pages = ['page-1', 'page-2']

  const bare = resumeLocation(readQuietLocation('#/c/c1'), envelope, pages)
  assert.equal(bare.from, 'bookmark')
  assert.equal(bare.location.page, 'page-1')

  const explicit = resumeLocation(readQuietLocation('#/c/c1/qpage/page-2'), envelope, pages)
  assert.equal(explicit.from, 'address')
  assert.equal(explicit.location.page, 'page-2', 'a link somebody sent is not redirected to a newer bookmark')

  const topicOnly = resumeLocation(readQuietLocation('#/c/c1/t/t1'), envelope, pages)
  assert.equal(topicOnly.from, 'address')
  assert.equal(topicOnly.location.page, CONVERSATION_PAGE,
    'anything explicit in the address is deliberate')

  const none = resumeLocation(readQuietLocation('#/c/c1'), null, [])
  assert.equal(none.from, 'default')
  assert.equal(none.location.page, CONVERSATION_PAGE)
})

test("a Page this browser does not have falls back to Conversation, visibly", () => {
  const envelope = { ...emptyEnvelope(), selectedPage: 'page-1' }
  const got = resumeLocation(readQuietLocation('#/c/c1/qpage/page-9'), envelope, ['page-1'])
  assert.equal(got.location.page, CONVERSATION_PAGE)
  assert.equal(got.unknownPage, 'page-9', 'and the reader can be told which Page that was')

  const stale = resumeLocation(readQuietLocation('#/c/c1'), { ...emptyEnvelope(), selectedPage: 'page-7' }, ['page-1'])
  assert.equal(stale.location.page, CONVERSATION_PAGE)
  assert.equal(stale.unknownPage, null, 'a closed Page in a bookmark is not an error to report')
})

/* -- the Page owner, and the conversation being read ----------------------- */

test('a link inside the reading keeps the origin and the Page; one leaving it does not', () => {
  const at = { originConversation: 'origin', page: 'page-1', effectiveConversation: 'child' }
  assert.equal(href('child', 't1', 'u1', at), '#/c/origin/t/t1/turn/u1/qpage/page-1',
    "the address names the Holder's owner, and the Page says what is read there")
  assert.equal(href('elsewhere', null, null, at), '#/c/elsewhere',
    'a link out of the effective conversation leaves the sequence normally')
  assert.equal(href('c1'), '#/c/c1', 'and with no location argument every existing call is unchanged')
  assert.equal(href('c1', 't1', 'u1'), '#/c/c1/t/t1/turn/u1')
})

/* -- destinations in fluid/nav.ts: the default, unscoped ------------------- */

test('with nothing scoped and no options, nav behaves exactly as it did', () => {
  nav.read('c1', 'p1', 1)
  assert.equal(nav.snapshot().conversation, 'c1')
  assert.equal(nav.snapshot().reading, 'p1')
  assert.equal(nav.snapshot().page, 'this-post')
  assert.equal(nav.snapshot().backLabel, null, 'arriving is not a step')

  nav.read('c1', 'p2', 2)
  assert.equal(nav.snapshot().backLabel, 'Back to #1')

  const made = nav.newPage()
  assert.equal(made, 'page-1')
  assert.equal(nav.snapshot().page, 'page-1')
  assert.equal(nav.snapshot().backLabel, 'Back to This post', 'a Page change is a step in Fluid')
  dismissToast()

  nav.showPage('ghost')
  assert.equal(nav.snapshot().page, 'page-1', 'an absent Page cannot be selected')

  nav.back()
  assert.equal(nav.snapshot().page, 'this-post')

  nav.openDetail({ kind: 'object', address: 'obj', anchor: { kind: 'post', id: 'p2' }, mode: 'over' })
  assert.equal(nav.snapshot().page, 'this-post', 'an object detail still returns to This post')
  nav.closeDetail()

  nav.showPage(made)
  assert.equal(nav.snapshot().page, made)
  nav.openDetail({ kind: 'object', address: 'obj', anchor: { kind: 'post', id: 'p2' }, mode: 'over' })
  assert.equal(nav.snapshot().page, 'this-post', 'and from a Page, as before')
  nav.closeDetail()
  nav.closePage(made)
})

test('a validated Page may be supplied to read, arrive and openDetail (F7)', () => {
  const made = nav.newPage()
  dismissToast()
  nav.read('c1', 'p3', { number: 3, page: made })
  assert.equal(nav.snapshot().page, made)
  nav.read('c1', 'p4', { number: 4, page: 'ghost' })
  assert.equal(nav.snapshot().page, made, 'an absent Page falls back rather than selecting nothing')
  nav.arrive('c1', 'p5', 5, { page: 'this-post' })
  assert.equal(nav.snapshot().page, 'this-post')
  nav.openDetail(
    { kind: 'object', address: 'obj', anchor: { kind: 'post', id: 'p5' }, mode: 'over' },
    { page: made },
  )
  assert.equal(nav.snapshot().page, made, 'the object-detail branch no longer forces This post')
  nav.closeDetail()
  nav.closePage(made)
})

/* -- the Deep dive Page's label and toast (F14) ---------------------------- */

test('a Deep dive Page says what it is, once, and keeps saying it when shortened', () => {
  const titleOf = (id) => nav.snapshot().pages.find((p) => p.id === id).title

  const one = nav.addPage('Door seals', { kind: 'deep-dive' })
  assert.equal(titleOf(one), 'Deep dive: Door seals')
  assert.equal(toastSnapshot().text, 'Deep dive opened as a page.')
  assert.equal(toastSnapshot().action.label, 'Undo')
  toastSnapshot().action.run()
  assert.equal(nav.snapshot().pages.some((p) => p.id === one), false, 'Undo takes it away')
  dismissToast()

  const twice = nav.addPage('Deep dive: Door seals', { kind: 'deep-dive' })
  assert.equal(titleOf(twice), 'Deep dive: Door seals', 'a returned name that already says it is not told twice')
  dismissToast()
  nav.closePage(twice)

  const long = nav.addPage('Why the door sticks to the frame every summer', { kind: 'deep-dive' })
  const label = titleOf(long)
  assert.ok(label.startsWith('Deep dive: '), 'the prefix survives shortening')
  assert.ok(label.endsWith('…'))
  assert.equal(label.length, 'Deep dive: '.length + 21)
  dismissToast()
  nav.closePage(long)

  const plain = nav.addPage('Notes')
  assert.equal(titleOf(plain), 'Notes')
  assert.equal(toastSnapshot().text, '"Notes" is now a page. This post kept its arrangement.',
    'an ordinary Page keeps the words it has always had')
  dismissToast()
  nav.closePage(plain)
})

/* -- Quiet's scope: one intent, no nav step, one guarded direction (F8) ---- */

test('in Quiet’s scope a destination change reports one intent and pushes no step', () => {
  const intents = []
  nav.read('cx', 'pa', 1)
  nav.read('cx', 'pb', 2)
  assert.equal(nav.snapshot().backLabel, 'Back to #1', 'a two-step history to tell a push from')

  const off = nav.hostExternalNavigation({
    page: (id) => intents.push({ kind: 'page', id }),
    read: (conversation, post, page) => intents.push({ kind: 'read', conversation, post, page }),
  })
  try {
    const made = nav.newPage()
    dismissToast()
    assert.equal(nav.snapshot().page, made)
    assert.deepEqual(intents, [{ kind: 'page', id: made }], 'exactly one destination intent')

    nav.back()
    assert.equal(nav.snapshot().reading, 'pa',
      'Back reached the step before the Page change: the Page change pushed nothing')

    /* reading in the same conversation: one intent, and applied here */
    intents.length = 0
    nav.read('cx', 'pc', 3)
    assert.deepEqual(intents, [{ kind: 'read', conversation: 'cx', post: 'pc', page: 'this-post' }])
    assert.equal(nav.snapshot().reading, 'pc')

    /* another conversation: reported, and NOT applied -- the host routes it
       through the working area's onNavigate before anything moves */
    intents.length = 0
    nav.read('other', 'pz', 4)
    assert.equal(intents.length, 1)
    assert.equal(intents[0].conversation, 'other')
    assert.equal(nav.snapshot().conversation, 'cx',
      'nothing inside the arrangement switches the conversation under the Holder')

    /* the other direction, guarded: applying the hash reports nothing */
    intents.length = 0
    nav.replayExternal(() => nav.arrive('other', 'pz', 4, { page: 'this-post' }))
    assert.deepEqual(intents, [], 'a replay is not a new intent')
    assert.equal(nav.snapshot().conversation, 'other')
    assert.equal(nav.snapshot().reading, 'pz')

    nav.replayExternal(() => nav.showPage(made))
    assert.deepEqual(intents, [])
    assert.equal(nav.snapshot().page, made)

    /* a nested call that names no Page stays on the active one */
    intents.length = 0
    nav.read('other', 'pz2', 5)
    assert.equal(nav.snapshot().page, made, 'reading a post is no reason to leave the Page')
    assert.deepEqual(intents, [{ kind: 'read', conversation: 'other', post: 'pz2', page: made }])

    nav.read('other', 'pz3', { number: 6, page: 'ghost' })
    assert.equal(nav.snapshot().page, made, 'an absent Page cannot be selected here either')

    nav.openDetail({ kind: 'object', address: 'obj', anchor: { kind: 'post', id: 'pz3' }, mode: 'over' })
    assert.equal(nav.snapshot().page, made, 'nor does opening an object leave it')
    nav.closeDetail()

    /* closing the Page being read is a destination change back to the
       conversation, and the hash has to say so */
    intents.length = 0
    nav.closePage(made)
    assert.deepEqual(intents, [{ kind: 'page', id: 'this-post' }])
    assert.equal(nav.snapshot().page, 'this-post')
  } finally {
    off()
  }
})

test('removing the adapter puts Fluid back exactly as it was', () => {
  const before = nav.snapshot().page
  assert.equal(before, 'this-post')
  nav.read('zzz', 'q1', 1)
  assert.equal(nav.snapshot().conversation, 'zzz', 'nothing is reported, and the change is applied again')
  const made = nav.newPage()
  dismissToast()
  assert.equal(nav.snapshot().backLabel, 'Back to This post', 'a Page change is a step again')
  nav.read('other', 'q2', 2)
  assert.equal(nav.snapshot().page, 'this-post',
    'and arriving in another conversation returns to This post as it always did')
  nav.closePage(made)
})
