/* ------------------------------------------------------------------------ *
 * WHAT ACTUALLY LEAVES THE PAGE, AND WHEN -- the captured request.
 *
 * WHY THIS EXISTS. The focused independent re-review of the composer
 * correction (adm-871e7b570a26) reproduced a permission escalation that every
 * check about the draft passed: the Brain a page is bound to is answered
 * AFTER the composer mounts, so Send can be pressed while the answer is
 * pending, and the body is built and serialised THEN. Quiet's real write
 * guard (`guardWrites`) does not save it -- it waits for the binding and sets
 * `X-Mentis-Brain` on a body that already exists -- so the write left naming
 * one Brain while carrying another's Allow All, "may coordinate" and
 * side-work depth. A workspace's ask, which is not guarded at all, left at
 * once.
 *
 * So this does not read a draft: it presses Send in that window, through the
 * REAL lifecycle, the REAL workspace request client and the REAL write guard,
 * and looks at the request that arrives at `fetch` -- its JSON body, its
 * headers, and whether it left before the page could say where it was going.
 *
 * WHAT IT DOES NOT CLAIM. No browser, no pixels, no server: `fetch` is a
 * recorder here, and the record end of it (what intake does with such a body)
 * is the server's own tests. What this establishes is what the client emits.
 * ------------------------------------------------------------------------ */

