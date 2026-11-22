/* THE MAGNET'S MINI CONVERSATION: state, HTTP boundary and what it draws.
 *
 * Every read and every write in this file goes through an INJECTED seam over a
 * synthetic fixture. Nothing here opens a Brain, starts a server or reaches the
 * network, and the only mutation exercised is the one the card makes when Send
 * is pressed, answered by a fixture. */
import assert from 'node:assert/strict'
import { test } from 'node:test'
import { readFileSync } from 'node:fs'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { createBinding, type Binding } from '../src/brainBinding'
import type { MagnetResource } from '../src/quiet2/magnets/contract'
import MiniConversation, { PostView, Words, WorkLine } from '../src/quiet2/magnets/MiniConversation'
import {
  CANNOT_WRITE, IN_FLIGHT_SEND, MALFORMED_SEND, NO_OWNER, NO_OWN_CONVERSATION, OTHER_BRAIN, OTHER_IDENTITY,
  OWN_IS_A_SOURCE, UNCERTAIN_SEND, UNCONFIRMED_BRAIN,
  adaptTurn, anyMiniDraft, confirmedBrain, corpusOfBoundBrain, corpusOfSpaceKey, createMiniConversation,
  discardMiniDraft, forgetMiniDrafts, hasMiniDraft, miniAttempt, miniDraft, miniReplyTarget, ownConversation,
  setMiniDraft, sourceConversations,
  type MiniAnswer, type MiniAt, type MiniGet, type MiniSend,
} from '../src/quiet2/magnets/conversation'

/* -- the synthetic fixture -------------------------------------------------- */

const CORPUS = 'corpus-fixture-a'
const SPACE_KEY = `https://fixture.invalid|dev|${CORPUS}`
const BOUND = `${CORPUS}@instance-1`
const SOURCE = 'ent-source111111'
const OWN = 'ent-ownconv11111'
const ME = 'ent-ownerme11111'

const config = (over: Record<string, unknown> = {}) => ({
  id: 'mag-fixtureA' as const,
  sources: [{ kind: 'conversation' as const, conversation: SOURCE }],
  selection: {},
  collection: { mode: 'one-time' as const },
  synthesis: { mode: 'manual' as const },
  notifications: { newItems: false, changes: false, failures: false },
  presentation: { renderer: 'disc' as const },
  conversation: OWN,
  ...over,
})

let ids = 0
const resourceFor = (over: Record<string, unknown> = {}, key = SPACE_KEY): MagnetResource => ({
  id: `mg${++ids}`, brainKey: key,
  saved: { id: 'mag-fixtureA', name: 'Fixture collection', config: config(over) as never },
  snapshot: () => ({}) as never, subscribe: () => () => {}, update: () => {},
  read: async () => {}, cancel: () => {}, dispose: () => {},
} as unknown as MagnetResource)

const turn = (over: Record<string, unknown> = {}) => ({
  id: 'ent-post11111a', number: 1, parts: [{ type: 'text', text: 'First words.' }],
  author: ME, author_alias: '@brian', written_by: null, at: 1795000000,
  addressees: [], topics: [], answering: null, replies: [], expectations: [], operational_acts: 0,
  ...over,
})

const conversationBody = (over: Record<string, unknown> = {}) => ({
  id: OWN, name: 'Magnet working notes', about: '', participants: [{ participant: ME, alias: '@brian' }],
  topics: [], instructions: [], turns: [turn()], turns_total: 1, focus_topic: null, awaiting: [],
  owed: [], batch: { older: 0, first: 1 }, failures: [],
  ...over,
})

/** A seam that records every path it was asked for. */
function seam(answers: (path: string, n: number) => MiniAnswer) {
  const paths: string[] = []
  const get: MiniGet = async (path) => { paths.push(path); return answers(path, paths.length) }
  return { paths, get }
}

const participants = (me: string | null): MiniAnswer => ({
  status: 200, body: { participants: [{ id: 'ent-someoneelse1' }], matched: 1, limit: 1, me },
})

const sends: { path: string; body: Record<string, unknown>; headers: Record<string, string> }[] = []
const sender = (answer: () => Promise<MiniAnswer>): MiniSend => async (path, body, headers) => {
  sends.push({ path, body: body as Record<string, unknown>, headers })
  return answer()
}

const bound = (key: string | null): Binding => {
  const b = createBinding()
  if (key) b.saw(key)
  return b
}

/* Keys are minted from ONE counter for the whole file, so a key that is the
   same across two mounts is a key that was genuinely reused rather than one a
   fresh per-mount counter happened to produce again. */
let keys = 0
const store = (at: Partial<MiniAt> & Pick<MiniAt, 'resource'>) => createMiniConversation({
  canWrite: true,
  binding: bound(BOUND),
  now: async (b) => b.moved() ? null : b.bound(),
  op: () => `op-fixture-${++keys}`,
  ...at,
} as MiniAt)

/* -- which Conversation is the Magnet's own --------------------------------- */

