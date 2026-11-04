/* MANUAL ACTIVATION, REACHABLE (docs/magnets/M1-contract.md, "Manual activation"):
 * a press is one key and a lost answer is asked again only under it; what the
 * server says is said in its words; a new Magnet can run and an old one is only
 * changed by an explicit press; the editor keeps what is unset absent; its own
 * Conversation is a separate action from its source. Refusals come from the
 * fixtures Python and Rust are held to. */
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { createActivations, readAnswer, resultWords, type ActivationKey, type ActivationResult } from '../src/fluid/surface/magnet/activation'
import { conversationSeed } from '../src/fluid/surface/magnet/choices'
import {
  ACTIVATION_REFUSALS, BUILD_ENV, activationRefusal, activationRuns, changeOf, createAdapters, draftProblems, magnetAvailability, notRunning, setUpChange, valueWord, withFacet,
} from '../src/fluid/surface/magnet/model'
import { bindMagnetOps, magnetDefs, type MagnetOps } from '../src/fluid/surface/magnet/provider'
import type { ActionCtx, ActionTarget } from '../src/fluid/surface/actions/types'
import { ACTIVATION_MODES, AI_MODES, DESTINATIONS, OPERATIONS, OUTPUTS, type MagnetConfig, type MagnetId, type MagnetSeed } from '../src/fluid/surface/magnet/types'

const fixture = (name: string) => JSON.parse(readFileSync(fileURLToPath(new URL(`../../../tests/fixtures/magnet-conformance/activation/${name}`, import.meta.url)), 'utf8'))
const ID = 'mag-a1c7e2f09b3d4e68' as MagnetId
const refusals = fixture('refusals.json') as Record<string, { status: number; body: Record<string, unknown> }>
const old = (): MagnetSeed => {
  const { activation: _a, processing: _p, ...seed } = conversationSeed('c1')
  return seed
}
const cfg = (seed: MagnetSeed = conversationSeed('c1')): MagnetConfig => ({ id: ID, ...seed })

const RESULT: ActivationResult = {
  magnet: ID, state: 'complete', conversation: 'ent-own', conversation_created: true, post: 'ent-post',
  page: { sources: 1, results: 3, statuses: { ok: 1, partial: 0, busy: 0, unavailable: 0 }, kept: [] }, replayed: false,
}

function world(answers: Array<() => { status: number; body: unknown } | Promise<{ status: number; body: unknown }>>) {
  const sent: ActivationKey[] = []
  const kept = new Map<string, ActivationKey>()
  let keys = 0
  const a = createActivations({
    post: async (_m, key) => {
      sent.push(key)
      const next = answers.shift()
      if (!next) throw new Error('nothing more was expected')
      return next()
    },
    me: async () => 'ent-me',
    newKey: () => `key-${++keys}`,
    keptKey: (m) => kept.get(m) ?? null,
    keepKey: (m, k) => { if (k) kept.set(m, k); else kept.delete(m) },
  })
  return { a, sent, kept }
}
const lost = () => { throw new Error('the connection went') }
const outcomeUnknown = () => ({ status: 503, body: refusals['outcome-unknown'].body });

/* -- one press, one key --------------------------------------------------------- */
{
  const { a, sent, kept } = world([() => ({ status: 201, body: RESULT }), () => ({ status: 201, body: { ...RESULT, post: 'ent-2' } })])
  assert.equal(a.now(ID).phase, 'idle', 'nothing has been pressed')
  assert.equal(sent.length, 0, 'and nothing was sent by asking')
  const first = await a.press(ID)
  assert.equal(first.phase, 'complete')
  assert.equal(first.result?.conversation, 'ent-own', 'the way to its result')
  assert.deepEqual(sent[0], { author: 'ent-me', op: 'key-1' }, 'it posts exactly author and op')
  assert.equal(kept.size, 0, 'a result ends the key')
  await a.press(ID)
  assert.equal(sent[1].op, 'key-2', 'the next press is a new key: a new activation')
}

/* running: while it is answered it is the same press, and its key is already kept */
{
  let answer!: (x: { status: number; body: unknown }) => void
  const { a, sent, kept } = world([() => new Promise((r) => { answer = r })])
  const phases: string[] = []
  a.subscribe(() => phases.push(a.now(ID).phase))
  const one = a.press(ID)
  const two = a.press(ID)
  await new Promise((r) => setTimeout(r, 0))
  assert.equal(a.now(ID).phase, 'running')
  assert.equal(kept.get(ID)?.op, 'key-1', 'kept before it is answered, so a reload loses nothing')
  answer({ status: 201, body: RESULT })
  assert.equal((await one).phase, 'complete')
  assert.equal((await two).phase, 'complete')
  assert.equal(sent.length, 1, 'a second press while running sends nothing')
  assert.deepEqual(phases, ['running', 'complete'])
}

