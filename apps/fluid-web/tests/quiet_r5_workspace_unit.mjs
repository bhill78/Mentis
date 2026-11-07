/* QUIET CHAT ROUND 5, PACKAGE W2: THE STAGE'S RUNTIME.
 *
 * What this suite is for: the two things in W2 that are decided OUTSIDE the
 * browser and are expensive to find later --
 *
 *  THE ENTRANCE AND ITS ORDER. `place.ts:969` makes a second `enter` for the
 *  same place a no-op, so whoever enters first decides what is drawn; and what
 *  travels has to be restored BEFORE that entrance or the Holder's own carry
 *  never sees it. The Page list is hydrated by the entrance itself, which is
 *  what `ready` reports, so these cases also pin down that `ready` is
 *  answerable in the same tick -- R's unknown-Page message is gated on it.
 *
 *  WHAT THE SCOPED ADAPTER DOES WITH WHAT NAV REPORTS. One intent per
 *  transition; a Page change carries the topic and post the address already
 *  has rather than clearing them; and a CROSS-CONVERSATION read or detail --
 *  which `fluid/nav.ts` reports and does not apply -- leaves through the
 *  working area's `onNavigate` with its whole target, with the detail held and
 *  not dropped (S review finding 6).
 *
 * The semantic touched flag is here too, because `changed()` is NOT it: after
 * a differing Brain response `changed()` is true while nothing of the
 * reader's was touched, and persisting that would mark every resumed place as
 * edited.
 *
 * F21: this is a .mjs suite and is deliberately not in the typechecked test
 * project. The rendered stage, the providers and the conversation stand-in are
 * checked in the browser (tests/test_quiet_r5_workspace_browser.py); the
 * Holder's own precedence is W1's suite.
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

class Store {
  constructor() { this.map = new Map(); this.refuseRead = false; this.refuseWrite = false }
  getItem(k) {
    if (this.refuseRead) throw new Error('refused')
    return this.map.has(String(k)) ? this.map.get(String(k)) : null
  }
  setItem(k, v) {
    if (this.refuseWrite) throw new Error('refused')
    this.map.set(String(k), String(v))
  }
  removeItem(k) { this.map.delete(String(k)) }
  clear() { this.map.clear(); this.refuseRead = false; this.refuseWrite = false }
}

const localFake = new Store()
const sessionFake = new Store()
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
globalThis.fetch = async () => { throw new Error('offline in a unit test') }
globalThis.window = { innerWidth: 1200, innerHeight: 800 }

const runtime = await import('../src/quiet/workspace/runtime.tsx')
const {
  awaitingDetail, enterPlace, externalNavigation, hostWorkingNavigation, placeKindOf,
  sequenceOf, touchedNow,
} = runtime
const place = await import('../src/fluid/workspace/place.ts')
const tree = await import('../src/fluid/workspace/tree.ts')
const nav = await import('../src/fluid/nav.ts')

const SESSION = 'mentis.fluid.arr:'
const TOUCHED = ':changed'

/** A place with these Pages, in the Holder's own tab representation -- built
 *  with Fluid's own tree helpers, so what is entered here is exactly what a
 *  browser would have kept and `fromLayout` reads it as it reads any other. */
const aLayout = (pages) => place.toLayout({
  tree: place.productStart().tree,
  pages: pages.map((p) => ({ id: p.id, title: p.title, tree: place.pageTree() })),
}, { tab: true })

/** A pinned travelling float, as `readTravel` validates one: a real zone of
 *  Fluid's own, pinned, with finite geometry. */
const aFloat = (id) => ({ id, zone: tree.zone(null), x: 20, y: 30, w: 320, h: 220, pinned: true })

let seq = 0
const freshPlace = () => `conv-w2-${(seq += 1)}`

/* -- which place, and what its sequence is called -------------------------- */

test('the kind of place is the one Fluid would have worked out itself', () => {
  assert.equal(placeKindOf('conv-1'), 'conversation')
  assert.equal(placeKindOf('stream'), 'stream')
  assert.equal(placeKindOf('wsp-a_place'), 'workspace')
  /* Supplied to Workspace rather than worked out twice: `enter` compares the
     kind as well as the key, so two answers would discard the entered copy. */
})

test('the sequence names Conversation and keeps every other title', () => {
  const got = sequenceOf([{ id: 'this-post' }, { id: 'page-2', title: 'Notes' }, { id: 'page-3' }])
  assert.deepEqual(got, [
    { id: 'this-post', title: 'Conversation' },
    { id: 'page-2', title: 'Notes' },
    { id: 'page-3', title: 'page-3' },
  ])
})

/* -- the entrance ---------------------------------------------------------- */

test('entering with a browser copy hydrates the Pages in the same tick', () => {
  const key = freshPlace()
  const layout = aLayout([{ id: 'page-7', title: 'Kept things' }])
  enterPlace(key, 'conversation', { from: 'local', layout, touched: false, protect: true })
  /* No awaiting anything: the Page list is nav's the moment `enter` returns,
     because `place.ts`'s `onArr` calls `setPages` inside its own `emit`. This
     is what makes `ready` answerable synchronously, and R's unknown-Page
     message reachable. */
  assert.deepEqual(nav.snapshot().pages.map((p) => p.id), ['this-post', 'page-7'])
  assert.equal(place.workspace.key, key)
  assert.equal(place.workspace.from, 'local')
  assert.equal(place.workspace.protectedSnapshot, true)
})