test('the Magnet’s own Conversation must exist and differ from every source', () => {
  assert.deepEqual(ownConversation(resourceFor()), { conversation: OWN })
  assert.deepEqual(ownConversation(resourceFor({ conversation: null })), { unavailable: NO_OWN_CONVERSATION })
  assert.deepEqual(ownConversation(resourceFor({ conversation: undefined })), { unavailable: NO_OWN_CONVERSATION })
  assert.deepEqual(ownConversation(resourceFor({ conversation: 'not-an-entry' })), { unavailable: NO_OWN_CONVERSATION })
  /* the saved Conversation IS the source it collects from: no own Conversation */
  assert.deepEqual(ownConversation(resourceFor({ conversation: SOURCE })), { unavailable: OWN_IS_A_SOURCE })
  /* a source of another kind that names a Conversation counts just as much */
  assert.deepEqual(
    ownConversation(resourceFor({ sources: [{ kind: 'agent-results', conversation: OWN }], conversation: OWN })),
    { unavailable: OWN_IS_A_SOURCE })
  assert.deepEqual(sourceConversations(config({ sources: [{ kind: 'conversation', conversation: SOURCE }, { kind: 'agent-results', conversation: OWN }] })), [SOURCE, OWN])
})

test('an unavailable own Conversation reads nothing and offers no send', async () => {
  const { paths, get } = seam(() => ({ status: 200, body: conversationBody() }))
  const s = store({ resource: resourceFor({ conversation: SOURCE }), get })
  await s.read()
  await s.send()
  assert.equal(s.conversation, null)
  assert.deepEqual(paths, [])
  assert.equal(sends.length, 0)
  assert.equal(s.snapshot().unavailable, OWN_IS_A_SOURCE)
  s.dispose()
})

/* -- which Brain ------------------------------------------------------------ */

test('the resource key and the page binding are compared on the corpus they both name', async () => {
  assert.equal(corpusOfSpaceKey(SPACE_KEY), CORPUS)
  assert.equal(corpusOfSpaceKey('no-separators'), '')
  assert.equal(corpusOfBoundBrain(BOUND), CORPUS)
  assert.equal(corpusOfBoundBrain('no-at-sign'), '')
  const r = resourceFor()
  /* the two keys are never equal, so a naive comparison would refuse everything */
  assert.notEqual(r.brainKey, BOUND)
  assert.deepEqual(await confirmedBrain(r, bound(BOUND), async (b) => b.bound()), { ok: true, brain: BOUND })
  assert.deepEqual(await confirmedBrain(r, bound(null), async (b) => b.bound()), { ok: false, why: UNCONFIRMED_BRAIN })
  assert.deepEqual(await confirmedBrain(r, bound('corpus-other@instance-1'), async (b) => b.bound()),
    { ok: false, why: OTHER_BRAIN })
  /* a moved page cannot say which Brain it is on at all */
  const moved = bound(BOUND); moved.move()
  assert.deepEqual(await confirmedBrain(r, moved, async (b) => b.moved() ? null : b.bound()),
    { ok: false, why: UNCONFIRMED_BRAIN })
})

/* -- reading the real Conversation ------------------------------------------ */

test('the latest page is read with CLIENT headers’ own API, nested and counted as the read states it', async () => {
  const { paths, get } = seam(() => ({
    status: 200,
    body: conversationBody({
      turns: [
        turn({ id: 'ent-post11111a', number: 1, thread_replies: 1, replies: ['ent-post11111b'] }),
        turn({ id: 'ent-post11111b', number: 2, answering: 'ent-post11111a', answering_number: 1, root: 'ent-post11111a', parts: [{ type: 'text', text: 'A real reply.' }], written_by: 'claude/abc123', author_alias: '@Builder' }),
      ],
      turns_total: 42, owed: [{ expectation: 'opr-1' }, { expectation: 'opr-2' }],
      batch: { older: 7, first: 1 },
    }),
  }))
  const s = store({ resource: resourceFor(), get })
  await s.read()
  assert.deepEqual(paths, [`/api/conversations/${OWN}?batch=30`])
  const snap = s.snapshot()
  assert.equal(snap.name, 'Magnet working notes')
  assert.equal(snap.total, 42)
  assert.equal(snap.owed, 2)
  assert.equal(snap.older, 7)
  assert.equal(snap.first, 1)
  /* a reply whose root is in hand hangs under it rather than beside it */
  assert.deepEqual(snap.posts.map((p) => p.id), ['ent-post11111a'])
  assert.equal(snap.posts[0].replies, 1)
  assert.equal(snap.error, undefined)
  s.dispose()
})

test('a refusal, a wrong Conversation and a bad status are said and never substituted', async () => {
  for (const [answer, pattern] of [
    [{ status: 200, body: { error: 'this conversation is in Trash' } }, /Trash/],
    [{ status: 200, body: conversationBody({ id: 'ent-elsewhere111' }) }, /another Conversation/],
    [{ status: 403, body: {} }, /403/],
    [{ status: 200, body: { id: OWN } }, /could not be understood/],
  ] as [MiniAnswer, RegExp][]) {
    const { get } = seam(() => answer)
    const s = store({ resource: resourceFor(), get })
    await s.read()
    assert.match(s.snapshot().error!, pattern)
    assert.deepEqual(s.snapshot().posts, [])
    assert.equal(s.snapshot().total, null)
    s.dispose()
  }
})

