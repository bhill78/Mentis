// What becomes of an answer that was sent: slow answers, lost acknowledgments, refreshes,
// duplicate sends, two tabs, storage that will not store. node tests/fluid_decision_outbox_unit.mjs
import { registerHooks } from 'node:module'
import { readFileSync, existsSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import assert from 'node:assert/strict'
import ts from '../node_modules/typescript/lib/typescript.js'

registerHooks({
  resolve(specifier, context, next) {
    if (specifier.startsWith('.')) {
      for (const suffix of ['.ts', '.tsx', '/index.ts']) {
        const url = new URL(specifier + suffix, context.parentURL)
        if (existsSync(fileURLToPath(url))) return { url: url.href, shortCircuit: true }
      }
    }
    return next(specifier, context)
  },
  load(url, context, next) {
    if (/\.tsx?$/.test(url)) return { format: 'module', shortCircuit: true, source: ts.transpileModule(readFileSync(fileURLToPath(url), 'utf8'), { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } }).outputText }
    return next(url, context)
  },
})

const O = await import('../src/experimental/decisionOutbox.ts')

/** A browser's storage, shared by every "page" and "tab" made over it. */
function storage() {
  const data = new Map()
  return {
    data,
    getItem: (k) => (data.has(k) ? data.get(k) : null),
    setItem: (k, v) => { data.set(k, String(v)) },
    removeItem: (k) => { data.delete(k) },
    get length() { return data.size },
    key: (i) => [...data.keys()][i] ?? null,
  }
}
const kept = (st, ask) => JSON.parse(st.data.get(O.STORE_PREFIX + ask) ?? 'null')

/** A server that records a post ONCE per (author, op), as Mentis does, can void a key in one
 *  step, and can be told to lose the answer, answer slowly, refuse, or be unreachable. */
function server() {
  const posts = new Map()           // author|op -> {turn, number} | {voided: true}
  const s = {
    posts, received: 0, mode: 'ok', release: null, arriving: null,
    net: {
      async post(conversation, body) {
        s.received++
        if (s.mode === 'refuse') return { status: 200, body: { error: 'a withdrawal answers the Turn that asked for the decision' } }
        if (s.mode === 'down') throw new TypeError('Failed to fetch')           // never reached the server
        const key = `${body.author}|${body.op}`
        if (s.mode === 'in-transit') {                                           // on its way: lands only when released
          await new Promise((r) => { s.arriving = r })
        }
        if (posts.get(key)?.voided) return { status: 200, body: { error: 'this operation key was already used for a different request; nothing was written' } }
        if (!posts.has(key)) posts.set(key, { turn: `ent-${posts.size + 1}`, number: 400 + posts.size + 1, dispatched: 0, ...(body.reconsidered ? { reconsidered: body.reconsidered } : {}) })
        const answer = { ...posts.get(key) }
        if (s.mode === 'slow') await new Promise((r) => { s.release = r })
        if (s.mode === 'lost') throw new TypeError('Failed to fetch')           // written, answer lost
        if (s.mode === '500') return { status: 502, body: null }                // written, proxy failed
        return { status: 200, body: answer }
      },
      async lookup(op, author) {
        if (s.mode === 'down') throw new TypeError('Failed to fetch')
        const got = posts.get(`${author}|${op}`)
        if (got?.voided) return { recorded: false, voided: true }
        return got ? { recorded: true, voided: false, result: got } : { recorded: false, voided: false }
      },
      async void(op, author) {
        if (s.mode === 'down') throw new TypeError('Failed to fetch')
        const key = `${author}|${op}`
        const got = posts.get(key)
        if (got && !got.voided) return { recorded: true, voided: false, result: got }
        posts.set(key, { voided: true })
        return { recorded: false, voided: true }
      },
    },
  }
  return s
}
const landed = (srv) => [...srv.posts.values()].filter((p) => !p.voided).length

const sent = (over = {}) => {
  const ask = over.ask ?? 'opr-1'
  const op = O.newOp(ask, () => 'u1')
  return {
    ask, op, conversation: 'ent-c', author: 'ent-owner',
    body: { author: 'ent-owner', text: 'my decision', op },
    pick: { kind: 'own' }, text: 'my decision', label: null, continued: false, phase: 'sending', at: 1,
    turn: null, number: null, dispatched: null, did: null, why: null, kept: true, brain: null, ...over,   // every page now says its Brain, or none
  }
}
const tick = () => new Promise((r) => setTimeout(r, 0))

