/* ------------------------------------------------------------------------ *
 * THE EYE TRAVELS TO WHAT YOU CHOOSE -- DRIVEN, NOT READ.
 *
 * This mounts the REAL SpaceSurface with a REAL session bound, down through
 * the REAL BrainSpace, and runs their real render bodies and effects
 * (tests/space_react_stub.mjs is the small hook runtime that makes that
 * possible). Nothing here matches source text.
 *
 * WHY IT EXISTS. Review adm-425121b18a7f found that with a session bound --
 * which is how every surface in the application draws, Fluid's `#/brain/space`
 * as much as Quiet's -- choosing a star no longer brought it into view: the
 * renderer read the selection revision once, when it mounted, and every saved
 * camera frame then wrote that stale number back over the session's. Neither
 * half could be seen by the suite, because every check about the renderer was
 * a regular expression over BrainSpace.tsx's characters, and the expressions
 * matched the broken gate exactly (A-1, A-2).
 *
 * So the two properties are driven as behaviour, both ways round:
 *   IT TRAVELS   for a click's choice, for the Tab walk, and for Escape
 *   IT DOES NOT  for a remount, a re-read handing over new node objects for
 *                the same ids, a radius change, or letting go of something no
 *                longer drawn
 * and a saved frame cannot take a choice back.
 *
 * WHAT IT DOES NOT CLAIM: nothing about painted pixels, CSS, real browser
 * scheduling or a real host. There is no canvas, so `paint` returns at its
 * first line and the camera is observed where the component puts it -- in the
 * session. Pixels are browser evidence and belong to whoever verifies the
 * integrated candidate.
 *
 * The graph here deliberately holds NO edges, so no strand is ever explained
 * and the animation loop never runs. Every animation frame this test counts
 * is therefore a travel frame, which is what makes "no frame at all was asked
 * for" a usable statement below.
 * ------------------------------------------------------------------------ */

import assert from 'node:assert/strict'
import { registerHooks } from 'node:module'
import { readFileSync, existsSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import ts from '../node_modules/typescript/lib/typescript.js'

const stub = new URL('./space_react_stub.mjs', import.meta.url).href

registerHooks({
  resolve(specifier, context, next) {
    /* REACT IS THE ONLY THING STOOD IN FOR. Everything else is the real file. */
    if (specifier === 'react' || specifier === 'react/jsx-runtime') return { url: stub, shortCircuit: true }
    if (specifier.startsWith('.')) {
      for (const suffix of ['.ts', '.tsx', '/index.ts']) {
        const url = new URL(specifier + suffix, context.parentURL)
        if (existsSync(fileURLToPath(url))) return { url: url.href, shortCircuit: true }
      }
    }
    return next(specifier, context)
  },
  load(url, context, next) {
    if (url.endsWith('.css')) return { format: 'module', source: '', shortCircuit: true }
    if (/\.tsx?$/.test(url))
      return {
        format: 'module',
        shortCircuit: true,
        source: ts.transpileModule(readFileSync(fileURLToPath(url), 'utf8'), {
          compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX },
        }).outputText,
      }
    return next(url, context)
  },
})

/* ---- the little of a browser these components actually touch ------------- */

let clock = 1_000
Object.defineProperty(globalThis, 'performance', { value: { now: () => clock }, configurable: true, writable: true })

let asked = 0
let pending = []
let nextFrame = 1
globalThis.requestAnimationFrame = (fn) => {
  const id = nextFrame++
  pending.push({ id, fn })
  asked += 1
  return id
}
globalThis.cancelAnimationFrame = (id) => {
  pending = pending.filter((f) => f.id !== id)
}

class Observer {
  observe() {}
  disconnect() {}
  unobserve() {}
}
globalThis.MutationObserver = Observer
globalThis.document = {
  documentElement: {},
  visibilityState: 'visible',
  addEventListener() {},
  removeEventListener() {},
  createElement: () => ({ width: 0, height: 0, style: {}, getContext: () => null }),
}
globalThis.window = {
  devicePixelRatio: 1,
  setTimeout: (fn, ms) => setTimeout(fn, ms),
  clearTimeout: (id) => clearTimeout(id),
  location: { pathname: '/', search: '', hash: '' },
}
/* `matchMedia` and `ResizeObserver` are deliberately absent: the components
   test for them, and without them motion is not reduced -- which is the path
   a travelling eye takes. */

const fetched = []
globalThis.fetch = async (url) => {
  fetched.push(String(url))
  return {
    ok: true,
    status: 200,
    statusText: 'OK',
    text: async () => '{}',
    json: async () => ({}),
    clone: () => ({ json: async () => null }),
  }
}

/* ---- the real components, over the stub --------------------------------- */