test('earlier posts are one bounded page before the first, merged ahead and never re-read wider', async () => {
  const { paths, get } = seam((path) => path.includes('before=')
    ? { status: 200, body: conversationBody({ turns: [turn({ id: 'ent-older111111', number: 0 })], batch: { older: 0, first: 0 } }) }
    : { status: 200, body: conversationBody({ batch: { older: 3, first: 1 } }) })
  const s = store({ resource: resourceFor(), get })
  await s.read()
  await s.earlier()
  assert.deepEqual(paths, [`/api/conversations/${OWN}?batch=30`, `/api/conversations/${OWN}?batch=30&before=1`])
  assert.deepEqual(s.snapshot().posts.map((p) => p.id), ['ent-older111111', 'ent-post11111a'])
  assert.equal(s.snapshot().older, 0)
  /* nothing older is left to ask for, so asking again asks nothing */
  await s.earlier()
  assert.equal(paths.length, 2)
  s.dispose()
})

test('one thread is read by its root, sorted, and a failed thread never empties the flow', async () => {
  const { paths, get } = seam((path) => path.includes('/thread/')
    ? { status: 200, body: { conversation: OWN, root: 'ent-post11111a', turn: turn(), replies_total: 2, replies: [turn({ id: 'ent-r2', number: 9 }), turn({ id: 'ent-r1', number: 4 })] } }
    : { status: 200, body: conversationBody() })
  const s = store({ resource: resourceFor(), get })
  await s.read()
  await s.openThread('ent-post11111a')
  assert.equal(paths[1], `/api/conversations/${OWN}/thread/ent-post11111a`)
  assert.deepEqual(s.snapshot().thread!.replies.map((p) => p.id), ['ent-r1', 'ent-r2'])
  s.closeThread()
  assert.equal(s.snapshot().thread, null)
  s.dispose()

  const failing = store({ resource: resourceFor(), get: seam((path) => path.includes('/thread/') ? { status: 503, body: {} } : { status: 200, body: conversationBody() }).get })
  await failing.read()
  await failing.openThread('ent-post11111a')
  assert.match(failing.snapshot().thread!.error!, /503/)
  assert.equal(failing.snapshot().posts.length, 1)
  failing.dispose()
})

test('cancel and disposal reject late answers rather than letting them land', async () => {
  let answer!: (v: MiniAnswer) => void
  const s = store({ resource: resourceFor(), get: () => new Promise<MiniAnswer>((r) => { answer = r }) })
  const pending = s.read()
  s.cancel()
  answer({ status: 200, body: conversationBody() })
  await pending
  assert.deepEqual(s.snapshot().posts, [])
  assert.equal(s.snapshot().loading, false)
  const again = s.read()
  s.dispose()
  answer({ status: 200, body: conversationBody() })
  await again
  assert.deepEqual(s.snapshot().posts, [])
})

/* -- Work, as the read states it -------------------------------------------- */

test('Work states come from the record’s own fields, and a claim is not an answer', () => {
  const work = (e: Record<string, unknown>) => adaptTurn(turn({ expectations: [{ id: 'opr-1', expects: 'do it', of: null, of_alias: null, by_alias: '@brian', response_present: false, live_execution: false, ...e }] }) as never).work[0]
  assert.equal(work({}).state, 'open')
  assert.equal(work({}).unassigned, true)
  assert.equal(work({ of: 'ent-carrier11111', of_alias: '@Builder' }).unassigned, false)
  assert.equal(work({ satisfied_by: ['opr-9'] }).state, 'claimed')
  assert.equal(work({ answered_by: { turn: 'ent-x', number: 2, said: '', author: ME, chose: null } }).state, 'answered')
  assert.equal(work({ lapsed: { act: 'opr-l', by: ME, by_alias: null, at: 1, because: null, reason: null, run: null } }).state, 'lapsed')
  assert.equal(work({ withdrawn: { act: 'opr-w', by: ME, by_alias: null, at: 1, because: null, reply: null }, answered_by: { turn: 'ent-x', number: 2, said: '', author: ME, chose: null } }).state, 'withdrawn')
  assert.equal(work({ live_execution: true }).liveExecution, true)
})

/* -- the write boundary ------------------------------------------------------ */

test('no capability means no write leaves the card at all', async () => {
  sends.length = 0
  const { paths, get } = seam(() => ({ status: 200, body: conversationBody() }))
  const s = store({ resource: resourceFor(), canWrite: false, get, post: sender(async () => ({ status: 200, body: {} })) })
  await s.read()
  s.draft('words that must not go anywhere')
  await s.send()
  assert.equal(sends.length, 0)
  assert.equal(s.snapshot().sendError, CANNOT_WRITE)
  /* and the participants read was never even made */
  assert.deepEqual(paths, [`/api/conversations/${OWN}?batch=30`])
  s.dispose(); forgetMiniDrafts()
})

test('a send names the owner the server names, the bound Brain, and records only', async () => {
  sends.length = 0
  const { paths, get } = seam((path) => path.startsWith('/fluid/api/participants')
    ? participants(ME)
    : { status: 200, body: conversationBody() })
  const mine = resourceFor()
  const s = store({
    resource: mine, get,
    post: sender(async () => ({ status: 200, body: { post: 'ent-new111111a', home: OWN, number: 2, replayed: false } })),
  })
  await s.read()
  s.draft('  A real message.  ')
  await s.send()
  assert.equal(sends.length, 1)
  assert.equal(sends[0].path, '/fluid/api/posts')
  assert.equal(sends[0].headers['X-Mentis-Brain'], BOUND)
  assert.equal(sends[0].body.conversation, OWN)
  assert.equal(sends[0].body.author, ME)
  assert.equal(sends[0].body.action, 'record-only')
  assert.equal(sends[0].body.dispatch, undefined)
  assert.equal(sends[0].body.addressed_to, undefined)
  assert.equal(sends[0].body.text, 'A real message.')
  assert.equal(sends[0].body.parts, undefined)
  assert.equal(sends[0].body.text, 'A real message.')
  assert.equal('replies_to' in sends[0].body, false)
  assert.equal(typeof sends[0].body.op, 'string')
  assert.deepEqual(s.snapshot().sent, { post: 'ent-new111111a', number: 2, replayed: false })
  /* the draft is gone, for this Magnet, and the Conversation was read again */
  assert.equal(s.snapshot().draft, '')
  assert.equal(hasMiniDraft(mine), false)
  assert.equal(anyMiniDraft(), false)
  assert.equal(paths.filter((p) => p === `/api/conversations/${OWN}?batch=30`).length, 2)
  assert.equal(s.snapshot().sending, false)
  s.dispose(); forgetMiniDrafts()
})