import assert from 'node:assert/strict'
import { registerHooks } from 'node:module'
import { readFileSync, existsSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import ts from '../node_modules/typescript/lib/typescript.js'

const stub = new URL('./space_react_stub.mjs', import.meta.url).href

registerHooks({
  resolve(specifier, context, next) {
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

/* ---- the little of a browser this needs, BEFORE the page's modules load -- */

const ORIGIN = 'http://localhost:5173'
globalThis.window = globalThis
globalThis.location = { origin: ORIGIN, pathname: '/', search: '', hash: '' }
globalThis.sessionStorage = undefined

/** EVERY REQUEST THAT LEAVES, in order, as the network would see it. */
const left = []
/** WHAT THE SERVER IS, when a write gets there. Set per case: a Brain whose name
 *  does not match what the write names is the server having come to serve another
 *  one between the asking and the writing, and it answers as Mentis's own check
 *  does (`mentis/web/__init__.py`, `_other_brain`: 409 `BrainChanged`, nothing
 *  written). Null is a server that answers every write. */
let serving = null
globalThis.fetch = async (input, init) => {
  const url = typeof input === 'string' ? input : String(input)
  const headers = new Headers(init?.headers ?? undefined)
  const method = (init?.method ?? 'GET').toUpperCase()
  const named = headers.get('X-Mentis-Brain')
  left.push({
    url,
    method,
    brain: named,
    body: typeof init?.body === 'string' ? JSON.parse(init.body) : null,
  })
  if (serving && method !== 'GET' && named && named !== serving)
    return new Response(JSON.stringify({ error: 'Nothing was recorded: this server serves another Brain.', kind: 'BrainChanged' }),
      { status: 409, headers: { 'Content-Type': 'application/json' } })
  return new Response(JSON.stringify({ conversation: 'ent-conversation', turn: 'ent-turn', number: 1 }),
    { status: 200, headers: { 'Content-Type': 'application/json' } })
}

const R = await import('./space_react_stub.mjs')
const { usePermissionDefault, UNPLACED_SEND } = await import('../src/fluid/composer/useDefault.ts')
const { createBinding, guardWrites, guarding } = await import('../src/brainBinding.ts')
const { saveDefault, seedAddressees } = await import('../src/fluid/composer/permissionDefault.ts')
const { bodyOf, emptyDraft } = await import('../src/composer/draft.ts')
const { sendRequest, workspaceRequest } = await import('../src/fluid/workspaces/client.ts')

let checks = 0
const is = (a, b, what) => { assert.strictEqual(a, b, what); checks += 1 }
const eq = (a, b, what) => { assert.deepEqual(a, b, what); checks += 1 }
const ok = (a, what) => { assert.ok(a, what); checks += 1 }
const no = (a, what) => { assert.ok(!a, what); checks += 1 }

const bag = (seed = {}) => {
  const held = { ...seed }
  return {
    get length() { return Object.keys(held).length },
    clear() { for (const k of Object.keys(held)) delete held[k] },
    getItem: (k) => (k in held ? held[k] : null),
    key: (i) => Object.keys(held)[i] ?? null,
    removeItem: (k) => { delete held[k] },
    setItem: (k, v) => { held[k] = String(v) },
  }
}

const BRAIN_A = 'corpus-1@a1b2c3d4e5f60718'
const BRAIN_B = 'corpus-1@9f8e7d6c5b4a3921'
const OWNER = 'ent-owner-a'
const SCOPE_A = `${BRAIN_A}|${OWNER}`
const ALL = { consent: { mode: 'all', workspaces: ['C:\\Work\\Mentis'] }, coordinate: true, followUp: 1 }
const WORDS = 'look at the overnight run'

/** THE DRAFT THE TAB KEPT, filled in on Brain A: words of the owner's own,
 *  and the three concrete permission values the saved default put there. */
const keptOnA = (over = {}) => ({
  ...emptyDraft(), text: WORDS, restored: true, seeded: true, seededIn: SCOPE_A, askMentis: { ...ALL }, ...over,
})

/** A Brain answer this test releases itself: asks are pending until `answer`,
 *  and asks made after it are answered at once. */
const heldAnswer = (binding, brain) => {
  let open = false
  let waiting = []
  const say = () => { if (brain) binding.saw(brain); return brain ? true : null }
  const confirm = () => {
    if (open) return Promise.resolve(say())
    return new Promise((res) => { waiting.push(() => res(say())) })
  }
  return { confirm, answer: () => { open = true; const w = waiting; waiting = []; w.forEach((f) => f()) } }
}

/** The composer around the lifecycle, as Composer.tsx is: a draft in state,
 *  every change to it through the one seam, and the real `sending` the send
 *  path submits through. */
function mount({ draft, storage, binding, confirm }) {
  const seen = {}
  const Composing = (props) => {
    const [held, setHeld] = R.useState(() => props.draft)
    const setDraft = (fn) => setHeld((d) => seedAddressees(typeof fn === 'function' ? fn(d) : fn, true))
    const got = usePermissionDefault({
      enabled: true, fresh: true, owner: OWNER, draft: held, setDraft,
      binding: props.binding, confirm: props.confirm, storage: props.storage,
    })
    seen.draft = held
    seen.place = got.sending
    return null
  }
  R.act(() => { R.render(R.createElement(Composing, { draft, storage, binding, confirm })) })
  return seen
}

/** PRESSING SEND ON A WORKSPACE'S ASK, exactly as Composer.tsx does it: the
 *  draft is placed against the scope this submission resolves to, the body is
 *  built from what came back, and that is what goes through the real request
 *  client (`workspaceRequest` / `sendRequest`, POST /fluid/api/requests). */
const press = async (seen, draft) => {
  const ready = await seen.place(draft ?? seen.draft)
  if (!ready.ok) return { sent: false, why: ready.why }
  const post = bodyOf(ready.draft, OWNER, ready.draft.topics, 'ask-mentis')
  /* `ready.brain` goes to the write, as Composer.tsx hands it to `asking.send`
     and workspaces/Column.tsx hands it on: the write names what the submission
     was placed against. */
  try {
    const got = await sendRequest(workspaceRequest(post, 'wsp-1', 'op-1'), ready.brain)
    return { sent: true, got }
  } catch (e) {
    return { sent: false, refused: e.refusal, why: e.message }
  }
}

/** let every pending microtask run, so "nothing has left yet" means it. */
const settle = () => new Promise((res) => setImmediate(res))

/* ======================================================================== *
 * 1. A WORKSPACE'S ASK, WHICH NOTHING GUARDS, DOES NOT LEAVE BEFORE THE
 *    PAGE CAN SAY WHERE IT IS GOING
 * ======================================================================== */
{
  no(guarding(), 'the older Fluid shell guards none of its writes, as it never did')
  const storage = bag()
  saveDefault(SCOPE_A, ALL, storage, 1000)
  const binding = createBinding()
  const brain = heldAnswer(binding, BRAIN_B)
  const seen = mount({ draft: keptOnA(), storage, binding, confirm: brain.confirm })
  eq(seen.draft.askMentis, ALL, 'the kept draft still holds what was filled in on the Brain it was written on')
  const sending = press(seen)
  await settle()
  is(left.length, 0, 'pressing Send while the Brain is still being asked sends nothing at all')
  /* the server answers now: another Brain than the draft was filled in on */
  brain.answer()
  const out = await sending
  R.act(() => {})
  ok(out.sent, 'and once it has answered, the ask goes')
  const req = left.find((r) => r.url.endsWith('/fluid/api/requests'))
  ok(req, 'to the workspace request door')
  is(req.method, 'POST', 'as a write')
  eq(req.body.from, { workspace: 'wsp-1' }, 'started in the workspace it was asked from')
  is(req.body.text, WORDS, 'carrying the words the owner wrote')
  no('ask_mentis' in req.body, 'and no permission selection of the other Brain\'s: no Allow All')
  is(JSON.stringify(req.body).includes('"mode":"all"'), false, 'nothing in the body says Allow All')
  is(JSON.stringify(req.body).includes('"coordinate":true'), false, 'nothing in it coordinates')
  is(JSON.stringify(req.body).includes('follow_up'), false, 'and nothing in it carries side-work depth')
  no('seededIn' in req.body, 'nor any of the composer\'s own bookkeeping')
  is(req.brain, null, 'and it names no Brain: it carries nothing scoped to one, as this page\'s writes never did')
  left.length = 0
}

/* ======================================================================== *
 * 2. THE SAME SCOPE IS NOT NARROWED: what the owner has been looking at is
 *    what the request carries, once the answer names that same Brain
 * ======================================================================== */
{
  const storage = bag()
  saveDefault(SCOPE_A, ALL, storage, 1000)
  const binding = createBinding()
  const brain = heldAnswer(binding, BRAIN_A)
  serving = BRAIN_A
  const seen = mount({ draft: keptOnA(), storage, binding, confirm: brain.confirm })
  const sending = press(seen)
  await settle()
  brain.answer()
  const out = await sending
  R.act(() => {})
  ok(out.sent, 'the ask goes once the Brain answers')
  const req = left.find((r) => r.url.endsWith('/fluid/api/requests'))
  eq(req.body.ask_mentis,
    { consent: { mode: 'all', workspaces: ['C:\\Work\\Mentis'] }, coordinate: true, follow_up: { depth: 1 } },
    'carrying the three concrete values the owner chose, for the Brain they chose them on')
  is(req.brain, BRAIN_A, 'and naming the Brain those values belong to, on the write itself')
  serving = null
  left.length = 0
}

/* ======================================================================== *
 * 3. A PAGE THAT CANNOT SAY AT ALL SENDS NOTHING, AND LOSES NOTHING
 * ======================================================================== */
{
  const storage = bag()
  saveDefault(SCOPE_A, ALL, storage, 1000)
  const binding = createBinding()
  const brain = heldAnswer(binding, null)
  const seen = mount({ draft: keptOnA(), storage, binding, confirm: brain.confirm })
  const sending = press(seen)
  await settle()
  brain.answer()
  const out = await sending
  R.act(() => {})
  no(out.sent, 'a submission the page cannot place is not sent')
  is(out.why, UNPLACED_SEND, 'and says why, in words about what was taken out of it')
  is(left.filter((r) => r.method === 'POST').length, 0, 'nothing was written')
  is(seen.draft.text, WORDS, 'the owner\'s words are still in the draft')
  is(seen.draft.askMentis, undefined, 'and what was filled in is out of it, so the controls say what a send would carry')
  /* pressing Send again sends what the controls now say, and nothing else */
  const again = await press(seen)
  R.act(() => {})
  ok(again.sent, 'the next press goes')
  const req = left.find((r) => r.url.endsWith('/fluid/api/requests'))
  is(req.body.text, WORDS, 'with the words intact')
  no('ask_mentis' in req.body, 'and no permission selection at all')
  left.length = 0
}

/* ======================================================================== *
 * 3a. B1-F1: A FRESH CONFIRMATION THAT FAILED IS NOT THE OLD BINDING
 *
 * The re-review's first blocking finding. The page IS bound -- to A, where the
 * saved configuration was filled in -- and the server has since come to serve
 * B (a copy, or a copy restored in place: the ordinary case). Send asks afresh,
 * which is the only thing on an unguarded page that would notice, and that ask
 * fails: unreachable, a 503, an answer naming no Brain. Falling back to the
 * binding it already had resolved A|owner, kept Allow All in the body, and sent
 * it unnamed to B. So a failed fresh ask places nothing.
 * ======================================================================== */
{
  const storage = bag()
  saveDefault(SCOPE_A, ALL, storage, 1000)
  const binding = createBinding()
  binding.saw(BRAIN_A)
  /* the Brain read fails while the write door still works */
  let asks = 0
  const cannotSay = async () => { asks += 1; return null }
  serving = BRAIN_B
  const seen = mount({ draft: keptOnA(), storage, binding, confirm: cannotSay })
  R.act(() => {})
  eq(seen.draft.askMentis, ALL, 'the draft holds what was filled in on the Brain this page is bound to')
  const out = await press(seen)
  R.act(() => {})
  no(out.sent, 'a submission whose fresh confirmation failed is not sent')
  is(out.why, UNPLACED_SEND, 'and says why, rather than being placed against a binding nobody confirmed')
  ok(asks >= 1, 'the server was asked afresh')
  is(left.filter((r) => r.method === 'POST').length, 0, 'nothing was written anywhere')
  is(seen.draft.text, WORDS, 'the owner\'s words are still in the draft')
  is(seen.draft.askMentis, undefined, 'and what was filled in is out of it, so the controls say what the next send carries')
  is(binding.bound(), BRAIN_A, 'the binding itself is untouched: a read that failed is not a move')
  no(binding.moved(), '')
  /* and the next press, with the read still failing, carries nothing of A's */
  const again = await press(seen)
  R.act(() => {})
  ok(again.sent, 'the next press goes, since the draft now holds nothing of any Brain\'s default')
  const req = left.find((r) => r.url.endsWith('/fluid/api/requests'))
  is(req.body.text, WORDS, 'with the words intact')
  no('ask_mentis' in req.body, 'no Allow All')
  is(req.brain, null, 'and naming no Brain, carrying nothing scoped to one')
  serving = null
  left.length = 0
}

/* ======================================================================== *
 * 3b. B1-F2: THE RESOLVED BRAIN IS BOUND TO THE WRITE ITSELF
 *
 * The re-review's second blocking finding. The fresh ask answered A, truly --
 * and the server came to serve B between that answer and the POST. A check
 * before a write cannot say where the write is committed, so the write names
 * what it was placed against, and Mentis's own check (`_other_brain`) refuses
 * it: 409 `BrainChanged`, nothing recorded, rather than A's Allow All,
 * coordination and side-work depth landing in B's Work.
 * ======================================================================== */
{
  const storage = bag()
  saveDefault(SCOPE_A, ALL, storage, 1000)
  const binding = createBinding()
  binding.saw(BRAIN_A)
  /* the ask says A; the server is B by the time the write gets there */
  const saysA = async () => binding.saw(BRAIN_A)
  serving = BRAIN_B
  const seen = mount({ draft: keptOnA(), storage, binding, confirm: saysA })
  R.act(() => {})
  const out = await press(seen)
  R.act(() => {})
  no(out.sent, 'the write is refused rather than recorded in the Brain it was not placed against')
  is(out.refused, 'moved', 'as the server having moved on, which is what it is')
  const req = left.find((r) => r.url.endsWith('/fluid/api/requests'))
  ok(req, 'the request did leave')
  is(req.brain, BRAIN_A, 'naming the Brain its values were placed against, which is how the server could refuse it')
  eq(req.body.ask_mentis,
    { consent: { mode: 'all', workspaces: ['C:\\Work\\Mentis'] }, coordinate: true, follow_up: { depth: 1 } },
    'the body carried A\'s own three values, and nothing accepted them')
  is(seen.draft.text, WORDS, 'the owner\'s words are kept: nothing of theirs is lost by the refusal')
  serving = null
  left.length = 0
}

/* ======================================================================== *
 * 4. QUIET'S REAL WRITE GUARD: the header and the body are the same Brain's
 *
 *    This is the re-review's step 5. The guard holds the write until the page
 *    is bound and then names that Brain -- so the body it names must have
 *    been built against the same answer, not before it.
 * ======================================================================== */
{
  const storage = bag()
  saveDefault(SCOPE_A, ALL, storage, 1000)
  const binding = createBinding()
  const brain = heldAnswer(binding, BRAIN_B)
  guardWrites(binding)
  ok(guarding(), 'the page guards its writes, as Quiet Chat does')
  const seen = mount({ draft: keptOnA(), storage, binding, confirm: brain.confirm })
  const sending = press(seen)
  await settle()
  is(left.filter((r) => r.method === 'POST').length, 0, 'no write leaves before the page is bound')
  brain.answer()
  const out = await sending
  R.act(() => {})
  ok(out.sent, 'the write goes once it is')
  const req = left.find((r) => r.url.endsWith('/fluid/api/requests'))
  is(req.brain, BRAIN_B, 'naming the Brain the server actually serves')
  no('ask_mentis' in req.body, 'and carrying nothing that was filled in for the other one')
  left.length = 0
}

/* ======================================================================== *
 * 5. A NAMED REQUEST, GUARDED, CARRIES NO COPY OF THE OTHER BRAIN'S EITHER
 * ======================================================================== */
{
  const storage = bag()
  saveDefault(SCOPE_A, ALL, storage, 1000)
  const binding = createBinding()
  const brain = heldAnswer(binding, BRAIN_B)
  const worker = { participant: 'ent-worker', alias: '@Worker', dispatch: true, ...ALL, seeded: true }
  const seen = mount({ draft: keptOnA({ to: [worker] }), storage, binding, confirm: brain.confirm })
  const sending = press(seen)
  await settle()
  brain.answer()
  const out = await sending
  R.act(() => {})
  ok(out.sent, 'the named request goes once the page is bound')
  const req = left.find((r) => r.url.endsWith('/fluid/api/requests'))
  is(req.brain, BRAIN_B, 'naming the Brain it is recorded in')
  is(req.body.dispatch.length, 1, 'asking the one recipient to work')
  no('consent' in req.body.dispatch[0], 'with no Permission Mode of the other Brain\'s')
  no('follow_up' in req.body.dispatch[0], 'no side-work permission')
  is(req.body.dispatch[0].coordinate, false, 'and no authority to coordinate')
  is(req.body.dispatch[0].participant, 'ent-worker', 'while who was asked is untouched')
}

R.unmount()
console.log(`permission send, captured: ${checks} checks ok`)