const R = await import('./space_react_stub.mjs')
const { default: SpaceSurface } = await import('../src/surfaces/space/SpaceSurface.tsx')
const { default: BrainSpace } = await import('../src/surfaces/space/BrainSpace.tsx')
const { createSpaceSession, spaceSessionInside } = await import('../src/surfaces/space/session.ts')

let checks = 0
const is = (a, b, what) => {
  assert.strictEqual(a, b, what)
  checks += 1
}
const eq = (a, b, what) => {
  assert.deepEqual(a, b, what)
  checks += 1
}
const ok = (a, what) => {
  assert.ok(a, what)
  checks += 1
}
const near = (a, b, what, slack = 1e-6) => {
  assert.ok(
    Math.abs(a.x - b.x) < slack && Math.abs(a.y - b.y) < slack && Math.abs(a.z - b.z) < slack,
    `${what} (expected ${JSON.stringify(b)}, got ${JSON.stringify(a)})`,
  )
  checks += 1
}

/* ---- a Brain to look at: two Conversations, no edges -------------------- */

const node = (entry, kind, layer, conversation, at) => ({
  entry,
  kind,
  layer,
  conversation,
  at,
  summary: `${kind} ${entry}`,
  deleted: false,
  edited: false,
  replaced: false,
})

const graph = (extra = []) => ({
  nodes: [
    node('c1', 'conversation', 'place', 'c1', 100),
    node('c2', 'conversation', 'place', 'c2', 101),
    node('r1', 'decision', 'how', 'c1', 102),
    node('r2', 'decision', 'how', 'c1', 103),
    node('r3', 'decision', 'how', 'c2', 104),
    ...extra,
  ],
  edges: [],
  conversations: { c1: 'Alpha', c2: 'Beta' },
  layers: ['how', 'that', 'place', 'who', 'said', 'material'],
  total: 5 + extra.length,
  omitted: 0,
  cap: 6000,
  material: false,
})

const session = createSpaceSession({ id: 'one', brainKey: 'brain' })
const inside = spaceSessionInside(session)
inside.publish('records', { data: graph(), loading: false, error: null })
session.setVisible(true)

const show = () => R.render(R.createElement(SpaceSurface, { onOpen: () => {}, session }))
const canvasOf = () => {
  const got = R.find(BrainSpace)
  ok(got.length === 1, 'exactly one canvas is rendered for this session')
  return got[0]
}
/** The canvas as it is now: its props after the latest pass. A re-read hands
 *  it new node objects at new places, so a star must be looked up in what the
 *  canvas is drawing, never in what it was drawing. */
const canvasNow = () => R.find(BrainSpace)[0]
const starAt = (id) => {
  const p = canvasNow().props.placed.find((q) => q.id === id)
  assert.ok(p, `${id} is drawn`)
  return { x: p.x, y: p.y, z: p.z }
}
const fieldOf = () => {
  const got = R.find('div').filter((d) => d.props.className === 'space-field')
  assert.strictEqual(got.length, 1, 'the canvas has one field')
  return got[0]
}
const travelling = () => fieldOf().props['data-moving'] === 'true'
const rev = () => session.getCamera().selectionRevision
const at = () => session.getCamera().eye.at
/* Run every frame that has been asked for, once, after this much time. A
   travel of 420ms finishes in one frame given more than that. */
const frame = (ms) =>
  R.act(() => {
    clock += ms
    const now = pending
    pending = []
    for (const f of now) f.fn(clock)
  })

/* ---- it is bound, and the surface reads nothing ------------------------- */

show()
const space = canvasOf()
is(space.props.session, session, 'the surface hands the canvas the session it was given: the bound path is the real one')
is(space.props.selected, null, 'nothing is chosen to begin with')
ok(
  !fetched.some((u) => u === '/api/space' || u.startsWith('/api/space?')),
  'a bound surface reads the Brain not at all: the host mounts the one reader',
)
const far = [...space.props.placed].sort((a, b) => Math.hypot(b.x, b.y, b.z) - Math.hypot(a.x, a.y, a.z))[0]
ok(Math.hypot(far.x, far.y, far.z) > 1, 'the star chosen below is not already where the eye is looking')
eq({ ...at() }, { x: 0, y: 0, z: 0 }, 'an untouched eye orbits the middle of the Brain')

/* ---- A CLICK'S CHOICE FLIES THE EYE ------------------------------------- *
 * `onSelect` is the whole of what a click does once it has hit a star
 * (BrainSpace's own onClick hit-tests the painted canvas, which there is not
 * one of here); the surface turns it into `select(..., 'user')`. */

const beforeClick = asked
R.act(() => space.props.onSelect(far.id))
is(session.getSnapshot().view.selected, far.id, 'choosing a star chooses it')
is(rev(), 1, '...as a choice, which is what the eye flies for')
ok(asked > beforeClick, 'a frame is asked for: the flight has begun')
ok(travelling(), '...and the field says it is moving')
frame(500)
near({ ...at() }, { x: far.x, y: far.y, z: far.z }, 'THE EYE ARRIVED AT WHAT WAS CHOSEN')
is(session.getCamera().framing, 'held', 'travelling is taking hold of the eye')
ok(!travelling(), 'and the flight is over')
is(rev(), 1, 'the frames it saved on the way did not take the choice back')

