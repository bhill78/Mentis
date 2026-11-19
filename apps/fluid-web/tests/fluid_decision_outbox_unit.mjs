// What becomes of an answer that was sent: slow answers, lost acknowledgments, refreshes,
// duplicate sends, storage that will not store. node tests/fluid_decision_outbox_unit.mjs
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

/** A browser's storage, shared by every "page" made over it. */
function storage() {
  const data = new Map()
  return { data, getItem: (k) => (data.has(k) ? data.get(k) : null), setItem: (k, v) => { data.set(k, v) } }
}

/** A server that records a post ONCE per (author, op), as Mentis does, and can be told to
 *  lose the answer, answer slowly, refuse, or fail. */
function server() {
  const posts = new Map()           // author|op -> {turn, number}
  const s = {
    posts, received: 0, mode: 'ok', hold: null, release: null,
    net: {
      async post(conversation, body) {
        s.received++
        if (s.mode === 'refuse') return { status: 200, body: { error: 'a withdrawal answers the Turn that asked for the decision' } }
        if (s.mode === 'down') throw new TypeError('Failed to fetch')           // never reached the server
        const key = `${body.author}|${body.op}`
        if (!posts.has(key)) posts.set(key, { turn: `ent-${posts.size + 1}`, number: 400 + posts.size + 1, dispatched: 0 })
        const answer = { ...posts.get(key), ...(s.received > 1 && posts.size === 1 ? { replayed: true } : {}) }
        if (s.mode === 'slow') await new Promise((r) => { s.release = r })
        if (s.mode === 'lost') throw new TypeError('Failed to fetch')           // written, answer lost
        if (s.mode === '500') return { status: 502, body: null }                // written, proxy failed
        return { status: 200, body: answer }
      },
      async lookup(op, author) {
        if (s.mode === 'down') throw new TypeError('Failed to fetch')
        const got = posts.get(`${author}|${op}`)
        return got ? { recorded: true, result: got } : { recorded: false }
      },
    },
  }
  return s
}

const sent = (over = {}) => ({
  ask: 'opr-1', op: O.newOp('opr-1', () => 'u1'), conversation: 'ent-c', author: 'ent-owner',
  body: { author: 'ent-owner', text: 'my decision', op: O.newOp('opr-1', () => 'u1') },
  pick: { kind: 'own' }, text: 'my decision', label: null, continued: false, phase: 'sending', at: 1,
  turn: null, number: null, dispatched: null, why: null, kept: true, ...over,
})

// -- what an answer means --------------------------------------------------------------
assert.deepEqual(O.outcomeOf(200, { turn: 'ent-9', number: 423, dispatched: 1 }), { kind: 'recorded', turn: 'ent-9', number: 423, dispatched: 1 })
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
  await new Promise((r) => setTimeout(r, 0))
  assert.equal(box.get('opr-1').phase, 'sending')
  assert.equal(JSON.parse(st.data.get(O.STORE_KEY))['opr-1'].phase, 'sending', 'kept on the device BEFORE the answer comes back')
  // a refresh while it is slow: a new page over the same storage
  const page2 = O.createOutbox(st)
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
  await new Promise((r) => setTimeout(r, 0))
  const page2 = O.createOutbox(st)             // the refresh; the first page is gone
  srv.mode = 'ok'
  await O.resume(page2, srv.net)
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
  assert.equal(srv.posts.size, 1)
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
  assert.equal(srv.posts.size, 1, 'sent twice, recorded once: the same operation key')
  assert.equal(box.get('opr-1').number, 401)
}