/* -- a lost answer: only ever the same key ---------------------------------------- */
{
  const { a, sent, kept } = world([outcomeUnknown, lost, () => ({ status: 200, body: { ...RESULT, replayed: true } }), () => ({ status: 201, body: RESULT })])
  const first = await a.press(ID)
  assert.equal(first.phase, 'unknown')
  assert.equal(first.words, refusals['outcome-unknown'].body.error, 'in the server\'s words')
  assert.equal(first.sameKey, true)
  assert.equal((await a.press(ID)).phase, 'unknown', 'no answer at all is not knowing too')
  const third = await a.press(ID)
  assert.deepEqual(sent.map((k) => k.op), ['key-1', 'key-1', 'key-1'], 'every retry is the same key')
  assert.equal(third.phase, 'complete')
  assert.ok(third.words?.startsWith('Already recorded under this key'), 'a replay says it wrote nothing again')
  assert.equal(kept.size, 0)
  await a.press(ID)
  assert.equal(sent[3].op, 'key-2', 'only then is a press a new one')
}

/* a key still kept when the page comes back: said, and it is what the next press uses */
{
  const { a, sent, kept } = world([() => ({ status: 200, body: { ...RESULT, replayed: true } })])
  kept.set(ID, { author: 'ent-earlier', op: 'key-from-before' })
  assert.equal(a.now(ID).phase, 'unknown', 'an earlier press was never answered here')
  assert.equal(a.now(ID).sameKey, true)
  await a.press(ID)
  assert.deepEqual(sent[0], { author: 'ent-earlier', op: 'key-from-before' }, 'its key, and its author')
}

/* asking about a lost answer, a Busy says nothing of it: the key stays */
{
  const { a, sent, kept } = world([outcomeUnknown, () => ({ status: 503, body: refusals['busy'].body }), () => ({ status: 200, body: { ...RESULT, replayed: true } })])
  await a.press(ID)
  const busy = await a.press(ID)
  assert.equal(busy.phase, 'busy')
  assert.equal(busy.sameKey, true)
  assert.equal(kept.get(ID)?.op, 'key-1')
  await a.press(ID)
  assert.deepEqual(sent.map((k) => k.op), ['key-1', 'key-1', 'key-1'])
}

/* -- every answer, in the server's own words ---------------------------------------- */
for (const [name, row] of Object.entries(refusals)) {
  const said = (row.body.reason as { message?: string } | undefined)?.message ?? row.body.error as string
  const { now, keepsKey } = readAnswer(row.status, row.body, false)
  assert.equal(now.words, said, `${name}: its own words`)
  if (name === 'outcome-unknown') {
    assert.equal(now.phase, 'unknown')
    assert.equal(keepsKey, true)
  } else {
    assert.equal(now.phase, row.body.kind === 'Busy' ? 'busy' : 'refused', `${name}: ${row.status}`)
    assert.equal(keepsKey, false, `${name}: nothing was recorded under it`)
  }
}
{
  assert.equal(readAnswer(500, { error: 'it failed' }, false).keepsKey, true, 'a failure nobody can vouch for keeps the key')
  assert.equal(readAnswer(502, '<html>', false).now.phase, 'unknown', 'nor is an answer it can\'t read taken for a refusal')
  assert.equal(readAnswer(200, { nope: 1 }, false).now.phase, 'unknown', 'nor for a result')
  assert.equal(readAnswer(422, refusals['no-readable-source'].body, true).keepsKey, false, 'past the key\'s look-up, a refusal says it is free')
  const partial: ActivationResult = { ...RESULT, state: 'partial', page: { ...RESULT.page, statuses: { ok: 0, partial: 0, busy: 1, unavailable: 1 }, kept: [{ facet: 'phrases', reason: 'phrase semantics are not decided' }] } }
  const { now } = readAnswer(201, partial, false)
  assert.equal(now.phase, 'partial')
  assert.ok(/1 busy; 1 unavailable; phrases: phrase semantics are not decided/.test(now.words ?? ''), 'partial says what it held back')
  assert.ok(resultWords(RESULT).includes('3 results from 1 source'), 'and a whole page what it holds')
}