// -- what an answer means --------------------------------------------------------------
assert.deepEqual(O.outcomeOf(200, { turn: 'ent-9', number: 423, dispatched: 1 }), { kind: 'recorded', turn: 'ent-9', number: 423, dispatched: 1, did: null })
assert.deepEqual(O.outcomeOf(200, { turn: 'ent-9', number: 5, reconsidered: { pursued: ['a', 'b'], deferred: ['c'], dismissed: [], started: [{}, {}] } }).did,
  { pursued: 2, deferred: 1, dismissed: 0, started: 2 }, 'what a choice about findings did is the server\'s account of it')
assert.equal(O.outcomeOf(200, { turn: 'ent-9', number: 5, reconsidered: { pursued: ['a'], deferred: [], dismissed: [] } }).did.started, null,
  'and when it does not say what it started, that is not turned into a number')
assert.equal(O.outcomeOf(200, { error: 'no' }).kind, 'refused', 'the server said it wrote nothing')
assert.equal(O.outcomeOf(401, { error: 'owner', kind: 'OwnerAuthRequired' }).kind, 'refused')
assert.equal(O.outcomeOf(502, null).kind, 'unknown', 'a failure between here and the server says nothing about the write')
assert.equal(O.outcomeOf(500, { error: 'boom' }).kind, 'unknown', 'a server error may have happened after the write')
assert.equal(O.outcomeOf(200, null).kind, 'unknown', 'an answer that is not the server\'s is not a confirmation')
assert.equal(O.outcomeOf(200, {}).kind, 'unknown')
assert.notEqual(O.newOp('a'), O.newOp('a'), 'each press of Decide is its own operation')

// -- the ordinary path: kept before it leaves, recorded only on the server's word ---------
{
  const st = storage(), srv = server(), box = O.createOutbox(st)
  srv.mode = 'slow'
  const going = O.deliver(box, srv.net, sent())
  await tick()
  assert.equal(box.get('opr-1').phase, 'sending')
  assert.equal(kept(st, 'opr-1').phase, 'sending', 'kept on the device BEFORE the answer comes back')
  const page2 = O.createOutbox(st)             // a refresh while it is slow
  assert.equal(page2.get('opr-1').text, 'my decision', 'the owner\'s words survive the refresh')
  srv.release()
  assert.equal((await going).kind, 'recorded')
  assert.equal(box.get('opr-1').phase, 'recorded')
  assert.equal(box.get('opr-1').number, 401)
}

// -- a slow answer, refreshed mid-send: asked, never resent, and found recorded ----------
{
  const st = storage(), srv = server(), box = O.createOutbox(st)
  srv.mode = 'slow'
  void O.deliver(box, srv.net, sent())
  await tick()
  const page2 = O.createOutbox(st)             // the refresh; the first page is gone
  srv.mode = 'ok'
  await O.resume(page2, srv.net, 2)
  assert.equal(srv.received, 1, 'the refresh did NOT send it again')
  assert.equal(page2.get('opr-1').phase, 'recorded', 'the server was asked, and it had landed')
  assert.equal(page2.get('opr-1').number, 401)
}

// -- the acknowledgment is lost after the server wrote the post --------------------------
{
  const st = storage(), srv = server(), box = O.createOutbox(st)
  srv.mode = 'lost'
  const got = await O.deliver(box, srv.net, sent())
  assert.equal(got.kind, 'unknown')
  assert.equal(box.get('opr-1').phase, 'unknown', 'neither "sent" nor "failed" is claimed')
  assert.equal(box.get('opr-1').text, 'my decision')
  srv.mode = 'ok'
  assert.equal(await O.ask(box, srv.net, 'opr-1'), 'recorded', 'asking finds it, without writing')
  assert.equal(srv.received, 1)
  assert.equal(box.get('opr-1').phase, 'recorded')
}

// -- lost acknowledgment, then the owner presses Send again: still one post ---------------
{
  const st = storage(), srv = server(), box = O.createOutbox(st)
  srv.mode = '500'
  await O.deliver(box, srv.net, sent())
  assert.equal(box.get('opr-1').phase, 'unknown')
  srv.mode = 'ok'
  const again = await O.deliver(box, srv.net, box.get('opr-1'))
  assert.equal(again.kind, 'recorded')
  assert.equal(srv.received, 2)
  assert.equal(landed(srv), 1, 'sent twice, recorded once: the same operation key')
}