// -- it never reached the server: asked, said to be not recorded, words kept --------------
{
  const st = storage(), srv = server(), box = O.createOutbox(st)
  srv.mode = 'down'
  await O.deliver(box, srv.net, sent())
  assert.equal(box.get('opr-1').phase, 'unknown')
  assert.equal(await O.ask(box, srv.net, 'opr-1'), null, 'the server could not be asked: still unknown, nothing claimed')
  assert.notEqual(box.get('opr-1').why, O.NOT_RECORDED)
  srv.mode = 'ok'
  assert.equal(await O.ask(box, srv.net, 'opr-1'), 'absent')
  assert.equal(box.get('opr-1').why, O.NOT_RECORDED)
  assert.equal(box.get('opr-1').text, 'my decision', 'and the owner\'s words are still here')
  assert.equal(srv.posts.size, 0, 'asking wrote nothing')
}

// -- a refusal keeps nothing: nothing was written, the form keeps the draft ---------------
{
  const st = storage(), srv = server(), box = O.createOutbox(st)
  srv.mode = 'refuse'
  const got = await O.deliver(box, srv.net, sent())
  assert.equal(got.kind, 'refused')
  assert.match(got.why, /answers the Turn/)
  assert.equal(box.get('opr-1'), undefined)
  assert.equal(JSON.parse(st.data.get(O.STORE_KEY))['opr-1'], undefined)
}

// -- two tabs: what one sent, the other sees ----------------------------------------------
{
  const st = storage(), srv = server()
  const tab1 = O.createOutbox(st), tab2 = O.createOutbox(st)
  await O.deliver(tab1, srv.net, sent())
  tab2.refresh()
  assert.equal(tab2.get('opr-1').phase, 'recorded', 'the second tab knows an answer was sent, and will not send another')
}

// -- storage that will not store: the answer is still sent, and says it is not kept --------
{
  const broken = { getItem: () => { throw new Error('denied') }, setItem: () => { throw new Error('quota') } }
  const srv = server(), box = O.createOutbox(broken)
  const got = await O.deliver(box, srv.net, sent())
  assert.equal(got.kind, 'recorded')
  assert.equal(box.get('opr-1').kept, false, 'held on this page only, and marked so')
  const none = O.createOutbox(null)
  assert.equal(none.put(sent()), false)
  assert.equal(none.get('opr-1').kept, false)
}

// -- storage holding rubbish does not break the form -------------------------------------
{
  const st = storage()
  st.data.set(O.STORE_KEY, '{not json')
  assert.deepEqual(O.createOutbox(st).all(), [])
  st.data.set(O.STORE_KEY, JSON.stringify({ 'opr-1': { ask: 'opr-other', op: 'x' }, 'opr-2': null }))
  assert.deepEqual(O.createOutbox(st).all(), [], 'an entry that is not what was kept is not believed')
}

// -- the record takes over ---------------------------------------------------------------
{
  const s = sent({ phase: 'recorded', turn: 'ent-9', number: 423 })
  assert.equal(O.settledBy(s, { response_present: true }), true, 'the question closed')
  assert.equal(O.settledBy(s, { response_present: false, answered_by: { turn: 'ent-9', number: 423 } }), true,
    'the record lists this reply on the question, though it did not close it')
  assert.equal(O.settledBy(s, { response_present: false, answered_by: { turn: 'ent-other', number: 7 } }), false,
    'some other reply is not this answer')
  assert.equal(O.settledBy(s, { response_present: false }), false, 'the record has not shown it yet: still kept')
  assert.equal(O.settledBy(sent({ phase: 'unknown' }), { response_present: false, answered_by: { turn: 'ent-9', number: 423 } }), false,
    'an answer of unknown outcome is not settled by a reply it cannot be matched to')
}

// -- an answer overtaken while it was out is not overwritten -----------------------------
{
  const st = storage(), srv = server(), box = O.createOutbox(st)
  srv.mode = 'slow'
  const going = O.deliver(box, srv.net, sent())
  await new Promise((r) => setTimeout(r, 0))
  box.drop('opr-1')                         // the record read showed the question closed meanwhile
  srv.release()
  await going
  assert.equal(box.get('opr-1'), undefined, 'a late answer does not bring back what the record already settled')
}

console.log('decision outbox: ok')