test('entering with no copy protects nothing and leaves Fluid its own order', () => {
  const key = freshPlace()
  enterPlace(key, 'conversation', null)
  assert.equal(place.workspace.key, key)
  assert.equal(place.workspace.protectedSnapshot, false)
  assert.notEqual(place.workspace.from, 'local')
})

test("this tab's own copy still wins a same-tab reload, with its touched state", () => {
  const key = freshPlace()
  sessionFake.setItem(SESSION + key, JSON.stringify(aLayout([{ id: 'page-9', title: 'This tab' }])))
  sessionFake.setItem(SESSION + key + TOUCHED, '1')
  /* The copy offered is a DIFFERENT one; F9 says the tab copy wins it. */
  enterPlace(key, 'conversation', {
    from: 'session', layout: aLayout([{ id: 'page-9', title: 'This tab' }]), touched: true, protect: true,
  })
  assert.equal(place.workspace.from, 'session')
  assert.equal(place.workspace.protectedSnapshot, true)
  assert.deepEqual(nav.snapshot().pages.map((p) => p.id), ['this-post', 'page-9'])
})

test('what travelled is put back BEFORE the entrance, so the carry sees it', () => {
  const key = freshPlace()
  enterPlace(key, 'conversation', null, [aFloat('f-1')])
  const back = place.workspace.exportLocalTravel()
  assert.equal(back.length, 1, 'the pinned travelling float was not restored')
  assert.equal(back[0].id, 'f-1')
  /* An unreadable mirror restores nothing rather than guessing. */
  const other = freshPlace()
  enterPlace(other, 'conversation', null, 'not floats at all')
  assert.deepEqual(place.workspace.exportLocalTravel(), [])
})

test('the exported layout is the device-inclusive tab copy the envelope keeps', () => {
  const key = freshPlace()
  enterPlace(key, 'conversation', { from: 'local', layout: aLayout([{ id: 'page-4', title: 'Four' }]), touched: false, protect: true })
  const out = place.workspace.exportLocalLayout()
  assert.ok(out && typeof out === 'object')
  assert.ok(Array.isArray(out.pages), 'the Page list is in the layout, and nowhere else')
  assert.deepEqual(out.pages.map((p) => p.id), ['page-4'])
})

/* -- the semantic touched flag --------------------------------------------- */

test("touched is the Holder's own marker, not a layout comparison", () => {
  const key = freshPlace()
  enterPlace(key, 'conversation', null)
  sessionFake.removeItem(SESSION + key + TOUCHED)
  assert.equal(touchedNow(key), false)
  /* An edit of the reader's: the Holder writes its marker beside the tab copy. */
  place.workspace.edit((a) => ({ ...a, pages: [...a.pages] }), undefined)
  sessionFake.setItem(SESSION + key + TOUCHED, '1')
  assert.equal(touchedNow(key), true)
  /* And a Save removes it again, which is what `changed()` would NOT say
     after a differing answer from the Brain. */
  sessionFake.removeItem(SESSION + key + TOUCHED)
  assert.equal(touchedNow(key), false)
})

test('a browser that refuses sessionStorage keeps the flag it entered with', () => {
  const key = freshPlace()
  enterPlace(key, 'conversation', {
    from: 'local', layout: aLayout([{ id: 'page-5', title: 'Five' }]), touched: true, protect: true,
  })
  sessionFake.refuseRead = true
  try {
    /* The marker cannot be asked for at all; the flag entered with stands,
       rather than a resumed edited place being written back as untouched. */
    assert.equal(touchedNow(key), true)
  } finally {
    sessionFake.refuseRead = false
  }
})

/* -- the scoped external history ------------------------------------------- */

function adapter({ here = 'conv-here', at = null, out = null } = {}) {
  const intents = []
  const outs = []
  const host = externalNavigation({
    originConversation: 'conv-origin',
    intend: (x) => intents.push(x),
    here: () => here,
    at: () => at,
    outward: () => (out === null ? null : (to) => outs.push(to)),
  })
  return { host, intents, outs }
}

test('a Page change carries the topic and post the address already has', () => {
  const { host, intents } = adapter({ at: { topic: 'topic-1', turn: 'post-3' } })
  host.page('page-2')
  assert.deepEqual(intents, [{ originConversation: 'conv-origin', topic: 'topic-1', turn: 'post-3', page: 'page-2' }])
  /* Cleared, a Page change would quietly drop the topic filtering the reading. */
})

test('a read in the conversation being read is one intent and nothing else', () => {
  const { host, intents, outs } = adapter({ here: 'conv-here', at: { topic: 'topic-1', turn: 'post-1' } })
  host.read('conv-here', 'post-9', 'page-2')
  assert.deepEqual(intents, [{ originConversation: 'conv-origin', topic: 'topic-1', turn: 'post-9', page: 'page-2' }])
  assert.deepEqual(outs, [])
})