test('a record naming no owner is a refusal, never participants[0]', async () => {
  sends.length = 0
  const { get } = seam((path) => path.startsWith('/fluid/api/participants')
    ? participants(null)
    : { status: 200, body: conversationBody() })
  const s = store({ resource: resourceFor(), get, post: sender(async () => ({ status: 200, body: {} })) })
  await s.read()
  s.draft('words')
  await s.send()
  assert.equal(sends.length, 0)
  assert.equal(s.snapshot().sendError, NO_OWNER)
  assert.equal(s.snapshot().draft, 'words')
  s.dispose(); forgetMiniDrafts()
})

test('an explicit reply names the post it answers; replying to the Conversation clears it', async () => {
  sends.length = 0
  const { get } = seam((path) => path.startsWith('/fluid/api/participants')
    ? participants(ME)
    : { status: 200, body: conversationBody() })
  const s = store({ resource: resourceFor(), get, post: sender(async () => ({ status: 200, body: { post: 'ent-new111111a', number: 3 } })) })
  await s.read()
  s.replyTo(s.snapshot().posts[0])
  assert.deepEqual(s.snapshot().replyTo, { id: 'ent-post11111a', number: 1, alias: '@brian' })
  s.draft('An answer.')
  await s.send()
  assert.equal(sends[0].body.replies_to, 'ent-post11111a')
  assert.equal(s.snapshot().replyTo, null)
  s.replyTo(null)
  assert.equal(s.snapshot().replyTo, null)
  s.dispose(); forgetMiniDrafts()
})

test('an uncertain send is never resent blindly: the words and the key are both kept', async () => {
  sends.length = 0
  let fail = true
  const { get } = seam((path) => path.startsWith('/fluid/api/participants') ? participants(ME) : { status: 200, body: conversationBody() })
  const s = store({
    resource: resourceFor(), get,
    post: sender(async () => { if (fail) throw new TypeError('network'); return { status: 200, body: { post: 'ent-new111111a', number: 2, replayed: true } } }),
  })
  await s.read()
  s.draft('Possibly recorded.')
  await s.send()
  assert.equal(sends.length, 1)
  assert.equal(s.snapshot().uncertain, true)
  assert.equal(s.snapshot().sendError, UNCERTAIN_SEND)
  assert.equal(s.snapshot().draft, 'Possibly recorded.')
  /* nothing went again by itself */
  assert.equal(sends.length, 1)
  /* the owner pressing send again reuses the SAME key, so the door cannot
     record a second post */
  fail = false
  await s.send()
  assert.equal(sends.length, 2)
  assert.equal(sends[1].body.op, sends[0].body.op)
  assert.equal(s.snapshot().sent!.replayed, true)
  assert.equal(s.snapshot().uncertain, false)
  s.dispose(); forgetMiniDrafts()
})

test('after an uncertain send, different words are a different post and get their own key', async () => {
  sends.length = 0
  let fail = true
  const { get } = seam((path) => path.startsWith('/fluid/api/participants') ? participants(ME) : { status: 200, body: conversationBody() })
  const s = store({
    resource: resourceFor(), get,
    post: sender(async () => { if (fail) throw new TypeError('network'); return { status: 200, body: { post: 'ent-new111111a', number: 2 } } }),
  })
  await s.read()
  s.draft('First try.')
  await s.send()
  assert.equal(s.snapshot().uncertain, true)
  s.draft('Different words entirely.')
  assert.equal(s.snapshot().uncertain, false)
  fail = false
  await s.send()
  assert.notEqual(sends[1].body.op, sends[0].body.op)
  s.dispose(); forgetMiniDrafts()
})

test('words typed while a send is in flight survive it, and a second press is not a second post', async () => {
  sends.length = 0
  const { get } = seam((path) => path.startsWith('/fluid/api/participants') ? participants(ME) : { status: 200, body: conversationBody() })
  let land!: (v: MiniAnswer) => void
  const mine = resourceFor()
  const s = store({ resource: mine, get, post: sender(() => new Promise<MiniAnswer>((r) => { land = r })) })
  await s.read()
  s.draft('the words that are going')
  const sending = s.send()
  await new Promise((r) => setImmediate(r))
  assert.equal(sends.length, 1)
  assert.equal(s.snapshot().sending, true)
  /* the owner keeps typing while it is in flight */
  s.draft('the words that are going, and more since')
  /* pressing Send again while one is in flight writes nothing more */
  await s.send()
  assert.equal(sends.length, 1)
  land({ status: 200, body: { post: 'ent-new111111a', number: 2 } })
  await sending
  assert.equal(s.snapshot().draft, 'the words that are going, and more since')
  assert.equal(hasMiniDraft(mine), true)
  assert.equal(s.snapshot().sending, false)
  s.dispose(); forgetMiniDrafts()
})

