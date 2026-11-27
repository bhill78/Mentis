/* READING A MAGNET POST'S ANSWER WHERE IT WAS ASKED (ent-e4257d0e65e5).
 *
 * A question asked in a Magnet's mini Conversation is answered by an agent as
 * an ordinary reply. The owner reads it in the card two ways: the fold under
 * the post ("1 reply") and "Read the thread". Both end in the same place --
 * the thread read, by root, into the one store of posts -- and both are only
 * worth pressing if that read leaves the REPLY'S OWN WORDS in hand.
 *
 * ent-e4257d0e65e5 reported the opposite: the affordances shown, the thread
 * read answering zero rows for that root, and nothing expanded. It did not
 * reproduce (the route answers `replies_total: 1`, and headless Edge and
 * Chrome both draw the reply on the TEST candidate). These are the checks
 * that would have failed had it been true, so the claim is answered by a
 * check from now on rather than by a browser session.
 *
 * The fixture is the record as TEST holds it: post #68 `ent-4ff244281f4e` in
 * conversation `ent-0db5ea9a3307`, answered by #69 `ent-511aec1ae11e`, whose
 * words cite `adm-e3d8cae2cb43`. The bodies below are the shapes
 * `/api/conversations/<id>` and `/api/conversations/<id>/thread/<root>`
 * return for them.
 *
 * Every read goes through an injected `fetch`. Nothing here opens a Brain,
 * starts a server or reaches the network. */
import assert from 'node:assert/strict'
import { test } from 'node:test'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { PageContext, type PostPage } from '../src/quiet2/Post'
import { ReplyFold } from '../src/quiet2/Thread'
import { adapt, childrenOf, postOf, putPosts, readThread, threadRootOf, threadSize } from '../src/quiet2/real'

const CONVERSATION = 'ent-0db5ea9a3307'
const ROOT = 'ent-4ff244281f4e'
const REPLY = 'ent-511aec1ae11e'
const CITED = 'adm-e3d8cae2cb43@a79673349571[0:7631]'
/** a phrase of the reply that appears nowhere else, so finding it is finding
 *  the ANSWER and not its heading, its byline or its count */
const ANSWERED = 'interpret Roman’s future observations'

const ASKED = "From this record alone, what does NASA say Hubble's observations of the "
  + 'galactic bulge are meant to do for the Roman Space Telescope, and what does the '
  + 'record not establish?'
const REPLIED = 'NASA says Hubble’s survey is intended to help researchers **interpret '
  + 'Roman’s future observations** of the crowded galactic bulge. When Roman observes '
  + 'such an event, researchers can compare the two datasets to interpret it more easily '
  + `and search for planets. [NASA’s collected article](${CITED})\n\n`
  + 'The record describes that purpose and anticipated comparison; it **does not '
  + 'establish that Roman has already observed a microlensing event**.'

/** The Turn shape both routes carry, with the fields this path reads. */
const turn = (over: Record<string, unknown> = {}) => ({
  id: ROOT, number: 68, parts: [{ type: 'text', text: ASKED }],
  author: 'ent-5936369158a8', author_alias: '@brian',
  written_by: 'unattributed-local-request', at: 1795742390.58,
  addressees: [], topics: [], anchors: [], returned_with: [],
  answering: null, answering_number: null, replies: [REPLY], root: ROOT,
  thread_replies: 1, expectations: [], operational_acts: 10,
  ...over,
})

const repliedTurn = () => turn({
  id: REPLY, number: 69, parts: [{ type: 'text', text: REPLIED }],
  author: 'ent-3a5fb342dd6b', author_alias: '@Caretaker',
  written_by: 'claude/b4cb0d79', answering: ROOT, answering_number: 68,
  replies: [], thread_replies: 0,
})

/** What the server answers for this thread, exactly as the route shapes it. */
const threadBody = () => ({
  conversation: CONVERSATION, root: ROOT, turn: turn(),
  replies_total: 1, replies: [repliedTurn()],
})

/** What it answers when the REPLY is asked for instead of its root: the
 *  route names the root rather than serving a thread (`threadRootOf`). */
const replyAsked = () => ({
  error: `${REPLY} is a reply, not a thread root; its thread is ${ROOT}`,
  thread: REPLY, root: ROOT,
})