// -- "THE SERVER DOES NOT HOLD IT" IS NOT "IT WAS NOT RECORDED" ----------------------------
// The lookup can run beside a request that is still on its way. Nothing is handed back on
// the strength of it, and the answer that then lands is found.
{
  const st = storage(), srv = server(), box = O.createOutbox(st)
  srv.mode = 'in-transit'
  const going = O.deliver(box, srv.net, sent())
  await tick()
  box.put({ ...box.get('opr-1'), phase: 'unknown', why: 'the page was reloaded before the server answered' })
  assert.equal(await O.ask(box, srv.net, 'opr-1'), 'absent')
  assert.equal(box.get('opr-1').phase, 'unknown')
  assert.equal(box.get('opr-1').why, O.NOT_HELD_YET, 'said as what it is: not held NOW')
  assert.equal(box.get('opr-1').text, 'my decision')
  srv.mode = 'ok'
  srv.arriving()                               // the original request arrives after all
  await going
  assert.equal(landed(srv), 1)
  assert.equal(box.get('opr-1').phase, 'recorded', 'and it is the one answer; no second was ever possible')
}

// -- giving it up is the server's act, and is final either way -----------------------------
{
  // never arrived: voided, the words come back, and the late original can no longer land
  const st = storage(), srv = server(), box = O.createOutbox(st)
  srv.mode = 'in-transit'
  const going = O.deliver(box, srv.net, sent())
  await tick()
  box.put({ ...box.get('opr-1'), phase: 'unknown', why: 'x' })
  const back = await O.giveUp(box, srv.net, 'opr-1')
  assert.deepEqual(back, { outcome: 'voided', pick: { kind: 'own' }, text: 'my decision' })
  assert.equal(box.get('opr-1'), undefined, 'nothing is kept: a different answer may now be sent')
  srv.mode = 'ok'
  srv.arriving()                               // the original turns up late
  assert.equal((await going).kind, 'refused', 'and is refused: it wrote nothing')
  assert.equal(landed(srv), 0, 'the first answer cannot surface beside a second')
}
{
  // it HAD landed: nothing is handed back, and the form says recorded
  const st = storage(), srv = server(), box = O.createOutbox(st)
  srv.mode = 'lost'
  await O.deliver(box, srv.net, sent())
  srv.mode = 'ok'
  assert.deepEqual(await O.giveUp(box, srv.net, 'opr-1'), { outcome: 'recorded' })
  assert.equal(box.get('opr-1').phase, 'recorded')
  assert.equal(landed(srv), 1)
}
{
  // the server cannot be asked: nothing changes, nothing is handed back
  const st = storage(), srv = server(), box = O.createOutbox(st)
  srv.mode = 'down'
  await O.deliver(box, srv.net, sent())
  assert.equal(await O.giveUp(box, srv.net, 'opr-1'), null)
  assert.equal(box.get('opr-1').phase, 'unknown')
  assert.equal(box.get('opr-1').text, 'my decision')
  assert.equal(await O.ask(box, srv.net, 'opr-1'), null, 'and asking, when it cannot be asked, claims nothing')
}

// -- a refusal keeps nothing: nothing was written, the form keeps the draft ---------------
{
  const st = storage(), srv = server(), box = O.createOutbox(st)
  srv.mode = 'refuse'
  const got = await O.deliver(box, srv.net, sent())
  assert.equal(got.kind, 'refused')
  assert.match(got.why, /answers the Turn/)
  assert.equal(box.get('opr-1'), undefined)
  assert.equal(kept(st, 'opr-1'), null)
}

// -- two tabs, at once, about different questions: neither undoes the other ---------------
{
  const st = storage(), srv = server()
  const tabA = O.createOutbox(st), tabB = O.createOutbox(st)      // both opened before anything was sent
  srv.mode = 'slow'
  const a = O.deliver(tabA, srv.net, sent({ ask: 'opr-A' }))
  await tick()
  const releaseA = srv.release
  srv.mode = 'ok'
  await O.deliver(tabB, srv.net, sent({ ask: 'opr-B' }))          // B is sent and recorded while A is out
  releaseA()
  await a                                                          // A now writes its own outcome
  assert.equal(kept(st, 'opr-A').phase, 'recorded')
  assert.equal(kept(st, 'opr-B').phase, 'recorded', 'tab A writing about its question did not erase tab B\'s')
  const page = O.createOutbox(st)                                  // a refresh sees both
  assert.deepEqual(page.all().map((s) => s.ask).sort(), ['opr-A', 'opr-B'])
  // and the same question, from the other tab: it is seen, so it is not answered twice
  assert.equal(tabB.get('opr-A').phase, 'recorded')
}