test('a refusal and a moved Brain keep the words and start nothing again', async () => {
  sends.length = 0
  const { get } = seam((path) => path.startsWith('/fluid/api/participants') ? participants(ME) : { status: 200, body: conversationBody() })
  const refused = store({ resource: resourceFor(), get, post: sender(async () => ({ status: 422, body: { error: 'this conversation is in Trash', refused: true } })) })
  await refused.read()
  refused.draft('words')
  await refused.send()
  assert.equal(refused.snapshot().sendError, 'this conversation is in Trash')
  assert.equal(refused.snapshot().uncertain, false)
  assert.equal(refused.snapshot().draft, 'words')
  refused.dispose(); forgetMiniDrafts()

  const binding = bound(BOUND)
  const moved = createMiniConversation({
    resource: resourceFor(), canWrite: true, get, binding,
    now: async (b) => b.moved() ? null : b.bound(), op: () => 'op-moved',
    post: sender(async () => ({ status: 409, body: { kind: 'BrainChanged', error: 'this server now serves another Brain' } })),
  })
  await moved.read()
  moved.draft('words')
  await moved.send()
  assert.equal(binding.moved(), true)
  assert.match(moved.snapshot().sendError!, /another Brain/)
  assert.ok(moved.snapshot().identity)
  assert.equal(moved.snapshot().draft, 'words')
  const before = sends.length
  await moved.send()
  /* a moved page cannot name a Brain, so the second press never reaches the door */
  assert.equal(sends.length, before)
  moved.dispose(); forgetMiniDrafts()
})

/* -- an attempt outlives the card that made it ------------------------------- */

test('an uncertain send survives the card: the remounted retry is the same key and the same reply target', async () => {
  forgetMiniDrafts(); sends.length = 0
  let fail = true
  const { get } = seam((path) => path.startsWith('/fluid/api/participants') ? participants(ME) : { status: 200, body: conversationBody() })
  const mine = resourceFor()
  const post = sender(async () => {
    if (fail) throw new TypeError('network')
    return { status: 200, body: { post: 'ent-new111111a', number: 2, replayed: true } }
  })
  const first = store({ resource: mine, get, post })
  await first.read()
  first.replyTo(first.snapshot().posts[0])
  first.draft('Possibly recorded, possibly not.')
  await first.send()
  assert.equal(sends.length, 1)
  assert.equal(first.snapshot().uncertain, true)
  assert.equal(sends[0].body.replies_to, 'ent-post11111a')

  /* collapse, a tab change, the parent: the card goes away mid-uncertainty */
  first.dispose()
  const kept = miniAttempt(mine)!
  assert.equal(kept.state, 'uncertain')
  assert.equal(kept.op, sends[0].body.op)
  assert.equal(kept.replyTo, 'ent-post11111a')
  assert.equal(kept.author, ME)
  assert.equal(kept.brain, BOUND)
  assert.deepEqual(miniReplyTarget(mine), { id: 'ent-post11111a', number: 1, alias: '@brian' })

  /* it comes back knowing exactly what it does not know */
  const again = store({ resource: mine, get, post })
  const back = again.snapshot()
  assert.equal(back.uncertain, true)
  assert.equal(back.uncertainOp, kept.op)
  assert.equal(back.sendError, UNCERTAIN_SEND)
  assert.equal(back.draft, 'Possibly recorded, possibly not.')
  assert.deepEqual(back.replyTo, { id: 'ent-post11111a', number: 1, alias: '@brian' })
  await again.read()

  /* the owner's deliberate retry: the SAME key and the SAME reply target, so
     the door answers from what it recorded rather than writing a second post */
  fail = false
  await again.send()
  assert.equal(sends.length, 2)
  assert.equal(sends[1].body.op, sends[0].body.op)
  assert.equal(sends[1].body.replies_to, 'ent-post11111a')
  assert.equal(again.snapshot().sent!.replayed, true)
  assert.equal(again.snapshot().uncertain, false)
  assert.equal(miniAttempt(mine), null)
  assert.equal(miniReplyTarget(mine), null)
  again.dispose(); forgetMiniDrafts()
})

test('a send still on its way when the card is put away cannot go again under a second key', async () => {
  forgetMiniDrafts(); sends.length = 0
  const { get } = seam((path) => path.startsWith('/fluid/api/participants') ? participants(ME) : { status: 200, body: conversationBody() })
  let land!: (v: MiniAnswer) => void
  const mine = resourceFor()
  const first = store({ resource: mine, get, post: sender(() => new Promise<MiniAnswer>((r) => { land = r })) })
  await first.read()
  first.draft('in flight when the card closed')
  const flying = first.send()
  await new Promise((r) => setImmediate(r))
  assert.equal(sends.length, 1)

  /* unmounted WHILE the write is on its way: nothing knows its outcome yet */
  first.dispose()
  assert.equal(miniAttempt(mine)!.state, 'in-flight')
  assert.equal(miniAttempt(mine)!.op, sends[0].body.op)

  const again = store({
    resource: mine, get,
    post: sender(async () => ({ status: 200, body: { post: 'ent-new111111a', number: 2, replayed: true } })),
  })
  assert.equal(again.snapshot().uncertain, true)
  assert.equal(again.snapshot().sendError, IN_FLIGHT_SEND)
  assert.equal(again.snapshot().draft, 'in flight when the card closed')
  await again.read()
  await again.send()
  assert.equal(sends.length, 2)
  assert.equal(sends[1].body.op, sends[0].body.op, 'the remount reused the in-flight key')
  assert.equal(again.snapshot().sent!.replayed, true)
  assert.equal(miniAttempt(mine), null)

  /* the first one landing late emits into nothing and revives no key */
  land({ status: 200, body: { post: 'ent-new111111a', number: 2, replayed: true } })
  await flying
  assert.equal(sends.length, 2)
  assert.equal(miniAttempt(mine), null)
  assert.equal(again.snapshot().draft, '')
  again.dispose(); forgetMiniDrafts()
})