/* ---- THE TAB WALK FLIES TOO -------------------------------------------- *
 * Through the field's own keyboard handler, as a reader's Tab arrives. With
 * nothing connected to what is chosen, Tab goes to the busiest Conversation
 * not yet visited, which is this canvas's documented walk. */

const prevented = []
const key = (k, more = {}) => ({
  key: k,
  shiftKey: false,
  ...more,
  preventDefault: () => prevented.push(k),
  stopPropagation: () => {},
})

const beforeTab = asked
R.act(() => fieldOf().props.onKeyDown(key('Tab')))
const walked = session.getSnapshot().view.selected
ok(walked !== far.id && walked !== null, 'Tab moved the selection on')
is(rev(), 2, '...as a choice')
ok(prevented.includes('Tab'), '...and Tab was taken, not left to move focus out')
ok(asked > beforeTab, 'a flight began for it')
frame(500)
near({ ...at() }, starAt(walked), 'THE EYE TRAVELLED WITH THE TAB WALK')

/* ---- ESCAPE LETS GO, AND THE EYE RETURNS TO THE MIDDLE ------------------ */

const beforeEsc = asked
R.act(() => fieldOf().props.onKeyDown(key('Escape')))
is(session.getSnapshot().view.selected, null, 'Escape lets go')
is(rev(), 3, '...which is a choice as much as choosing is')
ok(asked > beforeEsc, 'and the eye is flown back')
frame(500)
near({ ...at() }, { x: 0, y: 0, z: 0 }, 'THE EYE RETURNED TO THE MIDDLE OF THE BRAIN')

/* ---- WHAT MUST NOT REPLAY ---------------------------------------------- */

R.act(() => canvasNow().props.onSelect('r3'))
frame(500)
const settled = session.getCamera()
const standing = { ...at() }
is(session.getSnapshot().view.selected, 'r3', 'something is chosen, and travelled to')
near(standing, starAt('r3'), 'the eye is at it')

// a remount -- which is what moving the graph to another column does
let quiet = asked
R.act(() => R.unmount())
show()
is(asked, quiet, 'A REMOUNT FLIES NOTHING: a restored selection has already been travelled to')
const after = session.getCamera()
eq(after.eye, settled.eye, '...and the eye comes back exactly where it was left')
is(after.framing, 'held', '...still held')
is(canvasOf().props.selected, 'r3', '...still looking at the same thing')
ok(!travelling(), '...and not moving')

// a re-read: the same ids, in new node objects, and more of them, so the
// world radius changes too
quiet = asked
inside.publish('records', { data: graph([node('r4', 'decision', 'how', 'c2', 105)]), loading: false, error: null })
R.act(() => {})
is(asked, quiet, 'A RE-READ FLIES NOTHING, though every node object and the world radius are new')
eq({ ...at() }, standing, '...and the eye has not been moved by it')
is(session.getCamera().eye.out, settled.eye.out, '...nor re-fitted: a held eye keeps its distance')

// letting go of something no longer drawn is not a choice
quiet = asked
const without = graph()
without.nodes = without.nodes.filter((n) => n.entry !== 'r3')
without.total = without.nodes.length
inside.publish('records', { data: without, loading: false, error: null })
R.act(() => {})
is(session.getSnapshot().view.selected, null, 'a selection that is no longer drawn is let go')
is(rev(), 4, '...and that is reconciled, not chosen: the revision does not move')
is(asked, quiet, 'SO NOTHING FLIES FOR IT: the eye stays where the reader left it')
eq({ ...at() }, standing, '...exactly where it was')

/* ---- and a stale frame cannot take a choice back ------------------------ *
 * The renderer saves the camera it read when it mounted, on every frame it
 * moves. A choice made since must survive that. */

const c2 = starAt('c2')
R.act(() => canvasNow().props.onSelect('c2'))
is(rev(), 5, 'a fresh choice')
frame(100) // part of the way: frames saved, the flight not finished
is(rev(), 5, 'a frame saved mid-flight has not taken the choice back')
frame(500)
is(rev(), 5, '...nor has the one that finished it')
near({ ...at() }, c2, 'and the eye got there')

/* ---- nothing read the Brain through any of it --------------------------- */

ok(
  !fetched.some((u) => u === '/api/space' || u.startsWith('/api/space?')),
  'choosing, walking, remounting and re-reading asked for no graph read of their own',
)

R.act(() => R.unmount())
session.dispose()

console.log(`space travel: ${checks} checks passed`)