// -- storage that will not store: the answer is still sent, and says it is not kept --------
{
  const broken = { getItem: () => { throw new Error('denied') }, setItem: () => { throw new Error('quota') }, removeItem: () => { throw new Error('denied') }, length: 0, key: () => null }
  const srv = server(), box = O.createOutbox(broken)
  const got = await O.deliver(box, srv.net, sent())
  assert.equal(got.kind, 'recorded')
  assert.equal(box.get('opr-1').kept, false, 'held on this page only, and marked so')
  assert.equal(box.all().length, 1)
  box.drop('opr-1')
  assert.equal(box.get('opr-1'), undefined)
  const none = O.createOutbox(null)
  assert.equal(none.put(sent()), false)
  assert.equal(none.get('opr-1').kept, false)
}

// -- storage holding rubbish, or other things, does not break the form --------------------
{
  const st = storage()
  st.data.set(O.STORE_PREFIX + 'opr-1', '{not json')
  st.data.set(O.STORE_PREFIX + 'opr-2', JSON.stringify({ ask: 'opr-other', op: 'x' }))
  st.data.set('something-else', 'x')
  assert.deepEqual(O.createOutbox(st).all(), [], 'an entry that is not what was kept is not believed')
  assert.equal(O.createOutbox(st).get('opr-1'), undefined)
}

// -- the record takes over only from an answer the server said it recorded -----------------
{
  const rec = sent({ phase: 'recorded', turn: 'ent-9', number: 423 })
  assert.equal(O.settledBy(rec, { response_present: true }), true, 'recorded, and the question closed')
  assert.equal(O.settledBy(rec, { response_present: false, answered_by: { turn: 'ent-9', number: 423 } }), true,
    'the record lists this reply on the question, though it did not close it')
  assert.equal(O.settledBy(rec, { response_present: false, answered_by: { turn: 'ent-other', number: 7 } }), false,
    'some other reply is not this answer')
  assert.equal(O.settledBy(rec, { response_present: false }), false, 'the record has not shown it yet: still kept')
  // an answer of unknown outcome is NEVER dropped because the question closed some other way
  const unk = sent({ phase: 'unknown' })
  assert.equal(O.settledBy(unk, { response_present: true, answered_by: { turn: 'ent-from-another-tab', number: 9 } }), false,
    'the question was closed by a different answer: this one\'s words are not thrown away')
  assert.equal(O.settledBy(sent({ phase: 'sending' }), { response_present: true }), false)
}

// -- a kept copy is not held for ever, and an unconfirmed one is never dropped by age -------
{
  const st = storage(), srv = server(), box = O.createOutbox(st)
  box.put(sent({ ask: 'opr-old', phase: 'recorded', turn: 'ent-1', number: 1, at: 0 }))
  box.put(sent({ ask: 'opr-new', phase: 'recorded', turn: 'ent-2', number: 2, at: O.KEEP_RECORDED_MS }))
  box.put(sent({ ask: 'opr-unk', phase: 'unknown', at: 0, why: 'x' }))
  srv.mode = 'down'
  await O.resume(box, srv.net, O.KEEP_RECORDED_MS + 1)
  assert.equal(box.get('opr-old'), undefined, 'recorded long ago and never settled by a read: let go')
  assert.equal(box.get('opr-new').phase, 'recorded')
  assert.equal(box.get('opr-unk').text, 'my decision', 'unknown is the owner\'s to give up, whatever its age')
}

// -- an answer settled while it was out is not brought back -------------------------------
{
  const st = storage(), srv = server(), box = O.createOutbox(st)
  srv.mode = 'slow'
  const going = O.deliver(box, srv.net, sent())
  await tick()
  box.drop('opr-1')
  srv.release()
  await going
  assert.equal(box.get('opr-1'), undefined, 'a late answer does not bring back what was already settled')
}

console.log('decision outbox: ok')