test('a late malformed answer does not revive a key a later press already resolved', async () => {
  forgetMiniDrafts(); sends.length = 0
  const { get } = seam((path) => path.startsWith('/fluid/api/participants') ? participants(ME) : { status: 200, body: conversationBody() })
  let land!: (v: MiniAnswer) => void
  const mine = resourceFor()
  const first = store({ resource: mine, get, post: sender(() => new Promise<MiniAnswer>((r) => { land = r })) })
  await first.read()
  first.draft('the words in flight')
  const flying = first.send()
  await new Promise((r) => setImmediate(r))
  first.dispose()

  const again = store({
    resource: mine, get,
    post: sender(async () => ({ status: 200, body: { post: 'ent-new111111a', number: 2, replayed: true } })),
  })
  await again.read()
  await again.send()
  assert.equal(miniAttempt(mine), null)
  /* the abandoned flight answers 200 without naming a post, long after */
  land({ status: 200, body: { home: OWN } })
  await flying
  assert.equal(miniAttempt(mine), null, 'a resolved post is not made uncertain again')
  again.dispose(); forgetMiniDrafts()
})

test('200 that names no recorded post is unknown, not sent: the words and the key both stay', async () => {
  for (const body of [{}, null, { post: null }, { post: '' }, { post: 'not-an-entry' }, { post: 42 }, { home: OWN, number: 2 }]) {
    forgetMiniDrafts(); sends.length = 0
    const { paths, get } = seam((path) => path.startsWith('/fluid/api/participants') ? participants(ME) : { status: 200, body: conversationBody() })
    const mine = resourceFor()
    const s = store({ resource: mine, get, post: sender(async () => ({ status: 200, body })) })
    await s.read()
    s.draft('words whose fate the answer did not say')
    await s.send()
    const snap = s.snapshot()
    const what = JSON.stringify(body)
    assert.equal(sends.length, 1, what)
    /* NOT a success: nothing is shown as recorded */
    assert.equal(snap.sent, undefined, `${what} is not a sent result`)
    assert.equal(snap.uncertain, true, what)
    assert.equal(snap.sendError, MALFORMED_SEND, what)
    /* the words and the key are both kept until the record itself says */
    assert.equal(snap.draft, 'words whose fate the answer did not say', what)
    assert.equal(hasMiniDraft(mine), true, what)
    const kept = miniAttempt(mine)!
    assert.equal(kept.state, 'malformed', what)
    assert.equal(kept.op, sends[0].body.op, what)
    /* and it re-reads, so the owner can see what is actually there */
    assert.equal(paths.filter((p) => p === `/api/conversations/${OWN}?batch=30`).length, 2, what)
    assert.equal(snap.sending, false, what)
    s.dispose(); forgetMiniDrafts()
  }
})

test('a retry after a malformed answer is the same key, across a remount', async () => {
  forgetMiniDrafts(); sends.length = 0
  let malformed = true
  const { get } = seam((path) => path.startsWith('/fluid/api/participants') ? participants(ME) : { status: 200, body: conversationBody() })
  const mine = resourceFor()
  const post = sender(async () => malformed
    ? { status: 200, body: { home: OWN, number: 2 } }
    : { status: 200, body: { post: 'ent-new111111a', number: 2, replayed: true } })
  const first = store({ resource: mine, get, post })
  await first.read()
  first.draft('said nothing about whether it landed')
  await first.send()
  assert.equal(first.snapshot().uncertain, true)
  first.dispose()

  const again = store({ resource: mine, get, post })
  assert.equal(again.snapshot().uncertain, true)
  assert.equal(again.snapshot().sendError, MALFORMED_SEND)
  await again.read()
  malformed = false
  await again.send()
  assert.equal(sends.length, 2)
  assert.equal(sends[1].body.op, sends[0].body.op)
  assert.deepEqual(again.snapshot().sent, { post: 'ent-new111111a', number: 2, replayed: true })
  assert.equal(miniAttempt(mine), null)
  again.dispose(); forgetMiniDrafts()
})