test('a cross-conversation read leaves through the way out, with its whole target', () => {
  const { host, intents, outs } = adapter({ here: 'conv-here', out: true })
  host.read('conv-other', 'post-4', 'page-2')
  assert.deepEqual(outs, [{ conversation: 'conv-other', turn: 'post-4' }])
  assert.deepEqual(intents, [], 'the working area reports it; the adapter does not write it twice')
})

test('with no way out registered the destination conversation is still named', () => {
  const { host, intents } = adapter({ here: 'conv-here', out: null })
  host.read('conv-other', 'post-4', 'page-2')
  assert.deepEqual(intents, [
    { originConversation: 'conv-other', topic: null, turn: 'post-4', page: 'this-post' },
  ])
  /* Never the origin's address with somebody else's post in it. */
})

test('a detail that came with a cross-conversation read is held, not dropped', () => {
  const detail = { kind: 'replies', root: 'post-4', anchor: { kind: 'post', id: 'post-4' }, mode: 'aside' }
  const { host, outs } = adapter({ here: 'conv-here', out: true })
  host.read('conv-other', 'post-4', 'page-2', detail)
  assert.deepEqual(outs, [{ conversation: 'conv-other', turn: 'post-4' }])
  assert.deepEqual(awaitingDetail(), { conversation: 'conv-other', detail })
  /* And a read with no detail clears what an earlier one held, so a stale
     sheet never opens over a later arrival. */
  host.read('conv-third', 'post-5', 'page-2')
  assert.equal(awaitingDetail(), null)
})

/* -- the adapter against the real nav -------------------------------------- */

test('nav reports a cross-conversation read and applies none of it', () => {
  const key = freshPlace()
  enterPlace(key, 'conversation', { from: 'local', layout: aLayout([{ id: 'page-2', title: 'Two' }]), touched: false, protect: true })
  nav.replayExternal(() => { nav.arrive(key, null, null, { page: 'this-post' }) })
  const seen = []
  const outs = []
  const off = hostWorkingNavigation((to) => outs.push(to))
  const remove = nav.hostExternalNavigation(externalNavigation({
    originConversation: key,
    intend: (x) => seen.push(x),
    here: () => nav.snapshot().conversation,
    at: () => null,
    outward: () => (to) => outs.push(to),
  }))
  try {
    nav.read('conv-elsewhere', 'post-77', { page: 'page-2' })
    assert.deepEqual(outs, [{ conversation: 'conv-elsewhere', turn: 'post-77' }])
    assert.equal(nav.snapshot().conversation, key, 'the conversation was switched where it stood')
    assert.deepEqual(seen, [], 'the way out reports it; the adapter writes no second intent')
  } finally {
    remove()
    off()
  }
})

test('a Page change through nav reports one intent, and applying it back reports none', () => {
  const key = freshPlace()
  enterPlace(key, 'conversation', { from: 'local', layout: aLayout([{ id: 'page-2', title: 'Two' }]), touched: false, protect: true })
  nav.replayExternal(() => { nav.arrive(key, null, null, { page: 'this-post' }) })
  const seen = []
  const remove = nav.hostExternalNavigation(externalNavigation({
    originConversation: key,
    intend: (x) => seen.push(x),
    here: () => nav.snapshot().conversation,
    at: () => ({ topic: 'topic-k', turn: 'post-k' }),
    outward: () => null,
  }))
  try {
    nav.showPage('page-2')
    assert.deepEqual(seen, [{ originConversation: key, topic: 'topic-k', turn: 'post-k', page: 'page-2' }])
    assert.equal(nav.snapshot().page, 'page-2')
    /* Selecting the Page already shown names the SAME destination, so the one
       writer of the hash has nothing new to write and no entry is added. */
    nav.showPage('page-2')
    assert.equal(seen.length, 2)
    assert.deepEqual(seen[1], seen[0])
    /* And applying the hash back reports nothing at all: one guarded
       direction per transition, so the two cannot echo each other. */
    nav.replayExternal(() => { nav.showPage('this-post') })
    assert.equal(seen.length, 2)
    assert.equal(nav.snapshot().page, 'this-post')
  } finally {
    remove()
  }
})

test('the Page callback sees the OUTGOING Page while naming the destination', () => {
  const key = freshPlace()
  enterPlace(key, 'conversation', { from: 'local', layout: aLayout([{ id: 'page-2', title: 'Two' }]), touched: false, protect: true })
  nav.replayExternal(() => { nav.arrive(key, null, null, { page: 'this-post' }) })
  const saw = []
  const remove = nav.hostExternalNavigation({
    page: (id) => saw.push({ told: id, still: nav.snapshot().page }),
    read: () => {},
  })
  try {
    nav.showPage('page-2')
    assert.deepEqual(saw, [{ told: 'page-2', still: 'this-post' }])
    /* That is the capture point: the reading being left is still the one
       shown, so what is captured is its reading and not the destination's. */
  } finally {
    remove()
  }
})