/** The one seam: `real.ts` reads through the global `fetch` and nothing else. */
function servedBy(body: (url: string) => unknown) {
  const asked: string[] = []
  const was = globalThis.fetch
  globalThis.fetch = (async (url: string) => {
    asked.push(String(url))
    return { ok: true, status: 200, statusText: 'OK', json: async () => body(String(url)) }
  }) as unknown as typeof fetch
  return { asked, restore: () => { globalThis.fetch = was } }
}

/** The words a post's body draws, joined as `adapt` leaves them. */
const drawnWords = (id: string) =>
  (postOf(id)?.blocks ?? []).map((b) => (b.kind === 'text' ? b.md : '')).join('\n')

test('the thread read answers this root with its reply, not zero rows', async () => {
  const seam = servedBy(threadBody)
  try {
    await readThread(CONVERSATION, ROOT)
    assert.deepEqual(seam.asked, [`/api/conversations/${CONVERSATION}/thread/${ROOT}`])
    assert.deepEqual(childrenOf(ROOT).map((p) => p.id), [REPLY])
    assert.equal(threadSize(ROOT), 1)
    assert.equal(postOf(REPLY)?.conversation, CONVERSATION)
    assert.equal(postOf(REPLY)?.replyTo, ROOT)
    assert.equal(postOf(REPLY)?.number, 69)
  } finally { seam.restore() }
})

test('the reply the card draws is the agent’s own words, with its citation', async () => {
  const seam = servedBy(threadBody)
  try {
    await readThread(CONVERSATION, ROOT)
    const words = drawnWords(REPLY)
    assert.ok(words.includes(ANSWERED), 'the reply’s answer is not among the words drawn')
    assert.ok(words.includes(CITED), 'the reply’s citation is not among the words drawn')
    assert.ok(words.includes('does not establish'), 'the reply’s limits are not drawn')
    /* and the question it answers is still the post above it */
    assert.ok(drawnWords(ROOT).includes('what does the record not establish?'))
    assert.equal(postOf(REPLY)?.by.agent, true, 'the reply is not drawn as an agent’s')
  } finally { seam.restore() }
})

test('the fold offers both ways in, and says how many replies there are', async () => {
  const seam = servedBy(threadBody)
  try {
    await readThread(CONVERSATION, ROOT)
    const page = {
      me: null, who: null, topic: null, compact: true,
      onWho: () => {}, onTopic: () => {}, onReply: () => {},
      onEnter: () => {}, onBeside: null, onView: () => {},
      openElsewhere: () => null, say: () => {}, working: [],
    } as unknown as PostPage
    const html = renderToStaticMarkup(createElement(PageContext.Provider, { value: page },
      createElement(ReplyFold, { root: ROOT })))
    assert.match(html, /1 reply/)
    assert.match(html, /Read the thread/)
    assert.doesNotMatch(html, /open in /, 'the card sends the owner out of the Magnet to read it')
  } finally { seam.restore() }
})

test('asked for the reply, the route names its root so the card can read it', async () => {
  const seam = servedBy((url) => (url.includes(REPLY) ? replyAsked() : threadBody()))
  try {
    assert.equal(await threadRootOf(CONVERSATION, REPLY), ROOT)
    assert.equal(await threadRootOf(CONVERSATION, ROOT), ROOT)
  } finally { seam.restore() }
})

/* THE TRAP THIS GUARDS. The flow read that drew the post may predate the
   reply: the post is then held with `replies: []`, and AN EMPTY ARRAY IS
   TRUTHY, so `childrenOf` answers from it and finds nothing. If the thread
   read left that stale list standing, the fold would open on nothing -- which
   is exactly what ent-e4257d0e65e5 described. */
test('a post first read before it was answered carries the reply afterwards', async () => {
  putPosts([adapt(turn({ replies: [], thread_replies: 0 }) as never, CONVERSATION, () => undefined)])
  assert.deepEqual(childrenOf(ROOT).map((p) => p.id), [], 'the fixture is not the stale state')
  assert.equal(threadSize(ROOT), 0)
  const seam = servedBy(threadBody)
  try {
    await readThread(CONVERSATION, ROOT)
    assert.deepEqual(childrenOf(ROOT).map((p) => p.id), [REPLY])
    assert.equal(threadSize(ROOT), 1)
    assert.ok(drawnWords(REPLY).includes(ANSWERED))
  } finally { seam.restore() }
})