test('the same words under a key sent as another owner are refused rather than resent', async () => {
  forgetMiniDrafts(); sends.length = 0
  let me = ME
  let fail = true
  const { get } = seam((path) => path.startsWith('/fluid/api/participants') ? participants(me) : { status: 200, body: conversationBody() })
  const mine = resourceFor()
  const s = store({
    resource: mine, get,
    post: sender(async () => { if (fail) throw new TypeError('network'); return { status: 200, body: { post: 'ent-new111111a', number: 2 } } }),
  })
  await s.read()
  s.draft('whose post would this be')
  await s.send()
  assert.equal(s.snapshot().uncertain, true)

  /* the server now names a different owner for the same page */
  me = 'ent-otherowner1'
  fail = false
  await s.send()
  assert.equal(sends.length, 1, 'nothing went out under a key that stands for another post')
  assert.equal(s.snapshot().sendError, OTHER_IDENTITY)
  assert.equal(s.snapshot().uncertain, true)
  assert.equal(s.snapshot().draft, 'whose post would this be')
  assert.equal(miniAttempt(mine)!.author, ME)
  s.dispose(); forgetMiniDrafts()
})

/* -- reading what has arrived since ------------------------------------------ */

test('an explicit refresh reads this Conversation again, and the open thread with it', async () => {
  forgetMiniDrafts()
  let since = false
  const later = () => since
  const { paths, get } = seam((path) => path.includes('/thread/')
    ? {
      status: 200,
      body: {
        conversation: OWN, root: 'ent-post11111a', turn: turn(), replies_total: later() ? 2 : 1,
        replies: later()
          ? [turn({ id: 'ent-r1', number: 4 }), turn({ id: 'ent-r2', number: 9, parts: [{ type: 'text', text: 'A reply that arrived since.' }] })]
          : [turn({ id: 'ent-r1', number: 4 })],
      },
    }
    : {
      status: 200,
      body: conversationBody(later()
        ? {
          turns: [turn(), turn({ id: 'ent-post11111c', number: 2, parts: [{ type: 'text', text: 'Recorded since this card opened.' }] })],
          turns_total: 2, owed: [{ expectation: 'opr-1' }],
        }
        : {}),
    })
  const s = store({ resource: resourceFor(), get })
  await s.read()
  await s.openThread('ent-post11111a')
  assert.deepEqual(s.snapshot().posts.map((p) => p.id), ['ent-post11111a'])
  assert.equal(s.snapshot().thread!.replies.length, 1)
  assert.equal(s.snapshot().owed, 0)
  assert.equal(s.snapshot().total, 1)

  /* replies and Work are recorded while the card stays open */
  since = true
  await s.refresh()
  assert.deepEqual(s.snapshot().posts.map((p) => p.id), ['ent-post11111a', 'ent-post11111c'])
  assert.equal(s.snapshot().total, 2)
  assert.equal(s.snapshot().owed, 1)
  assert.deepEqual(s.snapshot().thread!.replies.map((p) => p.id), ['ent-r1', 'ent-r2'])
  /* exactly one page read and one thread read per ask: nothing widened */
  assert.equal(paths.filter((p) => p === `/api/conversations/${OWN}?batch=30`).length, 2)
  assert.equal(paths.filter((p) => p.includes('/thread/')).length, 2)
  assert.equal(s.snapshot().loading, false)

  /* with no thread open, refresh reads the page and nothing else */
  s.closeThread()
  await s.refresh()
  assert.equal(paths.filter((p) => p.includes('/thread/')).length, 2)
  assert.equal(paths.filter((p) => p === `/api/conversations/${OWN}?batch=30`).length, 3)
  s.dispose()
})

test('a refresh on a Magnet with no own Conversation reads nothing at all', async () => {
  const { paths, get } = seam(() => ({ status: 200, body: conversationBody() }))
  const s = store({ resource: resourceFor({ conversation: SOURCE }), get })
  await s.refresh()
  assert.deepEqual(paths, [])
  s.dispose()
})

/* -- the draft lives for the page, and nowhere else -------------------------- */

test('a draft is per Magnet, survives unmount, guards the page and is never stored', () => {
  forgetMiniDrafts()
  const a = resourceFor(), b = resourceFor()
  assert.equal(hasMiniDraft(a), false)
  assert.equal(anyMiniDraft(), false)
  const first = store({ resource: a, get: async () => ({ status: 200, body: conversationBody() }) })
  first.draft('kept across a collapse')
  assert.equal(hasMiniDraft(a), true)
  assert.equal(hasMiniDraft(b), false)
  assert.equal(anyMiniDraft(), true)
  /* the card unmounting (collapse, a tab change, the parent) keeps the words */
  first.dispose()
  assert.equal(miniDraft(a), 'kept across a collapse')
  const again = store({ resource: a, get: async () => ({ status: 200, body: conversationBody() }) })
  assert.equal(again.snapshot().draft, 'kept across a collapse')
  again.dispose()
  /* whitespace alone is not a draft to protect */
  setMiniDraft(a, '   ')
  assert.equal(hasMiniDraft(a), false)
  discardMiniDraft(a)
  assert.equal(miniDraft(a), '')
  assert.equal(anyMiniDraft(), false)
})