/* -- what can run: the server's rows, in its words -------------------------------------- */
{
  const rows = fixture('definitions.json').executable as Array<{ id: string; definition: MagnetConfig; answer: string }>
  assert.ok(rows.length > 5)
  for (const { id, definition, answer } of rows) {
    const got = activationRefusal(definition)
    assert.equal(got?.code ?? 'ready', answer, `${id}: as Python decides`)
    assert.equal(activationRuns(definition), answer === 'ready')
    if (got) assert.equal(got.message, (refusals[answer].body.reason as { message: string }).message, `${id}: in Python's words`)
  }
  for (const [code, words] of Object.entries(ACTIVATION_REFUSALS)) assert.equal(refusals[code].body.error, words, code)
}

/* -- a new Magnet can run; nothing else is changed without a press ------------------------ */
{
  const seed = conversationSeed('c1')
  assert.deepEqual(seed.activation, { mode: 'manual' })
  assert.deepEqual(seed.processing, { operations: [{ op: 'extract' }] })
  assert.equal(activationRuns(cfg()), true, 'made from Fluid, it can run')
  for (const absent of ['ai', 'outputs', 'destinations', 'conversation'] as const) assert.ok(!(absent in seed), `${absent} is left unset`)
  assert.equal(setUpChange(cfg()), null, 'nothing to set up')

  const before = cfg(old())
  assert.equal(activationRefusal(before)?.code, 'activation-not-supported')
  assert.deepEqual(setUpChange(before), { activation: { mode: 'manual' }, processing: { operations: [{ op: 'extract' }] } })
  const set = { ...before, ...setUpChange(before) } as MagnetConfig
  assert.equal(activationRuns(set), true, 'what it sends is what makes it run')
  assert.deepEqual(setUpChange({ ...before, activation: { mode: 'manual' } }), { processing: { operations: [{ op: 'extract' }] } }, 'only what it lacks')
  for (const asks of [{ activation: { mode: 'event', event: 'x' } }, { processing: { operations: [{ op: 'classify' }] } }, { processing: { operations: [{ op: 'extract' }, { op: 'compare' }] } }] as Partial<MagnetConfig>[])
    assert.equal(setUpChange({ ...before, ...asks }), null, `${JSON.stringify(asks)} is never overwritten`)
}

/* -- the actions: one registry, disabled with the reason, its own Conversation ------------- */
{
  const did: string[] = []
  const configs = new Map<string, MagnetConfig>([[ID, cfg()]])
  let running = false
  const adapters = createAdapters()
  bindMagnetOps({
    notHere: () => null, config: (id) => configs.get(id), existing: () => null, create: async () => { throw new Error('no') }, reveal: () => {},
    current: () => null, conversationName: () => 'Tidewater', showTab: () => {}, configure: () => {}, peek: () => {}, look: () => {}, remove: async () => {},
    adapters: () => adapters,
    activate: async (id) => { did.push(`activate(${id})`) },
    activating: () => running,
    setUpActivation: async (id) => { did.push(`setUp(${id})`) },
    ownConversation: async (id) => { did.push(`own(${id})`); return 'ent-own' },
  } satisfies MagnetOps)
  const target: ActionTarget = { resource: { address: 'magnet:' + ID, kind: 'magnet' } }
  const opened: string[] = []
  const ctx = { nav: { openPlace: (k: string) => opened.push(k) } } as unknown as ActionCtx
  const def = (id: string) => magnetDefs(target).find((d) => d.id === id)!
  const state = (id: string) => def(id).available(target, ctx)

  assert.deepEqual(state('magnet.activate'), { state: 'available' })
  assert.equal(state('magnet.setUpActivation').state, 'absent', 'nothing to set up on a Magnet that can run')
  assert.equal(def('magnet.activate').writes, 'record')
  await def('magnet.activate').run(target, ctx)
  assert.deepEqual(did, [`activate(${ID})`])

  running = true
  const waits = state('magnet.activate')
  assert.ok(waits.state === 'disabled' && /running/.test(waits.reason.message), 'while it runs it says so')
  running = false

  configs.set(ID, cfg(old()))
  const off = state('magnet.activate')
  assert.ok(off.state === 'disabled', 'a definition that cannot run is disabled')
  assert.equal(off.state === 'disabled' && off.reason.message, ACTIVATION_REFUSALS['activation-not-supported'], 'and says why, in the server\'s words')
  assert.equal(state('magnet.setUpActivation').state, 'available', 'with the explicit way to set it up')
  did.length = 0
  await def('magnet.setUpActivation').run(target, ctx)
  assert.deepEqual(did, [`setUp(${ID})`])

  did.length = 0
  await def('magnet.conversation').run(target, ctx)
  assert.deepEqual(did, [`own(${ID})`])
  assert.deepEqual(opened, ['ent-own'], 'it opens its own, never c1, its source')
  assert.equal(def('magnet.conversation').group, 'resource')

  const none = { ...cfg() } as MagnetConfig
  assert.equal(magnetAvailability(none, BUILD_ENV, adapters).get('magnet.conversation')?.state, 'available')
  bindMagnetOps(null)
}

