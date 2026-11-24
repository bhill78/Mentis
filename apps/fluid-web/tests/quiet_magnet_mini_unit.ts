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
import MiniConversation, {
  messageTargetOf, offsetInBox, refOfViewable, referenceClicked, replyTargetOf,
} from '../src/quiet2/magnets/MiniConversation'
import type { PostPage } from '../src/quiet2/Post'
import { adapt } from '../src/quiet2/real'
import {
  ComposerBarView, PIN_TO_BOTTOM, afterSent,
  contextCandidate, managedSelector, configurationDigest as composerConfigurationDigest, type ComposerBarViewProps,
} from '../src/quiet2/magnets/ComposerBar'
import { configurationDigest as definitionConfigurationDigest } from '../src/quiet2/magnets/configuration'
import { actionOf, bodyOf, emptyDraft, sendLabel } from '../src/composer/draft'
import { loadDraft, saveDraft, dropDraft } from '../src/fluid/composer/drafts'
import { miniAsking } from '../src/quiet2/magnets/asking'
import { miniComposerDraft, miniComposerWhere, saveMiniComposer } from '../src/quiet2/magnets/conversation'
import { composerRequest, agentsOf, evidencePieces, isEvidence } from '../src/quiet2/magnets/evidence'
import { emptyPlace, emptyPlaces, restore } from '../src/quiet2/magnets/places'
import type { MagnetSnapshot } from '../src/quiet2/magnets/contract'
import {
  CANNOT_WRITE, IN_FLIGHT_SEND, MALFORMED_SEND, MESSAGE_SEARCH_BOUND, NO_CONVERSATION_TO_SEARCH,
  NO_OWNER, NO_OWN_CONVERSATION, OTHER_BRAIN, OTHER_IDENTITY,
  OWN_IS_A_SOURCE, UNCERTAIN_SEND, UNCONFIRMED_BRAIN,
  adaptTurn, anyMiniDraft, attachContext, carryContext, clearContext, confirmedBrain, corpusOfBoundBrain, corpusOfSpaceKey,
  createMiniConversation, discardMiniDraft, discussEvidence, forgetMiniDrafts, hasMiniDraft, messageSource,
  miniAttempt, miniDraft, miniReplyTarget, ownConversation, removeContext,
  restoredReplyTarget, setMiniDraft, sourceConversations, textOfTurn, withContext,
  livePost, AGENTS_PATH, collectionPath,
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
  saved: { id: `mag-fixture${ids}`,  name: 'Fixture collection', config: config(over) as never },
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
  assert.equal(sends[0].path, '/fluid/api/requests')
  assert.equal(sends[0].headers['X-Mentis-Brain'], BOUND)
  assert.equal(sends[0].body.conversation, undefined)
  assert.deepEqual(sends[0].body.from, { magnet: mine.saved.id })
  assert.equal(sends[0].body.author, ME)
  assert.equal(sends[0].body.action, 'record-only')
  assert.deepEqual(sends[0].body.dispatch, [])
  assert.equal(sends[0].body.addressed_to, undefined)
  assert.equal(sends[0].body.text, '  A real message.  ')
  assert.deepEqual(sends[0].body.parts, [{ type: 'text', text: '  A real message.  ' }])
  assert.equal(sends[0].body.text, '  A real message.  ')
  assert.equal('replies_to' in sends[0].body, false)
  assert.equal(typeof sends[0].body.op, 'string')
  /* and it names the key it resolved, which is how a bar that was not mounted
     when the answer landed knows which send it still owes an act (B1) */
  assert.deepEqual(s.snapshot().sent, { post: 'ent-new111111a', op: sends[0].body.op as string, number: 2, replayed: false })
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
  assert.deepEqual(again.snapshot().sent, { post: 'ent-new111111a', op: sends[0].body.op as string, number: 2, replayed: true })
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

test('mini interactions never navigate, poll, inject markup or touch the main store', () => {
  const code = readFileSync(new URL('../src/quiet2/magnets/conversation.ts', import.meta.url), 'utf8')
  const view = readFileSync(new URL('../src/quiet2/magnets/MiniConversation.tsx', import.meta.url), 'utf8')
  for (const [name, src] of [['conversation.ts', code], ['MiniConversation.tsx', view]] as [string, string][]) {
    assert.doesNotMatch(src, /history\.(push|replace)State|location\.(assign|replace|hash)/, `${name} puts nothing in the address`)
    assert.doesNotMatch(src, /from ['"]\.\.\/\.\.\/fluid\/store['"]/, `${name} does not touch the main store`)
    assert.doesNotMatch(src, /dangerouslySetInnerHTML|innerHTML/, `${name} renders no markup from the record`)
    assert.doesNotMatch(src, /setInterval|requestIdleCallback|EventSource|new WebSocket/, `${name} starts no poll or stream`)
  }
  /* The card follows the record through Quiet's own reader, which is what
     applies the shared pulse and its Conversation-scoped move filter
     (`real.ts`: `hearPulse`, `flowMoved`, `FLOW_SPACING`). The view adds no
     beat of its own, which is why neither appears here any more. */
  assert.match(view, /useRealFlow/, 'the mini view reads through Quiet\'s own flow reader')
  const shared = readFileSync(new URL('../src/quiet2/real.ts', import.meta.url), 'utf8')
  assert.match(shared, /hearPulse/, 'which reuses Quiet\'s shared pulse')
  assert.match(shared, /export function flowMoved/, 'and its Conversation-scoped move filter')
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
  assert.match(html, /Start a Conversation here/)
  assert.match(html, /Create own Conversation/)
  assert.doesNotMatch(html, /textarea/)
  assert.doesNotMatch(html, /Send/)
})

test('without the capability the composer is visibly unavailable, with it the card writes', () => {
  forgetMiniDrafts()
  const readOnly = renderToStaticMarkup(createElement(MiniConversation, { resource: resourceFor(), onFull: () => {}, canWrite: false }))
  assert.match(readOnly, /Sending is unavailable for this Magnet here/)
  assert.doesNotMatch(readOnly, /textarea/)
  assert.match(readOnly, /Open full Conversation/)

  // The real Composer is client-only (its facts store has no server snapshot).
  // Its writable rendering, split menu and permissions run in the Edge fixture.

  forgetMiniDrafts()
})

test('the mini Conversation follows the record without a manual Refresh affordance', () => {
  forgetMiniDrafts()
  for (const canWrite of [false]) {
    const html = renderToStaticMarkup(createElement(MiniConversation, { resource: resourceFor(), onFull: () => {}, canWrite }))
    assert.doesNotMatch(html, /Refresh conversation/, `canWrite=${canWrite}`)
    assert.match(html, /Open full Conversation/, `canWrite=${canWrite}`)
  }
  /* a Magnet with no own Conversation has nothing to refresh */
  const none = renderToStaticMarkup(createElement(MiniConversation, {
    resource: resourceFor({ conversation: null }), onFull: () => {}, canWrite: true,
  }))
  assert.doesNotMatch(none, /Refresh conversation/)
})

/* -- ONE CONVERSATION EXPERIENCE (owner §5) ---------------------------------
   The card no longer draws posts itself. These check that what it draws is
   Mentis's own post, that the adaptation behind it is the shared one, and
   that the page those shared components are given is bounded to the card. */

const boundedPage = (over: Partial<PostPage> = {}): PostPage => ({
  me: null, who: null, topic: null, compact: true,
  onWho: () => {}, onTopic: () => {}, onReply: () => {}, onEnter: () => {},
  onBeside: null, onView: () => {}, openElsewhere: () => null, say: () => {}, working: [],
  ...over,
})

test('the card keeps no renderer of its own: a post is Mentis’s own post', () => {
  const view = readFileSync(new URL('../src/quiet2/magnets/MiniConversation.tsx', import.meta.url), 'utf8')
  assert.match(view, /from '\.\.\/Post'/, 'the shared post')
  assert.match(view, /from '\.\.\/Thread'/, 'the shared replies')
  assert.match(view, /from '\.\.\/real'/, 'the one shared store of posts')
  /* what used to be here, gone rather than reproduced */
  for (const gone of [/function Words\b/, /function PostView\b/, /function WorkLine\b/, /q2-mini-words/, /q2-mini-attribution/]) {
    assert.doesNotMatch(view, gone, `${gone} is not drawn here any more`)
  }
  /* and nothing in it leads out of the card */
  assert.match(view, /onBeside: null/, 'no working surface is offered inside the card')
  assert.match(view, /compact: true/, 'the bounded host: no annotation margin, no open-beside')
})

test('the shared adaptation is what a post in the card is: words, files and what it answers', () => {
  const post = adapt(turn({
    id: 'ent-post11111b', number: 12, written_by: 'claude/run1', author_alias: '@Builder',
    answering: 'ent-post11111a', answering_number: 3, thread_replies: 2,
    parts: [{ type: 'text', text: '## A heading\n\nWords **with** Markdown.' },
      { type: 'acquired', text: '', ref: 'adm-111111111111', name: 'notes.txt', media_type: 'text/plain', size: 4 }],
    expectations: [{ id: 'opr-1', expects: 'return the mini card', of: null, of_alias: null, by_alias: '@brian', response_present: false, live_execution: false, unassigned: true }],
  }) as never, 'ent-own1111111', () => undefined)
  assert.equal(post.number, 12)
  assert.equal(post.by.name, '@Builder')
  assert.equal(post.by.agent, true, 'written by a run')
  assert.equal(post.replyNumber, 3)
  assert.equal(post.threadCount, 2)
  assert.equal(post.title, 'A heading', 'the heading is the title, as everywhere else')
  assert.ok(post.blocks.some((b) => b.kind === 'text' && b.md.includes('**with**')), 'the words stay Markdown for Prose to draw')
  assert.ok(post.status, 'and the record\'s own facts come with it, for the shared status line')
  assert.equal(post.real, true)
})

test('replying aims the card’s own composer at the post the record names', () => {
  const post = adapt(turn({ id: 'ent-post11111b', number: 12, author_alias: '@Builder', thread_replies: 2 }) as never,
    'ent-own1111111', () => undefined)
  const target = replyTargetOf(post)
  assert.equal(target.id, 'ent-post11111b')
  assert.equal(target.number, 12, 'the number the composer says it is replying to')
  assert.equal(target.authorAlias, '@Builder', 'and who wrote it')
})

test('a deleted post has no words to draw, and none are substituted', () => {
  /* WHAT THE SERVER ACTUALLY SENDS. "a deleted Turn's parts are empty, and
     what it said is disclosed only by its Details" (`mentis/web/__init__.py`
     `_turn_view`), so the read a deleted post arrives in carries no words.
     The shared adaptation draws what the read holds and invents nothing. */
  const post = adapt(turn({
    id: 'ent-deleted1111', number: 4, deleted: { record: 'ent-d', at: 1, by: ME, because: null }, parts: [],
  }) as never, 'ent-own1111111', () => undefined)
  assert.deepEqual(post.blocks, [], 'nothing to draw')
  assert.equal(post.text, '', 'and nothing to copy or edit')
})

test('a reference in a post’s words opens inside the card and nowhere else', () => {
  const view = readFileSync(new URL('../src/quiet2/magnets/MiniConversation.tsx', import.meta.url), 'utf8')
  /* Prose turns each `ent-`/`adm-` an agent wrote into the one inspectable
     reference component; the card gives that component its own opener, so a
     citation is read as evidence in the card exactly as one opened from any
     other tab is (`withInspections`). */
  assert.match(view, /RefIndex/)
  assert.match(view, /openEntry=\{onEvidence\}/)
  /* and a click on the reference Prose marked in the words is read here, so
     every kind of reference is opened as evidence in the card */
  const marked = (said: string, inBody = true) => ({
    closest: (sel: string) => sel === '[data-src-text]'
      ? { getAttribute: () => said, closest: (s: string) => (s === '.q2-body' && inBody ? {} : null) } as unknown as Element
      : null,
  }) as unknown as Element
  assert.equal(referenceClicked(marked('ent-32b3d6e010db')), 'ent-32b3d6e010db')
  assert.equal(referenceClicked(marked('adm-2a92de66e51b')), 'adm-2a92de66e51b', 'a retained artifact too')
  assert.equal(referenceClicked(marked('opr-d812cf2caa48')), 'opr-d812cf2caa48')
  assert.equal(referenceClicked(marked('adm-2a92de66e51b#L2-L9')), null, 'a citation of extracted text is not a plain reference')
  assert.equal(referenceClicked(marked('ent-not-hex-at-all')), null)
  assert.equal(referenceClicked(marked('ent-32b3d6e010db', false)), null, 'and only inside a post’s own words')
  assert.equal(referenceClicked(null), null)
  assert.ok(evidencePieces('ent-32b3d6e010db adm-2a92de66e51b').filter(isEvidence).length === 2)
  const viewable = refOfViewable({ kind: 'file', item: { url: '/api/artifacts/adm-111111111111', name: 'notes.txt', alt: 'notes.txt', kind: 'file', ref: 'adm-111111111111', mediaType: 'text/plain', size: 4 } })
  assert.equal(viewable, 'adm-111111111111', 'a held file opens as evidence in the card')
  assert.equal(boundedPage().onBeside, null)
})

test('the exact message a search result meant, and only from a Conversation target', () => {
  assert.equal(messageTargetOf({ searchTarget: null }), null)
  assert.equal(messageTargetOf({ searchTarget: { kind: 'Posts', message: 'ent-32b3d6e010db' } }), null,
    'a retained post result is not a message in this Conversation')
  assert.equal(messageTargetOf({ searchTarget: { kind: 'Conversation' } }), null, 'no message named, nothing guessed')
  assert.equal(messageTargetOf({ searchTarget: { kind: 'Conversation', message: 'ent-32b3d6e010db' } }), 'ent-32b3d6e010db')
  /* where that post is put: in the card's one scroll container, through the
     same place the reading position is restored from */
  assert.equal(offsetInBox({ top: 540 }, { top: 100, scrollTop: 0 }), 428)
  assert.equal(offsetInBox({ top: 540 }, { top: 100, scrollTop: 260 }), 688)
  assert.equal(offsetInBox({ top: 100 }, { top: 540, scrollTop: 0 }), 0, 'never above the top of the view')
})

/* Quill adm-db550afa8dd6: exact F1-F4 probes and Brain control. */
{
const OWN = 'ent-reviewown111', ME = 'ent-reviewowner1', ROOT = 'ent-reviewroot11'
const deferred = () => { let resolve!: (v: any) => void; const promise = new Promise<any>(r => { resolve = r }); return { promise, resolve } }
const tick = async () => { for (let i = 0; i < 12; i++) await Promise.resolve() }
const page = (over: any = {}) => ({ status: 200, body: { id: OWN, name: 'Synthetic', turns: [], turns_total: 0, owed: [], batch: { older: 0, first: null }, ...over } })
const post = (id = ROOT) => ({ id, number: 1, author: ME, author_alias: '@synthetic', at: 1, parts: [{type:'text',text:id}], expectations: [], replies: [] })
let ids = 0, keys = 0
const resource = () => ({ id: `review-${++ids}`, brainKey: 'https://synthetic.invalid||review-corpus', saved: {id:`mag-review${ids}`, config:{ conversation:OWN, sources:[{kind:'conversation',conversation:'ent-reviewsource'}]}} })
const options = (r: any, over: any = {}) => {
  const binding = createBinding(); binding.saw('review-corpus@review-instance')
  return { resource:r, canWrite:true, binding, now:async () => binding.bound(), op:()=>`review-key-${++keys}`,
    get:async (path:string) => path.includes('participants') ? {status:200,body:{me:ME}} : page(),
    post:async () => ({status:200,body:{post:'ent-reviewposted1'}}), ...over }
}

test('B1: success from disposed mount must retire visible remount draft before another Send', async () => {
  forgetMiniDrafts(); const r = resource(), answer = deferred(), bodies:any[]=[]
  const opts = options(r,{post:async (_:any,b:any)=>{bodies.push(b);return bodies.length===1?answer.promise:{status:200,body:{post:'ent-reviewposted2'}}}})
  const a = createMiniConversation(opts as any); a.draft('same words'); const pending=a.send(); await tick(); a.dispose()
  const b = createMiniConversation(opts as any)
  answer.resolve({status:200,body:{post:'ent-reviewposted1'}}); await pending
  assert.equal(miniDraft(r as any),'')
  await b.send(); b.dispose()
  console.log('B1 request keys:', bodies.map(b=>b.op))
  assert.equal(bodies.length,1,'retired send must not be emitted again under a new key from stale snapshot')
})

test('B2: success must preserve same words now aimed at a different reply target', async () => {
  forgetMiniDrafts(); const r=resource(), answer=deferred()
  const a=createMiniConversation(options(r,{post:()=>answer.promise}) as any)
  a.draft('same words'); const pending=a.send(); await tick()
  a.replyTo({id:'ent-reviewtarget2',number:2,authorAlias:'@other'} as any)
  answer.resolve({status:200,body:{post:'ent-reviewposted1'}}); await pending; a.dispose()
  assert.equal(miniDraft(r as any),'same words','reply target changed: this composer is a different unsent post')
  assert.equal(miniReplyTarget(r as any)?.id,'ent-reviewtarget2')
})


test('N2: refresh overlapping earlier read must release earlier-page loading', async () => {
  forgetMiniDrafts();const older=deferred()
  const a=createMiniConversation(options(resource(),{get:async(p:string)=>p.includes('before=')?older.promise:page({turns:[post()],batch:{older:30,first:31}})}) as any)
  await a.read();const pending=a.earlier();await a.refresh();older.resolve(page());await pending
  const snapshot=a.snapshot();a.dispose()
  assert.equal(snapshot.loadingEarlier,false,'refresh invalidated the earlier result, but must unlock the control')
})

test('N3: a closed and reopened thread must ignore its earlier request finishing last', async () => {
  forgetMiniDrafts(); const old=deferred(),fresh=deferred();let reads=0
  const a=createMiniConversation(options(resource(),{get:()=>++reads===1?old.promise:fresh.promise}) as any)
  const first=a.openThread(ROOT);a.closeThread();const second=a.openThread(ROOT)
  fresh.resolve({status:200,body:{replies:[post('ent-reviewnew111')]}});await second
  old.resolve({status:200,body:{replies:[post('ent-reviewold111')]}});await first
  const ids=a.snapshot().thread!.replies.map(p=>p.id);a.dispose()
  assert.deepEqual(ids,['ent-reviewnew111'],'closed request must not overwrite a later read of the same root')
})


test('control: changed Brain instance after uncertain send refuses same-key resend', async () => {
  forgetMiniDrafts();const r=resource();let brain='review-corpus@review-instance',calls=0
  const opts=options(r,{now:async()=>brain,post:async()=>{calls++;throw Error('lost')}})
  const a=createMiniConversation(opts as any);a.draft('kept');await a.send();a.dispose()
  brain='review-corpus@different-instance';const b=createMiniConversation(opts as any);await b.send()
  assert.equal(calls,1);assert.match(b.snapshot().sendError!,/another owner or on another Brain/)
  assert.ok(miniAttempt(r as any));assert.equal(miniDraft(r as any),'kept');b.dispose()
})


for (const edit of ['retarget', 'retarget-back', 'edit-back']) {
  test(`F2: a newer ${edit} intent survives late success after remount`, async () => {
    forgetMiniDrafts()
    const r = resource(), answer = deferred()
    const opts = options(r, { post: () => answer.promise })
    const a = createMiniConversation(opts as any)
    a.draft('same words')
    const pending = a.send(); await tick(); a.dispose()
    const b = createMiniConversation(opts as any)
    if (edit === 'edit-back') { b.draft('new words'); b.draft('same words') }
    else {
      b.replyTo({ id: 'ent-reviewtarget2', number: 2, authorAlias: '@other' } as any)
      if (edit === 'retarget-back') b.replyTo(null)
    }
    answer.resolve({ status: 200, body: { post: 'ent-reviewposted1' } }); await pending
    assert.equal(miniDraft(r as any), 'same words')
    assert.equal(b.snapshot().draft, 'same words')
    assert.equal(b.snapshot().replyTo?.id ?? null, edit === 'retarget' ? 'ent-reviewtarget2' : null)
    assert.equal(miniAttempt(r as any), null)
    assert.equal(b.snapshot().uncertain, false)
    b.dispose()
  })
}

test('F1: late success during remounted retry preflight cannot mint a new key', async () => {
  forgetMiniDrafts()
  const r = resource(), answer = deferred(), identity = deferred(), bodies: any[] = []
  const a = createMiniConversation(options(r, { post: async (_: any, body: any) => {
    bodies.push(body); return answer.promise
  } }) as any)
  a.draft('same words'); const first = a.send(); await tick(); a.dispose()
  const b = createMiniConversation(options(r, { now: () => identity.promise, post: async (_: any, body: any) => {
    bodies.push(body); return { status: 200, body: { post: 'ent-reviewposted2' } }
  } }) as any)
  const retry = b.send()
  answer.resolve({ status: 200, body: { post: 'ent-reviewposted1' } }); await first
  identity.resolve('review-corpus@review-instance'); await retry
  assert.equal(bodies.length, 1)
  assert.equal(b.snapshot().draft, '')
  assert.equal(b.snapshot().sending, false)
  b.dispose()
})

for (const olderFirst of [true, false]) {
  test(`F3: refresh supersedes earlier read (${olderFirst ? 'earlier' : 'refresh'} finishes first) and history stays usable`, async () => {
    const old = deferred(), latest = deferred(); let pages = 0, earlier = 0
    const a = createMiniConversation(options(resource(), { get: (path: string) => {
      if (path.includes('before=')) return ++earlier === 1 ? old.promise : Promise.resolve(page({ turns: [post('ent-reviewearlier')], batch: { older: 0, first: 1 } }))
      return ++pages === 1 ? Promise.resolve(page({ turns: [post()], batch: { older: 30, first: 31 } })) : latest.promise
    } }) as any)
    await a.read(); const pending = a.earlier(); const refreshing = a.refresh()
    const fresh = page({ turns: [post('ent-reviewlatest1')], batch: { older: 30, first: 31 } })
    if (olderFirst) { old.resolve(page({ turns: [post('ent-reviewstale11')] })); await pending; latest.resolve(fresh); await refreshing }
    else { latest.resolve(fresh); await refreshing; old.resolve(page({ turns: [post('ent-reviewstale11')] })); await pending }
    assert.equal(a.snapshot().loadingEarlier, false)
    assert.deepEqual(a.snapshot().posts.map(p => p.id), ['ent-reviewlatest1'])
    await a.earlier()
    assert.equal(earlier, 2)
    assert.deepEqual(a.snapshot().posts.map(p => p.id), ['ent-reviewearlier', 'ent-reviewlatest1'])
    a.dispose()
  })
}

for (const staleError of [true, false]) {
  for (const reopen of [true, false]) {
    test(`F4: ${reopen ? 'same-root reopen' : 'refresh'} ignores stale ${staleError ? 'error' : 'success'}`, async () => {
      const old = deferred(), fresh = deferred(); let threads = 0
      const a = createMiniConversation(options(resource(), { get: (path: string) => path.includes('/thread/')
        ? (++threads === 1 ? old.promise : fresh.promise) : Promise.resolve(page()) }) as any)
      const first = a.openThread(ROOT)
      if (reopen) a.closeThread()
      const second = reopen ? a.openThread(ROOT) : a.refresh()
      await tick()
      fresh.resolve({ status: 200, body: { replies: [post('ent-reviewnew111')] } }); await second
      old.resolve(staleError ? { status: 503, body: {} } : { status: 200, body: { replies: [post('ent-reviewold111')] } }); await first
      assert.deepEqual(a.snapshot().thread!.replies.map(p => p.id), ['ent-reviewnew111'])
      assert.equal(a.snapshot().thread!.loading, false)
      assert.equal(a.snapshot().thread!.error, undefined)
      a.dispose()
    })
  }
}

test('F1/F2: a mutable parent holder cannot redirect late completion to another resource', async () => {
  forgetMiniDrafts()
  const r = resource(), other = resource(), answer = deferred()
  const opts = options(r, { post: () => answer.promise })
  const a = createMiniConversation(opts as any)
  a.draft('first resource'); const sending = a.send(); await tick(); a.dispose()
  opts.resource = other
  const b = createMiniConversation(opts as any); b.draft('other resource')
  answer.resolve({ status: 200, body: { post: 'ent-reviewposted1' } }); await sending
  assert.equal(miniDraft(r as any), '')
  assert.equal(miniDraft(other as any), 'other resource')
  assert.equal(b.snapshot().draft, 'other resource')
  b.dispose()
})


test('F4: a second refresh owns its thread response even when the first finishes last', async () => {
  const old = deferred(), fresh = deferred(); let threads = 0
  const a = createMiniConversation(options(resource(), { get: (path: string) => {
    if (!path.includes('/thread/')) return Promise.resolve(page())
    threads++
    return threads === 1 ? Promise.resolve({ status: 200, body: { replies: [post()] } })
      : threads === 2 ? old.promise : fresh.promise
  } }) as any)
  await a.openThread(ROOT)
  const first = a.refresh(); await tick()
  const second = a.refresh(); await tick()
  fresh.resolve({ status: 200, body: { replies: [post('ent-reviewnew111')] } }); await second
  old.resolve({ status: 200, body: { replies: [post('ent-reviewold111')] } }); await first
  assert.equal(threads, 3)
  assert.deepEqual(a.snapshot().thread!.replies.map(p => p.id), ['ent-reviewnew111'])
  a.dispose()
})

}


/* Functional B seam checks. These assert real serialized HTTP bodies, never
 * substitute a scripted answer for a real agent or claim product E2E. */
const AGENT = 'ent-realagent111'
const retained = (r: MagnetResource, ref = 'adm-retained111') => ({
  magnet: r.saved.id, config: r.saved.config,
  activation: { post: 'ent-collection111', at: 1795000000, state: 'retained',
    artifact: { ref, digest: 'sha256:captured', size: 42, media_type: 'application/json' } },
  page: { sources: [{ key: 'conversation:source', status: 'ok', results: [
    { kind: 'post', id: 'ent-evidence111', version: 'ent-version111',
      value: { parts: [{ type: 'text', text: 'Captured material.' }] } },
  ] }] },
})
const agentPeople = () => ({ me: ME, participants: [
  { id: ME, alias: '@owner', default_runtime: 'codex' },
  { id: 'ent-human11111', alias: '@human', runtime_mode: 'undeclared' },
  { id: AGENT, alias: '@ActualBuilder', default_runtime: 'codex', runtime_mode: 'default' },
] })
function groundedGet(r: MagnetResource, batch: () => unknown = () => retained(r)): MiniGet {
  return async (path) => ({ status: 200, body: path === collectionPath(r) ? batch()
    : path === AGENTS_PATH ? agentPeople()
    : path.startsWith('/fluid/api/participants') ? { me: ME }
    : conversationBody() })
}

test('ordinary ask preserves exact authored parts without attaching the retained collection', async () => {
  forgetMiniDrafts()
  const r = resourceFor(), calls: { path: string; init: RequestInit }[] = []
  const fetchBefore = globalThis.fetch
  globalThis.fetch = (async (path: string, init: RequestInit) => {
    calls.push({ path, init })
    return new Response(JSON.stringify({ post: 'ent-asked111111', number: 2 }), { status: 200 })
  }) as typeof fetch
  try {
    const s = store({ resource: r, get: groundedGet(r), post: livePost })
    s.draft('  What does the retained evidence say?  ')
    await s.ask()
    assert.equal(calls.length, 1)
    assert.equal(calls[0].path, '/fluid/api/requests')
    assert.equal((calls[0].init.headers as any)['X-Mentis-Brain'], BOUND)
    assert.equal((calls[0].init.headers as any)['X-Mentis-Client'], '1')
    const body = JSON.parse(calls[0].init.body as string)
    assert.deepEqual(body.from, { magnet: r.saved.id })
    assert.equal(body.conversation, undefined)
    assert.equal(body.author, ME)
    assert.equal(body.action, 'ask-participant')
    assert.deepEqual(body.addressed_to, [AGENT])
    assert.deepEqual(body.parts, [
      { type: 'text', text: '  What does the retained evidence say?  ' },
    ])
    assert.equal(body.dispatch[0].participant, AGENT)
    assert.equal(body.dispatch[0].runtime, 'codex')
    assert.equal(body.dispatch[0].work, undefined)
    assert.equal(body.parts.some((p: any) => p.type === 'file'), false)
    assert.equal(s.snapshot().draft, '')
    assert.match(s.snapshot().dispatchStatus!, /Request recorded/)
    assert.doesNotMatch(s.snapshot().dispatchStatus!, /completed|finished/)
    s.dispose()
  } finally { globalThis.fetch = fetchBefore; forgetMiniDrafts() }
})

test('asking refuses wrong, unreadable or malformed retained context without dispatch', async () => {
  for (const kind of ['wrong-magnet', 'bad-file', 'bad-page', 'refused']) {
    forgetMiniDrafts(); const r = resourceFor(); let posts = 0
    const batch = () => {
      const b: any = retained(r)
      if (kind === 'absent') { b.activation = null; b.page = null }
      if (kind === 'wrong-magnet') b.magnet = 'mag-another'
      if (kind === 'bad-file') b.activation.artifact.ref = 'ent-noartifact'
      if (kind === 'bad-page') b.page = null
      if (kind === 'refused') return { error: 'retained artifact is unavailable' }
      return b
    }
    const s = store({ resource: r, get: groundedGet(r, batch), post: async () => { posts++; return { status: 200, body: {} } } })
    s.draft('Answer this.'); await s.ask()
    assert.equal(posts, 0, kind)
    assert.ok(s.snapshot().sendError)
    assert.equal(s.snapshot().draft, 'Answer this.')
    s.dispose()
  }
})

test('empty retained collection permits ordinary assistance with work reach and no implicit file', async () => {
  forgetMiniDrafts(); const r = resourceFor(); const calls: any[] = []
  const s = store({ resource: r, get: groundedGet(r, () => ({ ...retained(r), activation: null, page: null })),
    post: async (_path, body) => { calls.push(body); return { status: 200, body: { post: 'ent-help111111' } } } })
  s.draft('How do I configure this Magnet?'); await s.ask()
  assert.equal(calls.length, 1)
  assert.equal(calls[0].dispatch[0].reach, 'work')
  assert.equal(calls[0].dispatch[0].work, undefined)
  assert.equal(calls[0].parts.some((p: any) => p.type === 'file'), false)
  s.dispose()
})

test('agent selection offers undeclared participants, prefers unique declared Codex, and does not choose by order', async () => {
  assert.deepEqual(agentsOf(agentPeople()), [
    { id: 'ent-human11111', alias: '@human', runtime: null },
    { id: AGENT, alias: '@ActualBuilder', runtime: 'codex' },
  ])
  const r = resourceFor(), base = groundedGet(r)
  const get: MiniGet = async (path) => path === AGENTS_PATH ? { status: 200, body: { me: ME, participants: [
    { id: 'ent-agent22222', alias: '@One', runtime_mode: 'auto' },
    { id: 'ent-agent33333', alias: '@Two', runtime_mode: 'auto' },
  ] } } : base(path)
  let posts = 0
  const s = store({ resource: r, get, post: async () => { posts++; return { status: 200, body: { post: 'ent-asked111111' } } } })
  await s.prepare(); assert.equal(s.snapshot().agent, '')
  s.draft('Which?'); await s.ask(); assert.equal(posts, 0)
  s.chooseAgent('ent-agent33333'); await s.ask(); assert.equal(posts, 1)
  s.dispose(); forgetMiniDrafts()
})

test('all-undeclared Fluid catalogue requires explicit choice and serializes automatic runtime with exact retained Admission', async () => {
  forgetMiniDrafts()
  const r = resourceFor(), base = groundedGet(r), calls: any[] = []
  // Actual Fluid row shape; the owner is deliberately not first in the list.
  const people = { me: ME, participants: [
    { id: 'ent-other11111', alias: '@Other', default_runtime: null, runtime_mode: 'undeclared' },
    { id: ME, alias: '@owner', default_runtime: null, runtime_mode: 'undeclared' },
    { id: AGENT, alias: '@Selected', default_runtime: null, runtime_mode: 'undeclared' },
  ] }
  const before = JSON.stringify(people)
  const get: MiniGet = async (path) => path === AGENTS_PATH ? { status: 200, body: people } : base(path)
  const s = store({ resource: r, get, post: async (path, body, headers) => {
    calls.push({ path, body: JSON.parse(JSON.stringify(body)), headers })
    return { status: 200, body: { post: 'ent-asked111111' } }
  } })
  await s.prepare()
  assert.deepEqual(s.snapshot().agents, [
    { id: 'ent-other11111', alias: '@Other', runtime: null },
    { id: AGENT, alias: '@Selected', runtime: null },
  ])
  assert.equal(s.snapshot().agent, '')
  s.draft('What does this retained batch say?'); await s.ask()
  assert.equal(calls.length, 0)
  assert.match(s.snapshot().sendError!, /Choose an agent participant/)
  s.chooseAgent(ME); assert.equal(s.snapshot().agent, '')
  s.chooseAgent(AGENT); await s.ask()
  assert.equal(calls.length, 1)
  assert.equal(calls[0].path, '/fluid/api/requests')
  assert.equal(calls[0].headers['X-Mentis-Brain'], BOUND)
  const body = calls[0].body
  assert.equal(body.author, ME)
  assert.deepEqual(body.addressed_to, [AGENT])
  assert.equal(body.dispatch[0].participant, AGENT)
  assert.equal(body.dispatch[0].runtime, null)
  assert.equal(body.parts.length, 1)
  assert.equal(body.dispatch[0].work, undefined)
  assert.equal(JSON.stringify(people), before)
  s.dispose(); forgetMiniDrafts()
})

test('a sole undeclared recipient still requires explicit selection and invalid owner identity fails closed', async () => {
  const r = resourceFor(), base = groundedGet(r)
  const people = { me: ME, participants: [
    { id: AGENT, alias: '@Selected', default_runtime: null, runtime_mode: 'undeclared' },
  ] }
  const s = store({ resource: r, get: async (path) => path === AGENTS_PATH
    ? { status: 200, body: people } : base(path) })
  await s.prepare()
  assert.equal(s.snapshot().agents.length, 1)
  assert.equal(s.snapshot().agent, '')
  s.chooseAgent(AGENT); await s.prepare()
  assert.equal(s.snapshot().agent, AGENT)
  for (const me of [undefined, null, '', 'not-an-entry']) {
    assert.throws(() => agentsOf({ ...people, me }), /identify the owner/)
  }
  s.dispose(); forgetMiniDrafts()
})

test('uncertain agent ask keeps the entire original request when a newer batch and agent arrive', async () => {
  forgetMiniDrafts(); const r = resourceFor(), bodies: unknown[] = []; let ref = 'adm-retained111'
  const opts = { resource: r, get: groundedGet(r, () => retained(r, ref)), post: async (_: string, body: unknown) => {
    bodies.push(body); if (bodies.length === 1) throw Error('lost answer')
    return { status: 200, body: { post: 'ent-asked111111', replayed: true } }
  } }
  const a = store(opts); a.draft('Question with evidence'); await a.ask(); a.dispose()
  ref = 'adm-newbatch111'; const b = store(opts); await b.prepare(); await b.ask()
  assert.deepEqual(bodies[1], bodies[0])
  assert.equal((bodies[1] as any).parts.length, 1)
  assert.equal(b.snapshot().uncertain, false)
  b.dispose(); forgetMiniDrafts()
})

test('Create Conversation is explicit, Brain bound and stable across an uncertain result', async () => {
  forgetMiniDrafts(); const r = resourceFor({ conversation: undefined }), calls: any[] = []
  let updates = 0; r.update = () => { updates++ }
  const s = store({ resource: r, get: groundedGet(r), post: async (path, body, headers) => {
    calls.push({ path, body, headers }); if (calls.length === 1) throw Error('unknown')
    return { status: 201, body: { conversation: OWN } }
  } })
  assert.equal(calls.length, 0)
  await s.createOwn(); assert.equal(r.saved.config?.conversation, undefined)
  await s.createOwn()
  assert.equal(calls[0].path, `/fluid/api/magnets/${r.saved.id}/conversation`)
  assert.deepEqual(calls[0], calls[1])
  assert.equal(calls[0].headers['X-Mentis-Brain'], BOUND)
  assert.equal(calls[0].body.op, `magnet-conversation:${r.saved.id}`)
  assert.equal(r.saved.config?.conversation, OWN)
  assert.equal(updates, 1)
  s.dispose()
})

test('collection refresh discovers an own Conversation created by activation', async () => {
  const r = resourceFor({ conversation: undefined }); let updates = 0; r.update = () => { updates++ }
  const b = retained(r); b.config = config() as never
  const s = store({ resource: r, get: groundedGet(r, () => b) })
  await s.prepare()
  assert.equal(r.saved.config?.conversation, OWN)
  assert.equal(updates, 1)
  s.dispose()
})

test('Create and grounded ask honour capability and full Brain identity before any write', async () => {
  for (const canWrite of [false, true]) {
    const r = resourceFor({ conversation: undefined }); let writes = 0
    const s = store({ resource: r, canWrite, now: async () => null, get: groundedGet(r), post: async () => { writes++; return { status: 200, body: {} } } })
    await s.createOwn(); assert.equal(writes, 0); s.dispose()
    const q = store({ resource: resourceFor(), canWrite, now: async () => null, post: async () => { writes++; return { status: 200, body: {} } } })
    q.draft('do not write'); await q.ask(); assert.equal(writes, 0); q.dispose()
  }
  forgetMiniDrafts()
})

test('post, version and artifact citations are recognised as the exact references they are', () => {
  const refs = ['ent-capturedpost', 'ent-capturedversion', 'adm-retained111']
  /* `evidence.ts` still decides what is a reference; what draws it is now the
     shared Prose and its one inspectable reference component, given the
     card's own opener (above). Nothing renders a record's words as markup. */
  assert.ok(evidencePieces(refs.join(' ')).filter(isEvidence).length === 3)
  assert.deepEqual(evidencePieces(`Evidence ${refs[0]}.`).filter(isEvidence), [refs[0]])
})

test('draft and frozen uncertain ask survive memory reset only for the exact Brain instance and Magnet', async () => {
  const data = new Map<string, string>()
  const old = Object.getOwnPropertyDescriptor(globalThis, 'localStorage')
  Object.defineProperty(globalThis, 'localStorage', { configurable: true, value: {
    getItem: (key: string) => data.get(key) ?? null,
    setItem: (key: string, value: string) => data.set(key, value),
    removeItem: (key: string) => data.delete(key),
  } })
  try {
    forgetMiniDrafts(); const r = resourceFor(), bodies: any[] = []
    const options = { resource: r, get: groundedGet(r), post: async (_: string, body: any) => { bodies.push(body); throw Error('lost') } }
    const a = store(options); a.draft('Persisted question'); await a.ask(); a.dispose()
    assert.equal(data.size, 1)
    assert.match([...data.keys()][0], /corpus-fixture-a@instance-1/)
    forgetMiniDrafts()
    const b = store(options); assert.equal(b.snapshot().draft, 'Persisted question')
    assert.equal(b.snapshot().uncertain, true)
    await b.ask(); assert.deepEqual(bodies[1], bodies[0]); b.dispose()
    forgetMiniDrafts()
    const another = store({ ...options, binding: bound(`${CORPUS}@instance-2`) })
    assert.equal(another.snapshot().draft, '')
    assert.equal(another.snapshot().uncertain, false); another.dispose()
    const otherMagnet = store({ resource: resourceFor(), binding: bound(BOUND) })
    assert.equal(otherMagnet.snapshot().draft, ''); otherMagnet.dispose()
    const original = store(options); discardMiniDraft(r); original.dispose()
    assert.equal(data.size, 0)
  } finally {
    if (old) Object.defineProperty(globalThis, 'localStorage', old)
    else delete (globalThis as any).localStorage
    forgetMiniDrafts()
  }
})


test('real Composer adapter migrates held draft/reply and cannot take the main composer draft', () => {
  forgetMiniDrafts()
  const r = resourceFor(), s = store({ resource: r })
  s.draft('old mini words')
  s.replyTo(adaptTurn(turn()) as never)
  saveDraft(`conversation:${OWN}`, { ...emptyDraft(), text: 'main words' })
  const adapter = miniAsking(r, s)
  assert.match(adapter.where, new RegExp(BOUND))
  assert.ok(adapter.where.includes(r.saved.id))
  assert.notEqual(adapter.where, `conversation:${OWN}`)
  assert.equal(adapter.drafts!.load().text, 'old mini words')
  assert.equal(miniReplyTarget(r)?.id, 'ent-post11111a')
  let changes = 0
  const stop = adapter.drafts!.subscribe(() => changes++)
  adapter.drafts!.save({ ...adapter.drafts!.load(), text: 'mini changed', to: [{ participant: 'ent-agent11111', alias: '@Agent', dispatch: true, consent: { mode: 'all', workspaces: [] }, coordinate: true }] })
  assert.equal(changes, 1)
  assert.equal(s.snapshot().draft, 'mini changed')
  assert.equal(loadDraft(`conversation:${OWN}`).text, 'main words')
  assert.equal(miniComposerDraft(r).to[0].consent?.mode, 'all')
  stop(); s.dispose(); dropDraft(`conversation:${OWN}`)
})

test('bodyOf Work choices and intentional parts survive ordinary Magnet routing', () => {
  const collection = { post: 'ent-collect11111', at: 1, artifact: { ref: 'adm-batch11111', digest: 'digest-1', size: 12, media_type: 'application/json' } }
  const draft = { ...emptyDraft(), text: 'My actual question', to: [{ participant: 'ent-agent11111', alias: '@Agent', dispatch: true,
    runtime: 'codex', model: 'chosen-model', effort: 'high', persona: 'ent-persona111', newInstance: true, coordinate: true,
    consent: { mode: 'task' as const, workspaces: ['C:\\Work'], extra: ['network'] }, followUp: 2, executionMode: 'sandboxed' as const }],
    attached: [{ id: 'extra', name: 'extra', mime: 'text/plain', size: 3, ref: 'adm-extra11111', state: 'held' as const }] }
  const built = bodyOf(draft, ME, ['ent-topic11111'])
  const routed = composerRequest(built, 'mag-fixture', ME, 'ent-reply11111', 'same-op', collection) as any
  assert.deepEqual(routed.from, { magnet: 'mag-fixture' })
  assert.equal(routed.replies_to, 'ent-reply11111')
  assert.deepEqual(routed.parts, built.parts)
  assert.equal(routed.parts.some((p: any) => p.ref === collection.artifact.ref), false)
  for (const [key, value] of Object.entries(built.dispatch[0])) assert.deepEqual(routed.dispatch[0][key], value, key)
  assert.equal(routed.dispatch[0].work, undefined)
  const note = bodyOf({ ...draft, action: 'record-only' }, ME, [])
  const recorded = composerRequest(note, 'mag-fixture', ME, null, 'note-op', null) as any
  assert.equal(recorded.action, 'record-only'); assert.deepEqual(recorded.dispatch, [])
  assert.deepEqual(recorded.parts, note.parts)
  const intake = composerRequest(bodyOf({ ...draft, action: 'ask-mentis', to: [] }, ME, []), 'mag-fixture', ME, null, 'ask-op', collection) as any
  assert.deepEqual(intake.parts, built.parts)
})

test('real adapter reload/retry freezes bodyOf permissions, evidence and op key', async () => {
  forgetMiniDrafts()
  const disk = new Map<string, string>()
  const old = globalThis.localStorage
  Object.defineProperty(globalThis, 'localStorage', { configurable: true, value: { getItem: (k: string) => disk.get(k) ?? null, setItem: (k: string, v: string) => disk.set(k, v), removeItem: (k: string) => disk.delete(k) } })
  try {
    const r = resourceFor(), calls: any[] = []
    let lost = true, batch = 'adm-batch11111'
    const opts = { resource: r, get: async (path: string) => path.includes('participants') ? { status: 200, body: { me: ME, participants: [{ id: 'ent-agent11111', alias: '@Agent', default_runtime: 'codex' }] } }
      : path.endsWith('/collection') ? { status: 200, body: { magnet: r.saved.id, config: r.saved.config, activation: { post: 'ent-collect11111', at: 1, artifact: { ref: batch, digest: batch, size: 1, media_type: 'application/json' } }, page: { sources: [] } } }
      : { status: 200, body: conversationBody() },
      post: async (path: string, body: any, headers: any) => { calls.push({ path, body, headers }); if (lost) throw Error('answer lost'); return { status: 200, body: { post: 'ent-record11111' } } } }
    const first = store(opts), adapter = miniAsking(r, first)
    const d = { ...emptyDraft(), text: 'Retain this question', to: [{ participant: 'ent-agent11111', alias: '@Agent', dispatch: true, coordinate: true, followUp: 2 }] }
    adapter.drafts!.save(d)
    await assert.rejects(adapter.send(bodyOf(d, ME, []), 'original-op', BOUND), /Nothing came back/)
    const original = calls[0]
    assert.equal(miniAttempt(r)?.op, 'original-op')
    first.dispose(); forgetMiniDrafts(); batch = 'adm-newbatch111'; lost = false
    const second = store(opts), again = miniAsking(r, second)
    assert.equal(again.drafts!.load().text, d.text)
    assert.equal(again.drafts!.load().to[0].coordinate, true)
    await again.send(bodyOf(again.drafts!.load(), ME, []), 'new-composer-key', BOUND)
    assert.deepEqual(calls[1], original)
    assert.equal(calls[1].path, '/fluid/api/requests')
    assert.deepEqual(calls[1].body.parts, [{ type: 'text', text: d.text }])
    assert.equal(again.drafts!.load().text, '')
    assert.equal(second.snapshot().uncertain, false)
    const other = store({ ...opts, binding: bound(`${CORPUS}@instance-2`) })
    assert.notEqual(miniComposerWhere(r), adapter.where)
    assert.equal(miniComposerDraft(r).text, '')
    other.dispose(); second.dispose()
  } finally { Object.defineProperty(globalThis, 'localStorage', { configurable: true, value: old }); forgetMiniDrafts() }
})

test('an uncertain shared Composer send cannot silently reuse a different recipient or inquiry', async () => {
  forgetMiniDrafts(); const r = resourceFor(); let count = 0, context = 'lens-one'
  const s = store({ resource: r, contextKey: () => context, get: groundedGet(r), post: async () => { count++; throw Error('lost response') } })
  const draft = { ...emptyDraft(), text: 'Help formulate a question', to: [{ participant: AGENT, alias: '@Agent', dispatch: true }] }
  const adapter = miniAsking(r, s); adapter.drafts!.save(draft)
  const original = bodyOf(draft, ME, [])
  await assert.rejects(adapter.send(original, 'first-help', BOUND), /Nothing came back/)
  const changed = bodyOf({ ...draft, to: [{ participant: 'ent-other111111', alias: '@Other', dispatch: true }] }, ME, [])
  await assert.rejects(adapter.send(changed, 'changed-agent', BOUND), /different recipients/)
  assert.equal(count, 1)
  context = 'lens-two'
  await assert.rejects(adapter.send(original, 'changed-lens', BOUND), /different recipients/)
  assert.equal(count, 1)
  s.dispose(); forgetMiniDrafts()
})

/* -- THE PERSISTENT COMPOSER (hybrid H2) ------------------------------------
 *
 * The composer is the card's own bar in the frame's footer slot, on every tab
 * and in the search overlay; the frame leaves it out of settings and out of a
 * closed card (`Magnet.tsx`, H1). These probes are of what H2 owns: the send
 * choice's seed, what the bar draws, the reading choice, the discussion
 * reference, what a recorded message does to the card, the first send on a
 * Magnet with no Conversation of its own, and the message search source.      */

/** A snapshot with every persisted field at its default, so a probe can set
 *  exactly the one it is about. */
const blankSnapshot = (): MagnetSnapshot => ({
  title: 'Fixture collection', loading: false, results: [],
  x: 12, y: 12, open: true, wide: false, tab: 'Summary', overlay: null,
  places: emptyPlaces(),
  query: '', searchType: 'All', searchTarget: null, searchListScroll: 0, lens: null,
  returnRoute: null, settingsReturn: null, context: null, contextSuppressed: false, carried: null,
})

/** A resource that actually holds what is written to it: the view-state spine
 *  and the context chip are resource state, so a probe of them needs one. */
const living = (over: Partial<MagnetSnapshot> = {}): MagnetResource => {
  let state: MagnetSnapshot = { ...blankSnapshot(), ...over }
  const heard = new Set<() => void>()
  return {
    id: `live${++ids}`, brainKey: SPACE_KEY,
    saved: { id: `mag-live${ids}`, name: 'Fixture collection', config: config() as never },
    snapshot: () => state,
    subscribe: (fn: () => void) => { heard.add(fn); return () => heard.delete(fn) },
    update: (change: Partial<MagnetSnapshot>) => { state = { ...state, ...change }; heard.forEach((fn) => fn()) },
    read: async () => {}, cancel: () => {}, dispose: () => {},
  } as unknown as MagnetResource
}

test('the per-message send choice is a fallback, not a pin (opr-8274edd84e06)', () => {
  forgetMiniDrafts()
  const r = resourceFor()
  const seed = miniComposerDraft(r)
  /* The seed pinned `record-only`, which `actionOf` lets dominate: addressing
     somebody for work could not retarget Send. It now says nothing. */
  assert.equal(seed.action, undefined)
  assert.equal(actionOf(seed), 'ask-mentis')
  assert.equal(sendLabel(actionOf(seed), null), 'Ask Mentis')
  const addressed = { ...seed, to: [{ participant: AGENT, alias: '@Agent', dispatch: true }] } as typeof seed
  assert.equal(actionOf(addressed), 'ask-participant')
  assert.equal(sendLabel(actionOf(addressed), '@Agent'), 'Ask @Agent')
  /* Record only is still the owner's per-message choice, and still dominates
     a contradiction: `actionOf` itself is untouched. */
  assert.equal(actionOf({ ...addressed, action: 'record-only' }), 'record-only')
  assert.equal(sendLabel('record-only', '@Agent'), 'Record')
  /* After a send the hold is let go, so the next message starts from the same
     fallback rather than from the last message's choice. */
  saveMiniComposer(r, { ...seed, text: 'words', action: 'record-only' })
  discardMiniDraft(r)
  assert.equal(miniComposerDraft(r).action, undefined)
  forgetMiniDrafts()
})

/** What the bar draws around the composer. The real `fluid/Composer` is
 *  client-only -- its facts store has no server snapshot -- so it is supplied
 *  here as the one textarea it renders, exactly as the Edge fixture supplies
 *  the real one. The behavioural oracle for the composer itself is
 *  `quiet_magnet_mini_browser.py`. */
const barView = (over: Partial<ComposerBarViewProps> = {}) => renderToStaticMarkup(createElement(ComposerBarView, {
  canWrite: true, chip: null, suppressed: false, onRemoveChip: () => {},
  frozen: false, sending: false, creating: false, uncertain: false, canRetry: true, onRetry: () => {},
  composer: createElement('textarea', { 'aria-label': 'Message this Magnet' }),
  ...over,
}))

test('the Conversation view holds no composer: the card’s one composer is the footer bar', () => {
  forgetMiniDrafts()
  const view = renderToStaticMarkup(createElement(MiniConversation, {
    resource: resourceFor(), onFull: () => {}, canWrite: true,
  }))
  /* Deliberate, and the reason is the approved design: there is one composer,
     in the footer, so this view has none -- and the two controls that used to
     sit beside it have their own homes (the reading choice in the bar's menu,
     the Perspective selector in the Perspectives view, which H5 owns). */
  assert.doesNotMatch(view, /textarea/)
  assert.doesNotMatch(view, /Assistance mode/)
  assert.doesNotMatch(view, /Active Perspective/)
  assert.doesNotMatch(view, /<select/)
  /* NO STANDING ADMINISTRATIVE PROSE (owner §6): the sentence about what an
     agent reads here is not drawn above every message any more. What a message
     carries is said by the composer, beside the words, when there is something
     to say. */
  assert.doesNotMatch(view, /Selected collection evidence is recorded separately/)
  assert.match(view, /Open full Conversation/)

  const bar = barView()
  assert.equal([...bar.matchAll(/<textarea/g)].length, 1, 'exactly one composer textarea in the bar')
  assert.doesNotMatch(bar, /<select/, 'no select anywhere in the composer')
  /* AND NO RETAINED-ANSWER AFFORDANCE, nor the status badge that stood beside
     it: answering from the collection is unavailable while configured-source
     access is unenforced, so the composer offers no choice about it. */
  assert.doesNotMatch(bar, /What Mentis reads/)
  assert.doesNotMatch(bar, /retained/i)
  assert.doesNotMatch(bar, /Grounded execution off/)

  const readOnly = barView({ canWrite: false })
  assert.doesNotMatch(readOnly, /textarea/)
  assert.match(readOnly, /Sending is unavailable for this Magnet here/)
  forgetMiniDrafts()
})

test('the bar is one bar, with no tab or overlay of its own to vary by', () => {
  /* The bar takes nothing from the tab: the frame supplies it once, into the
     footer slot, and leaves it out of settings and out of a closed card
     (`Magnet.tsx:219`, H1's, asserted by `quiet_magnet_hybrid_shell_unit.ts`
     and by `quiet_magnet_puck_unit.ts`'s "one composer on every tab"). What
     this probe holds is that nothing here reads the tab. */
  const bar = readFileSync(new URL('../src/quiet2/magnets/ComposerBar.tsx', import.meta.url), 'utf8')
  const render = bar.slice(bar.indexOf('export function ComposerBarView'))
  assert.doesNotMatch(render, /\.tab\b/, 'what the bar draws does not depend on which tab is open')
  assert.doesNotMatch(render, /overlay/, 'nor on which overlay is open')
  /* and both states it does vary by are drawn */
  assert.match(barView({ unavailable: NO_OWN_CONVERSATION }), /Sending makes one and records the message in it/)
  assert.match(barView({ frozen: true }), /<fieldset[^>]*disabled/)
})

test('there is no reading choice and no retained-answer affordance left in the bar', () => {
  /* The two-item reading menu is gone with the capability it offered. Nothing
     in the composer proposes answering from the retained collection, and the
     persisted mode is not read by anything this file draws: the choice would
     have been a control over something that refuses. */
  const bar = readFileSync(new URL('../src/quiet2/magnets/ComposerBar.tsx', import.meta.url), 'utf8')
  assert.doesNotMatch(bar, /menuitemradio/)
  assert.doesNotMatch(bar, /assistanceMode/)
  assert.doesNotMatch(bar, /_magnetAssistance/, 'no client-only instruction marker is built here any more')
  assert.doesNotMatch(barView({ chip: null, suppressed: true }), /menuitemradio/)
})

test('old assistance markers refuse and an available collection adds no authored content', () => {
  assert.throws(() => composerRequest({ action: 'ask-mentis', text: 'Help', parts: [],
    _magnetAssistance: { configuration: {} } }, 'mag-fixtureA', ME, null, 'old', null), /old Magnet send/)
  const plain = { action: 'ask-mentis', text: 'What can this collect?',
    parts: [{ type: 'text', text: 'What can this collect?' }], dispatch: [] }
  const ordinary = composerRequest(plain, 'mag-fixtureA', ME, null, 'ordinary',
    { post: 'ent-collect11111', artifact: { ref: 'adm-batch111111', digest: 'a'.repeat(64),
      size: 1, media_type: 'application/json' }, at: 1 })
  assert.deepEqual(ordinary.parts, plain.parts)
  assert.equal(ordinary.text, plain.text)
})

test('the discussion reference attaches once, is never silently replaced, and never reattaches after removal', () => {
  forgetMiniDrafts()
  const r = living()
  const post = { ref: 'ent-post11111a', kind: 'post' as const, label: 'First words.' }
  const other = { ref: 'ent-post11111b', kind: 'post' as const, label: 'Second.' }
  /* attaches when nothing is attached and nothing is suppressed */
  assert.equal(attachContext(r, post), true)
  assert.deepEqual(r.snapshot().context, post)
  /* never silently replaced by a later candidate */
  assert.equal(attachContext(r, other), false)
  assert.deepEqual(r.snapshot().context, post)
  /* removing keeps the words and suppresses further automatic attachment */
  setMiniDraft(r, 'words I already typed')
  removeContext(r)
  assert.equal(r.snapshot().context, null)
  assert.equal(r.snapshot().contextSuppressed, true)
  assert.equal(miniDraft(r), 'words I already typed')
  assert.equal(attachContext(r, other), false, 'typing does not put it back')
  /* the explicit act may replace it, and clears suppression */
  discussEvidence(r, other)
  assert.deepEqual(r.snapshot().context, other)
  assert.equal(r.snapshot().contextSuppressed, false)
  clearContext(r)
  assert.equal(r.snapshot().context, null)
  assert.equal(r.snapshot().contextSuppressed, false)
  forgetMiniDrafts()
})

test('the candidate reference is the inspected item of the current place, else the selected Perspective', () => {
  const r = living()
  assert.equal(contextCandidate(r), null, 'nothing is volunteered where nothing is open')
  /* AND ONLY WHAT A MESSAGE CAN ACTUALLY CARRY. A candidate becomes a chip by
     itself, on the first keystroke, so one the card cannot state by exact
     identity would leave Send with nothing it could do: a collected post has
     no exact authored version here, and a file with no recorded digest has no
     identity to send. Both are still attachable deliberately, and the composer
     then says why they cannot go (`quiet_magnet_composer_boundary_unit.ts`). */
  r.update({ tab: 'Posts', places: { ...r.snapshot().places, Posts: { ...emptyPlace(), inspected: 'ent-post11111a' } },
    results: [{ kind: 'post', id: 'ent-post11111a', value: { title: 'First words.' } }] as never })
  assert.equal(contextCandidate(r), null)
  r.update({ tab: 'Files', places: { ...r.snapshot().places, Files: { ...emptyPlace(), inspected: 'adm-batch111111' } } })
  assert.equal(contextCandidate(r), null)
  /* a held file whose digest the collection read states is one exact reference */
  r.update({ results: [{ kind: 'file', id: 'adm-batch111111', value: { digest: 'a'.repeat(64), title: 'notes.txt' } }] as never })
  assert.deepEqual(contextCandidate(r), { ref: 'adm-batch111111', kind: 'file', label: 'notes.txt' })
  /* the Perspectives view offers the selected Perspective and nothing else */
  r.update({ tab: 'Perspectives', lens: 'ent-lens1111111' })
  assert.deepEqual(contextCandidate(r, { perspective: 'ent-lens1111111', name: 'Cost of delay' }), { ref: 'ent-lens1111111', kind: 'perspective', label: 'Cost of delay' })
  r.update({ tab: 'Summary' })
  assert.equal(contextCandidate(r, { perspective: 'ent-lens1111111', name: 'Cost of delay' }), null)
})

test('a reply target is restored only with its intentional non-empty draft', () => {
  const target = { id: 'ent-post11111a', number: 4, alias: '@brian' }
  assert.equal(restoredReplyTarget('', target), null)
  assert.equal(restoredReplyTarget('   ', target), null)
  assert.deepEqual(restoredReplyTarget('intentional reply', target), target)
})

test('a message carries the reference, never the captured content', () => {
  const r = living()
  const plain = { action: 'ask-mentis', text: 'Explain this', parts: [{ type: 'text', text: 'Explain this' }] }
  assert.deepEqual(withContext(r, plain), plain, 'no chip, no change')
  discussEvidence(r, { ref: 'ent-post11111a', kind: 'post', label: 'First words.', text: 'THE WHOLE CAPTURED BODY' })
  assert.throws(() => withContext(r, plain), /exact version/)
  const selected = { ...plain, magnet_context: { version: 1, mode: 'ordinary',
    configuration_digest: 'a'.repeat(64), perspective: null,
    references: [{ kind: 'post', ref: 'ent-post11111a', version: 'ent-post11111a', digest: 'b'.repeat(64) }] } }
  const carried = withContext(r, selected)
  assert.deepEqual(carried.parts, plain.parts)
  assert.equal(carried.text, plain.text)
  assert.doesNotMatch(JSON.stringify(carried), /THE WHOLE CAPTURED BODY/)

})

test('a recorded message saves the way back, goes to the Conversation and pins it to the bottom', () => {
  const r = living()
  r.update({ tab: 'All', places: { ...r.snapshot().places, All: { ...emptyPlace(), scroll: 420, inspected: 'ent-post11111a' } } })
  /* the reference went with the words, so it is let go with them */
  discussEvidence(r, { ref: 'ent-post11111a', kind: 'post', label: 'First words.' })
  afterSent(r)
  const after = r.snapshot()
  assert.equal(after.context, null)
  assert.equal(after.contextSuppressed, false)
  assert.equal(after.tab, 'Conversation')
  assert.equal(after.returnRoute?.tab, 'All')
  assert.equal(after.returnRoute?.placeKey, 'All')
  assert.equal(after.returnRoute?.placeSnapshot.scroll, 420)
  assert.equal(after.returnRoute?.placeSnapshot.inspected, 'ent-post11111a')
  assert.equal(after.places.Conversation.scroll, PIN_TO_BOTTOM)
  /* a deep snapshot: mutating the live place afterwards cannot move the way back */
  r.update({ places: { ...after.places, All: { ...after.places.All, scroll: 9 } } })
  assert.equal(r.snapshot().returnRoute?.placeSnapshot.scroll, 420)
  /* sending from the Conversation stays there and invents no return */
  const inside = living()
  inside.update({ tab: 'Conversation' })
  afterSent(inside)
  assert.equal(inside.snapshot().returnRoute, null)
  assert.equal(inside.snapshot().tab, 'Conversation')
  /* restoring the way back moves the card and never the words */
  setMiniDraft(r, 'still being written')
  restore(r, r.snapshot().returnRoute!)
  assert.equal(r.snapshot().tab, 'All')
  assert.equal(r.snapshot().places.All.scroll, 420)
  assert.equal(miniDraft(r), 'still being written')
  forgetMiniDrafts()
})

/* -- a success that arrives while the footer is not mounted ----------------- */

test('a send notes what it carries under its own key, with the position it was written from', () => {
  const r = living({ tab: 'Files', places: { ...emptyPlaces(), Files: { ...emptyPlace(), scroll: 450 } } })
  discussEvidence(r, { ref: 'adm-context1111', kind: 'file', label: 'old evidence' })
  carryContext(r, 'op-first')
  const note = r.snapshot().carried!
  assert.equal(note.op, 'op-first')
  assert.deepEqual(note.context, { ref: 'adm-context1111', kind: 'file', label: 'old evidence' })
  assert.equal(note.suppressed, false)
  assert.equal(note.from.tab, 'Files')
  assert.equal(note.from.placeSnapshot.scroll, 450, 'the reading position is taken at the press')
  /* a deep copy: the card moving afterwards cannot move the note */
  r.update({ tab: 'Perspectives', context: null })
  assert.equal(r.snapshot().carried?.from.tab, 'Files')
  assert.deepEqual(r.snapshot().carried?.context, { ref: 'adm-context1111', kind: 'file', label: 'old evidence' })
})

test('a success received while the footer is unmounted still moves to the Conversation, from where it was sent', () => {
  const r = living({ tab: 'Files', places: { ...emptyPlaces(), Files: { ...emptyPlace(), scroll: 450 } } })
  discussEvidence(r, { ref: 'adm-context1111', kind: 'file', label: 'old evidence' })
  carryContext(r, 'op-closed')
  /* the card is closed and reopened while the answer is on its way: the bar is
     gone and comes back, and its place is read again from nothing */
  const note = r.snapshot().carried!
  r.update({ open: false })
  r.update({ open: true, places: { ...r.snapshot().places, Files: { ...emptyPlace(), scroll: 0 } } })
  afterSent(r, note)
  const after = r.snapshot()
  assert.equal(after.tab, 'Conversation', 'the move happens when the bar can next make it')
  assert.equal(after.context, null, 'the reference that went is let go')
  assert.equal(after.contextSuppressed, false)
  assert.equal(after.carried, null, 'the note is consumed, so this settles once')
  assert.equal(after.returnRoute?.tab, 'Files')
  assert.equal(after.returnRoute?.placeSnapshot.scroll, 450, 'the way back is where the owner was writing from')
  assert.equal(after.places.Conversation.scroll, PIN_TO_BOTTOM)
  /* and the message after it carries nothing of the one that was sent */
  assert.deepEqual(withContext(r, { action: 'ask-mentis', text: 'next unrelated message', parts: [] }),
    { action: 'ask-mentis', text: 'next unrelated message', parts: [] })
})

test('a reference attached while the send was unresolved belongs to the next message and is left alone', () => {
  const r = living({ tab: 'Summary' })
  discussEvidence(r, { ref: 'adm-context1111', kind: 'file', label: 'old evidence' })
  carryContext(r, 'op-pending')
  const note = r.snapshot().carried!
  /* the owner goes on writing under the unresolved send */
  discussEvidence(r, { ref: 'adm-context2222', kind: 'file', label: 'what I am asking about now' })
  afterSent(r, note)
  assert.deepEqual(r.snapshot().context, { ref: 'adm-context2222', kind: 'file', label: 'what I am asking about now' })
  assert.equal(r.snapshot().carried, null)
  assert.equal(r.snapshot().tab, 'Conversation', 'the transition still happens')
  /* the same holds for a suppression made since: it is the next message's */
  const again = living({ tab: 'Summary' })
  discussEvidence(again, { ref: 'adm-context1111', kind: 'file', label: 'old evidence' })
  carryContext(again, 'op-removed')
  const second = again.snapshot().carried!
  removeContext(again)
  afterSent(again, second)
  assert.equal(again.snapshot().context, null)
  assert.equal(again.snapshot().contextSuppressed, true, 'the owner undid the chip after sending; that stands')
  assert.equal(again.snapshot().carried, null)
})

test('the same key answered twice settles the card once', () => {
  const r = living({ tab: 'Files' })
  discussEvidence(r, { ref: 'adm-context1111', kind: 'file', label: 'old evidence' })
  carryContext(r, 'op-replayed')
  const note = r.snapshot().carried!
  afterSent(r, note)
  r.update({ tab: 'Files' })                       // the owner goes back to read
  discussEvidence(r, { ref: 'adm-context3333', kind: 'file', label: 'a new question' })
  assert.equal(r.snapshot().carried, null, 'nothing is owed for that key any more')
  /* which is what the bar reads: no note, no second act (see ComposerBar) */
  assert.deepEqual(r.snapshot().context, { ref: 'adm-context3333', kind: 'file', label: 'a new question' })
  assert.equal(r.snapshot().tab, 'Files')
})

test('the first send on a Magnet with no Conversation of its own makes one and records the message in it', async () => {
  sends.length = 0; forgetMiniDrafts()
  const mine = resourceFor({ conversation: null })
  const { get } = seam((path) => path.startsWith('/fluid/api/participants')
    ? participants(ME)
    : { status: 200, body: conversationBody() })
  const s = store({
    resource: mine, get,
    post: sender(async () => ({ status: 200, body: { post: 'ent-new111111c', home: OWN, number: 1, replayed: false } })),
  })
  assert.equal(s.snapshot().unavailable, NO_OWN_CONVERSATION)
  s.draft('Ordinary help before anything is collected.')
  await s.send()
  assert.equal(sends.length, 1, 'one audited request creates the Conversation and records the message atomically')
  assert.equal(sends[0].path, '/fluid/api/requests')
  assert.equal(sends[0].body.conversation, undefined)
  assert.deepEqual(sends[0].body.from, { magnet: mine.saved.id })
  assert.equal(sends[0].body.text, 'Ordinary help before anything is collected.')
  assert.equal(s.conversation, OWN)
  assert.equal(s.snapshot().unavailable, undefined)
  assert.equal(s.snapshot().sent?.post, 'ent-new111111c')
  assert.equal(s.snapshot().draft, '')
  s.dispose(); forgetMiniDrafts()
})

test('a Magnet pointed at one of its own sources still creates nothing and sends nothing', async () => {
  sends.length = 0; forgetMiniDrafts()
  const mine = resourceFor({ conversation: SOURCE })
  const { get } = seam(() => ({ status: 200, body: conversationBody() }))
  const s = store({ resource: mine, get, post: sender(async () => ({ status: 200, body: {} })) })
  s.draft('words')
  await s.send()
  assert.equal(sends.length, 0)
  assert.equal(s.conversation, null)
  assert.equal(s.snapshot().sendError, OWN_IS_A_SOURCE)
  assert.equal(miniDraft(mine), 'words', 'the words are kept where nothing was sent')
  s.dispose(); forgetMiniDrafts()
})

test('messageSource searches the Conversation itself, not the page the card happens to hold', async () => {
  const loaded = [
    { id: 'ent-loaded11111', number: 31, text: 'the newest page mentions needle once' },
    { id: 'ent-loaded22222', number: 32, text: 'nothing matching here' },
  ]
  const asked: string[] = []
  const opened: string[] = []
  const hits = (post: string, number: number) => ({ post, number, snippet: `…needle in #${number}…`, at: 1 })
  const get: MiniGet = async (path) => {
    asked.push(path)
    if (path.includes('before=')) return { status: 200, body: { hits: [hits('ent-older222222', 2)], more: false } }
    return { status: 200, body: { hits: [hits('ent-older111111', 1)], more: true } }
  }
  const source = messageSource({ conversation: OWN, snapshot: () => ({ posts: loaded }) } as never, (p) => opened.push(p), get)
  assert.equal(source.queryDependent, true)
  assert.deepEqual(source.entries().map((e) => e.key), ['Conversation:ent-loaded11111', 'Conversation:ent-loaded22222'])
  const found = await source.complete!('needle')
  const keys = found.map((e) => e.key)
  /* the loaded match, and two matches on pages the card never read */
  assert.deepEqual(keys, ['Conversation:ent-loaded11111', 'Conversation:ent-older111111', 'Conversation:ent-older222222'])
  assert.equal(found.every((e) => e.kind === 'Conversation'), true)
  assert.match(asked[0], /^\/fluid\/api\/search\?conversation=ent-ownconv11111&q=needle&limit=30$/)
  assert.match(asked[1], /&before=ent-older111111$/)
  assert.equal(source.bound!(), null, 'a search that finished claims no bound')
  found.find((e) => e.key === 'Conversation:ent-older222222')!.open()
  assert.deepEqual(opened, ['ent-older222222'], 'a hit opens the post it names')
})

test('the message search says its bound, its refusal and its absence rather than claiming a search', async () => {
  const endless: MiniGet = async () => ({ status: 200, body: { hits: [{ post: `ent-p${Math.random().toString(36).slice(2, 10)}`, number: 1, snippet: 'needle', at: 1 }], more: true } })
  const paging = messageSource({ conversation: OWN, snapshot: () => ({ posts: [] }) } as never, () => {}, endless)
  await paging.complete!('needle')
  assert.equal(paging.bound!(), MESSAGE_SEARCH_BOUND)

  const refused: MiniGet = async () => ({ status: 403, body: { error: 'this Conversation is not visible here' } })
  const no = messageSource({ conversation: OWN, snapshot: () => ({ posts: [] }) } as never, () => {}, refused)
  assert.deepEqual(await no.complete!('needle'), [])
  assert.match(String(no.bound!()), /not visible here/)

  const none = messageSource({ conversation: null, snapshot: () => ({ posts: [] }) } as never, () => {}, endless)
  assert.deepEqual(await none.complete!('needle'), [])
  assert.equal(none.bound!(), NO_CONVERSATION_TO_SEARCH)
})

test('the composer bar adds no send semantics of its own: the five conventions are the real Composer’s', () => {
  const bar = readFileSync(new URL('../src/quiet2/magnets/ComposerBar.tsx', import.meta.url), 'utf8')
  assert.doesNotMatch(bar, /dangerouslySetInnerHTML|innerHTML/)
  assert.doesNotMatch(bar, /setInterval|setTimeout|requestIdleCallback|EventSource|new WebSocket/)
  assert.doesNotMatch(bar, /history\.(push|replace)State|location\.(assign|replace|hash)/)
  assert.doesNotMatch(bar, /key === 'Enter'/, 'the bar implements no send key of its own')
  assert.doesNotMatch(barView(), /<select/, 'no select is rendered in the composer')
  /* The conventions themselves, where they actually live. The behavioural
     oracle is the browser suite (quiet_magnet_mini_browser.py); this asserts
     that the bar routes through the handler that has them. */
  const real = readFileSync(new URL('../src/fluid/Composer.tsx', import.meta.url), 'utf8')
  assert.match(real, /if \(e\.nativeEvent\.isComposing\) return/)
  assert.match(real, /e\.key === 'Enter' && e\.altKey[\s\S]{0,80}record-only/)
  assert.match(real, /if \(e\.ctrlKey \|\| e\.metaKey\)/)
  assert.match(real, /e\.key === 'Enter' && e\.shiftKey/)
  assert.match(real, /disabled=\{busy \|\| isEmpty\(draft\) \|\| !me\}/)
  assert.match(bar, /import Composer from '\.\.\/\.\.\/fluid\/Composer'/)
})

test('mini text projection preserves whitespace, line endings and combining characters', () => {
  const words = '  how do I configure a magnet?\r\n??e?  '
  assert.equal(textOfTurn(turn({ parts: [{ type: 'text', text: words }] }) as never), words)
})

/* The returned D selector and draft functions through A's actual adapter/store,
 * including record-only. These exercise the serialized request, not source probes. */
test('joined composer preserves raw words and explicit empty selections on every action', async () => {
  for (const action of ['record-only', 'ask-mentis', 'ask-participant'] as const) {
    forgetMiniDrafts()
    const r = living({ lens: 'ent-selected111', contextSuppressed: true })
    r.saved.config = { ...r.saved.config!, sources: [] }
    const calls: Record<string, unknown>[] = []
    let prepared = 0
    const s = store({ resource: r, get: groundedGet(r),
      beforeRequest: async (post, op) => {
        prepared++
        const selector = await managedSelector({ resource: r, inquiries: {
          ordinaryContext: async () => { throw Error('removed question must not be read') },
          snapshot: () => ({ rows: [] }),
        } }, post)
        return { post: { ...post, magnet_context: selector }, op }
      },
      post: async (_path, body) => { calls.push(JSON.parse(JSON.stringify(body))); return {
        status: 200, body: { post: 'ent-record11111', route: { conversation: OWN } },
      } },
    })
    const adapter = miniAsking(r, s)
    const raw = '  help #setup\r\n\u{1f9f2}e\u0301  '
    const d = { ...emptyDraft(), action, text: raw,
      marks: [{ kind: 'topic' as const, topic: 'ent-topic11111', text: '#setup', start: 7 }],
      to: action === 'ask-participant' ? [{ participant: AGENT, alias: '@Agent', dispatch: true,
        coordinate: false, followUp: 1, consent: { mode: 'ask' as const, workspaces: [] } }] : [],
    }
    adapter.drafts!.save(d)
    const authored = bodyOf(d, ME, [], 'ask-mentis', { references: 'audited' })
    await adapter.send(authored, `joined-${action}`, BOUND)
    assert.equal(prepared, 1, action)
    assert.equal(calls.length, 1, action)
    assert.equal(calls[0].text, raw)
    assert.deepEqual(calls[0].parts, authored.parts)
    const selector = calls[0].magnet_context as any
    assert.equal(selector.configuration_digest, await definitionConfigurationDigest(r.saved.config! as never))
    assert.equal(selector.perspective, null, 'a removed selected lens is never inferred')
    assert.deepEqual(selector.references, [])
    assert.equal(calls[0].action, action)
    assert.equal((calls[0].dispatch as any[]).some((spec) => spec.work), false)
    if (action === 'ask-participant') {
      const dispatch = (calls[0].dispatch as any[])[0]
      assert.equal(dispatch.coordinate, false)
      assert.equal(dispatch.follow_up.depth, 1)
      assert.deepEqual(dispatch.consent, { mode: 'ask', workspaces: [] })
    }
    s.dispose()
  }
  forgetMiniDrafts()
})

test('joined selector freezes the original question and configuration across uncertain remount', async () => {
  forgetMiniDrafts()
  const r = living({ context: { ref: 'ent-question111', kind: 'perspective', label: 'Setup' } })
  const calls: any[] = []
  let prepared = 0, lost = true
  const opts = { resource: r, get: groundedGet(r),
    beforeRequest: async (post: Record<string, unknown>, op: string) => {
      prepared++
      return { post: { ...post, magnet_context: await managedSelector({ resource: r, inquiries: {
        ordinaryContext: async () => ({ perspective: 'ent-question111', revision: 'adm-question111' }),
        snapshot: () => ({ rows: [{ perspective: 'ent-question111',
          question: { ref: 'adm-question111', digest: 'b'.repeat(64) } }] }),
      } }, post) }, op }
    },
    post: async (path: string, body: any, headers: any) => {
      calls.push({ path, body: JSON.parse(JSON.stringify(body)), headers })
      if (lost) throw Error('receipt lost')
      return { status: 200, body: { post: 'ent-record11111' } }
    },
  }
  const first = store(opts), adapter = miniAsking(r, first)
  const d = { ...emptyDraft(), action: 'record-only' as const, text: '  a note about this question  ' }
  adapter.drafts!.save(d)
  await assert.rejects(adapter.send(bodyOf(d, ME, []), 'frozen-question-note', BOUND), /Nothing came back/)
  assert.equal(prepared, 1)
  const original = miniAttempt(r)!
  first.dispose()
  r.saved.config = { ...r.saved.config!, identity: { name: 'Changed after the uncertain send' } } as never
  lost = false
  const back = store(opts)
  await back.submit(original.request!.body, original.op, original.brain)
  assert.deepEqual(calls[1], calls[0])
  assert.equal(prepared, 1, 'receipt replay never rebuilds a newer selector')
  assert.equal(calls[1].body.magnet_context.perspective.question_ref, 'adm-question111')
  assert.equal(miniAttempt(r), null)
  back.dispose()
  forgetMiniDrafts()
})

test('D composer digest matches B snapshots for every actual wire-definition vector', async () => {
  const vectors = JSON.parse(readFileSync(new URL('../../../tests/fixtures/magnet-definition-digest/vectors.json', import.meta.url), 'utf8'))
  for (const vector of vectors.vectors) {
    /* The arrangement/collection API strips the file-only schema_version
       (magnet.wire); ComposerBar receives the whole remaining definition. */
    const wire = { ...vector.definition }
    delete wire.schema_version
    assert.equal(await composerConfigurationDigest(wire), vector.digest, vector.name)
    assert.equal(await definitionConfigurationDigest(wire), vector.digest, vector.name)
  }
})