test('nothing unsent reaches storage, the address, the record or the main store', () => {
  const code = readFileSync(new URL('../src/quiet2/magnets/conversation.ts', import.meta.url), 'utf8')
  const view = readFileSync(new URL('../src/quiet2/magnets/MiniConversation.tsx', import.meta.url), 'utf8')
  for (const [name, src] of [['conversation.ts', code], ['MiniConversation.tsx', view]] as [string, string][]) {
    assert.doesNotMatch(src, /localStorage|sessionStorage|document\.cookie/, `${name} keeps nothing beyond the page`)
    assert.doesNotMatch(src, /history\.(push|replace)State|location\.(assign|replace|hash)/, `${name} puts nothing in the address`)
    assert.doesNotMatch(src, /from ['"]\.\.\/real['"]|from ['"]\.\.\/\.\.\/fluid\/store['"]/, `${name} does not touch the main store`)
    assert.doesNotMatch(src, /dangerouslySetInnerHTML|innerHTML/, `${name} renders no markup from the record`)
    assert.doesNotMatch(src, /\/activate|magnets\/.*\/create|POST \/fluid\/api\/conversations/, `${name} creates and activates nothing`)
    /* reading again is the owner pressing Refresh, never a timer */
    assert.doesNotMatch(src, /setInterval|setTimeout|requestIdleCallback|EventSource|new WebSocket/, `${name} polls nothing and runs on no timer`)
  }
  /* exactly one write path, and it is the existing posting door */
  assert.deepEqual([...code.matchAll(/method: 'POST'/g)].length, 1)
  assert.match(code, /POSTS_PATH = '\/fluid\/api\/posts'/)
})

/* -- what it draws ----------------------------------------------------------- */

test('an unavailable own Conversation is visibly unavailable and offers no composer', () => {
  forgetMiniDrafts()
  const html = renderToStaticMarkup(createElement(MiniConversation, {
    resource: resourceFor({ conversation: null }), onFull: () => {}, canWrite: true,
  }))
  assert.match(html, /Magnet conversation unavailable/)
  assert.match(html, /no Conversation of its own/)
  assert.doesNotMatch(html, /textarea/)
  assert.doesNotMatch(html, /Send/)
})

test('without the capability the composer is visibly unavailable, with it the card writes', () => {
  forgetMiniDrafts()
  const readOnly = renderToStaticMarkup(createElement(MiniConversation, { resource: resourceFor(), onFull: () => {}, canWrite: false }))
  assert.match(readOnly, /Sending is unavailable for this Magnet here/)
  assert.doesNotMatch(readOnly, /textarea/)
  assert.match(readOnly, /Open full Conversation/)

  const writable = resourceFor()
  setMiniDraft(writable, 'half a thought')
  const html = renderToStaticMarkup(createElement(MiniConversation, { resource: writable, onFull: () => {}, canWrite: true }))
  assert.match(html, /<textarea/)
  assert.match(html, /half a thought/)
  assert.match(html, /Nothing is dispatched and no run is started/)
  forgetMiniDrafts()
})

test('a mounted card offers an explicit Refresh beside the way out, and a read-only one still does', () => {
  forgetMiniDrafts()
  for (const canWrite of [true, false]) {
    const html = renderToStaticMarkup(createElement(MiniConversation, { resource: resourceFor(), onFull: () => {}, canWrite }))
    assert.match(html, /Refresh conversation/, `canWrite=${canWrite}`)
    assert.match(html, /Open full Conversation/, `canWrite=${canWrite}`)
  }
  /* a Magnet with no own Conversation has nothing to refresh */
  const none = renderToStaticMarkup(createElement(MiniConversation, {
    resource: resourceFor({ conversation: null }), onFull: () => {}, canWrite: true,
  }))
  assert.doesNotMatch(none, /Refresh conversation/)
})

test('a post’s words are drawn as text, and nothing in the record becomes markup', () => {
  const nasty = '<script>alert(1)</script> & "quoted"\n\nsecond paragraph'
  const html = renderToStaticMarkup(createElement(Words, { text: nasty }))
  assert.doesNotMatch(html, /<script>/)
  assert.match(html, /&lt;script&gt;/)
  assert.match(html, /second paragraph/)
  assert.equal([...html.matchAll(/class="q2-mini-words"/g)].length, 2)
})

test('a post says who wrote it, what it answers and what work it carries', () => {
  const post = adaptTurn(turn({
    id: 'ent-post11111b', number: 12, written_by: 'claude/run1', author_alias: '@Builder',
    answering: 'ent-post11111a', answering_number: 3, thread_replies: 2,
    expectations: [{ id: 'opr-1', expects: 'return the mini card', of: null, of_alias: null, by_alias: '@brian', response_present: false, live_execution: false, unassigned: true }],
  }) as never)
  const html = renderToStaticMarkup(createElement(PostView, {
    post, canReply: true, threadOpen: false, onReply: () => {}, onThread: () => {},
  }))
  assert.match(html, /#12/)
  assert.match(html, /@Builder/)
  assert.match(html, /agent/)
  assert.match(html, /in reply to #3/)
  assert.match(html, /Show 2 replies/)
  assert.match(html, /nobody carries it/)
  assert.match(html, /open/)

  const deleted = renderToStaticMarkup(createElement(PostView, {
    post: adaptTurn(turn({ deleted: { record: 'ent-d', at: 1, by: ME, because: null }, parts: [{ type: 'text', text: 'secret' }] }) as never),
    canReply: false, threadOpen: false, onReply: () => {}, onThread: () => {},
  }))
  assert.doesNotMatch(deleted, /secret/)
  assert.match(deleted, /was deleted/)
})

test('a withdrawn request is never drawn as answered', () => {
  const html = renderToStaticMarkup(createElement(WorkLine, {
    work: { expectation: 'opr-1', expects: 'decide', state: 'withdrawn', ofAlias: '@brian', unassigned: false, byAlias: '@Caretaker', liveExecution: false },
  }))
  assert.match(html, /withdrawn/)
  assert.doesNotMatch(html, />answered</)
})