/* -- the editor's rules: every value said, what is unset stays absent --------------------- */
{
  assert.equal(valueWord('activation', 'manual'), 'manual: runs')
  for (const m of ACTIVATION_MODES.filter((v) => v !== 'manual')) assert.equal(valueWord('activation', m), `${m}: kept, not run`)
  for (const o of OPERATIONS.filter((v) => v !== 'extract')) assert.equal(valueWord('operation', o), `${o}: kept, not run`)
  for (const m of AI_MODES.filter((v) => v !== 'none')) assert.equal(valueWord('ai', m), `${m}: kept, not run`)
  for (const o of OUTPUTS.filter((v) => v !== 'records')) assert.equal(valueWord('output', o), `${o}: kept, not run`)
  for (const k of DESTINATIONS.filter((v) => v !== 'magnet-conversation')) assert.equal(valueWord('destination', k), `${k}: kept, not run`)

  const seed = old()
  const shown = cfg(seed)
  assert.deepEqual(changeOf(shown, { ...seed }), {}, 'opened and saved as it was: nothing to send')

  /* set, then unset: as if it had never been said, with no key left behind */
  const facets = [['ai', { mode: 'agent', agent: 'x' }], ['outputs', ['findings']], ['destinations', [{ kind: 'brain', ref: 'b' }]], ['activation', { mode: 'manual' }], ['processing', { operations: [{ op: 'extract' }] }]] as const
  for (const [f, value] of facets) {
    const set = withFacet(seed, f, value as never)
    assert.deepEqual(changeOf(shown, set), { [f]: value }, `${f}: only what changed`)
    const unset = withFacet(set, f, undefined)
    assert.ok(!(f in unset), `${f}: no key is left`)
    assert.equal(JSON.stringify(unset), JSON.stringify(seed), `${f}: the same draft again`)
    assert.deepEqual(changeOf(shown, unset), {}, `${f}: nothing to send`)
    assert.deepEqual(changeOf(cfg(set), unset), { [f]: null }, `${f}: a saved one is taken out by null`)
  }
  const wire = JSON.parse(JSON.stringify(changeOf(cfg(withFacet(seed, 'ai', { mode: 'none' })), seed)))
  assert.deepEqual(wire, { ai: null }, 'and the null survives the wire')

  assert.deepEqual(draftProblems({ ...seed, activation: { mode: 'scheduled' } }).length, 1, 'a schedule needs its timing')
  assert.deepEqual(draftProblems({ ...seed, activation: { mode: 'event', event: 'x' } }), [])
  assert.deepEqual(draftProblems({ ...seed, activation: { mode: 'condition' } }).length, 1)

  /* a theme is drawn, and doesn't stop anything running */
  assert.equal(activationRuns(cfg({ ...conversationSeed('c1'), presentation: { renderer: 'disc', theme: 'glass' } })), true)
  const adapters = createAdapters()
  assert.ok(notRunning(cfg({ ...seed, ai: { mode: 'agent' } }), BUILD_ENV, adapters).some((n) => n.facet === 'ai'), 'notRunning says what is kept')
}

/* -- the source says what the action promises ------------------------------------------- */
{
  const src = (f: string) => readFileSync(fileURLToPath(new URL(`../src/fluid/surface/magnet/${f}`, import.meta.url)), 'utf8')
  const ed = src('Editor.tsx')
  for (const part of ['activation', 'processing', 'ai', 'outputs', 'destinations', 'theme']) assert.ok(ed.includes(`data-part="${part}"`), `the editor has ${part}`)
  const client = src('client.ts')
  assert.ok(client.includes("magnetDoor(id, 'activate', key)"), 'Activate posts what the door takes, and only that')
  assert.ok(!/setInterval|setTimeout/.test(src('activation.ts')), 'nothing presses for anybody')
}

console.log('fluid_magnet_activation_unit: ok')
