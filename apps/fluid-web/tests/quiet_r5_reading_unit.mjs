/* QUIET CHAT ROUND 5, PACKAGE R: THE READING'S OWN PLACE.
 *
 * What this suite is for: the expensive mistakes in a reading restoration are
 * not in the storage underneath it (that is S's) but in the ARITHMETIC and the
 * PRECEDENCE around it, and both can be checked without a browser:
 *
 *  - a post's offset is measured from the pinned header's edge, and the post
 *    chosen is one the reader could actually SEE -- not one behind a thread's
 *    pinned parent header, and not an arbitrary loaded id;
 *  - putting it back is computed against what is drawn NOW, so heights that
 *    changed in between are not a wrong answer but the right one;
 *  - a post that is not drawn at all -- filtered out, not loaded, deleted --
 *    answers "no", which is a recoverable state and never a silent jump;
 *  - an explicit address beats what the browser remembers, every time;
 *  - a saved reply target that is no longer in its thread does not become a
 *    silent reply to something else;
 *  - a link inside the reading keeps the origin and the Page; a link leaving
 *    it does not carry the suffix out;
 *  - the reader draws ONE reading column, ONE stream and ONE dock, and draws
 *    them with no bookmark provider above it at all -- which is memory-only,
 *    not a fresh arrival to be recorded over.
 *
 * F21: a .mjs suite, deliberately not in the typechecked test project.
 * Reload, a fresh browser context, the late restore and the reply actually
 * submitted are `tests/test_quiet_r5_reading_browser.py`'s.
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

const { createElement } = await import('react')
const { renderToStaticMarkup } = await import('react-dom/server')
const { anchorIn, anchorDelta, resumeReading, validReplyTarget, SCROLL_KEYS,
  readingKey, threadKey, placesIn, noPlaces, knownPage } =
  await import('../src/quiet/reader/scroll.ts')
const { QuietNavigationProvider, useQuietHref } = await import('../src/quiet/reader/navigation.tsx')
const { href } = await import('../src/quiet/model.ts')
const Post = (await import('../src/quiet/post/Post.tsx')).default
const ParentHeader = (await import('../src/quiet/post/ParentHeader.tsx')).default
const ConversationReader = (await import('../src/quiet/reader/ConversationReader.tsx')).default

/* -- a reading, as it is drawn --------------------------------------------- */

/** Posts of equal height, laid out from `first` down. */
const drawn = (ids, first, height = 100, gap = 20) =>
  ids.map((id, i) => ({ id, top: first + i * (height + gap), bottom: first + i * (height + gap) + height }))

const frame = (posts, over = {}) =>
  ({ top: 0, bottom: 800, blocked: 0, posts, ...over })

/* -- 1. which post the reader was looking at ------------------------------- */

test('the anchor names the first post the reader could actually see', () => {
  /* a is scrolled off the top, b straddles the edge, c is below it */
  const posts = [
    { id: 'a', top: -240, bottom: -140 },
    { id: 'b', top: -40, bottom: 60 },
    { id: 'c', top: 80, bottom: 180 },
  ]
  assert.deepEqual(anchorIn(frame(posts)), { post: 'b', offset: -40 })
})

test('a post behind a thread\'s pinned parent header is not in view', () => {
  const posts = [
    { id: 'root', top: 10, bottom: 70 },
    { id: 'reply', top: 90, bottom: 190 },
  ]
  /* with nothing stuck, the root is what is seen */
  assert.deepEqual(anchorIn(frame(posts)), { post: 'root', offset: 10 })
  /* with an 80px parent header stuck at the top, it is not */
  assert.deepEqual(anchorIn(frame(posts, { blocked: 80 })), { post: 'reply', offset: 90 })
})

test('the offset is measured from the pinned header, not from the covered edge', () => {
  const posts = [{ id: 'a', top: 140, bottom: 240 }]
  /* an 80px pinned header and a 60px box stuck under it: the post's offset is
     its distance from the HEADER, which is what does not move while reading */
  assert.deepEqual(anchorIn(frame(posts, { top: 80, blocked: 60 })), { post: 'a', offset: 60 })
})

test('a reading scrolled past its end still names a post that is drawn', () => {
  const posts = drawn(['a', 'b'], -900)
  const got = anchorIn(frame(posts))
  assert.equal(got.post, 'b', 'the last post above the fold, not null')
})

test('no post drawn is not a reading, and is not remembered as one', () => {
  assert.equal(anchorIn(frame([])), null)
})

/* -- 2. putting it back, against what is drawn now ------------------------- */

test('an unchanged reading needs no scrolling at all', () => {
  const posts = drawn(['a', 'b', 'c'], -100)
  const anchor = anchorIn(frame(posts))
  assert.equal(anchorDelta(frame(posts), anchor), 0)
})

test('heights that changed in between are answered, not guessed', () => {
  /* captured when b sat 60px below the top */
  const anchor = { post: 'b', offset: 60 }
  /* drawn again with every post 80px taller and pushed down: b is now 300 down */
  const taller = drawn(['a', 'b', 'c'], 100, 180)
  assert.equal(anchorDelta(frame(taller), anchor), 300 - 60, 'scroll down to put it back')
  /* and shorter, where b happens to land exactly where it was asked for */
  const shorter = drawn(['a', 'b', 'c'], 0, 40)
  assert.equal(anchorDelta(frame(shorter), anchor), 0, 'already there, so nothing moves')
  /* shorter still, which is a scroll UP */
  const shortest = drawn(['a', 'b', 'c'], 0, 20)
  assert.equal(anchorDelta(frame(shortest), anchor), 40 - 60)
})

test('a post that is not drawn answers no, rather than jumping somewhere else', () => {
  const posts = drawn(['a', 'c'], 0)
  assert.equal(anchorDelta(frame(posts), { post: 'b', offset: 40 }), null,
    'a filtered-out, unloaded or deleted anchor is not silently replaced')
  assert.equal(anchorDelta(frame(posts), null), null)
})

test('a captured anchor round-trips to the same offset through a reflow', () => {
  const before = drawn(['a', 'b', 'c', 'd'], -250)
  const anchor = anchorIn(frame(before))
  /* the same posts, 40px taller each and pushed down by a margin opening */
  const after = drawn(['a', 'b', 'c', 'd'], -120, 140)
  const delta = anchorDelta(frame(after), anchor)
  const moved = after.map((p) => ({ ...p, top: p.top - delta, bottom: p.bottom - delta }))
  const put = moved.find((p) => p.id === anchor.post)
  assert.ok(Math.abs(put.top - anchor.offset) < 0.01,
    `the post is back at its offset: ${put.top} vs ${anchor.offset}`)
})

/* -- 3. which reading an arrival shows ------------------------------------- */

const savedReading = {
  flow: { topic: 't-1', batch: { before: 42 }, anchor: { post: 'p-9', offset: -17.5 } },
  thread: { root: 'p-1', target: 'p-4', replyTo: 'p-7', anchor: { post: 'p-6', offset: 24 } },
  margin: { reading: 'carried', searchOpen: true, query: 'ink', scrollByReading: { carried: 120 } },
}

test('an explicit address wins over everything the browser remembers', () => {
  const got = resumeReading({ topic: 't-2', turn: null }, savedReading, true)
  assert.deepEqual(got, {
    topic: 't-2', turn: null, batch: {}, flowAnchor: null, threadAnchor: null,
    replyTo: null, from: 'address',
  })
})

test('a bare resume entry shows the topic, the batch, the thread and the reply target', () => {
  const got = resumeReading({ topic: null, turn: null }, savedReading, false)
  assert.equal(got.from, 'bookmark')
  assert.equal(got.topic, 't-1')
  assert.equal(got.turn, 'p-4', 'the post that was being read in the thread')
  assert.deepEqual(got.batch, { before: 42 })
  assert.deepEqual(got.flowAnchor, { post: 'p-9', offset: -17.5 })
  assert.deepEqual(got.threadAnchor, { post: 'p-6', offset: 24 })
  assert.equal(got.replyTo, 'p-7', 'and the post the composer was answering, which is not p-4')
})

test('nothing remembered is the address, unchanged', () => {
  const got = resumeReading({ topic: 't-3', turn: 'p-2' }, null, false)
  assert.equal(got.from, 'address')
  assert.equal(got.topic, 't-3')
  assert.equal(got.turn, 'p-2')
  assert.deepEqual(got.batch, {})
})

test('a saved flow with no thread resumes no thread', () => {
  const got = resumeReading({ topic: null, turn: null },
    { ...savedReading, thread: null }, false)
  assert.equal(got.turn, null)
  assert.equal(got.replyTo, null)
  assert.equal(got.threadAnchor, null)
})

/* -- 4. the post a restored composer answers ------------------------------ */

const rows = [{ id: 'p-1' }, { id: 'p-4' }, { id: 'p-7' }]

test('a saved reply target still in the thread is kept, and is not the post being read', () => {
  assert.deepEqual(validReplyTarget(rows, 'p-7', 'p-4'), { reply: 'p-7', lost: false })
})

test('a saved reply target that is gone falls back to the post being read, and says so', () => {
  assert.deepEqual(validReplyTarget(rows, 'p-99', 'p-4'), { reply: 'p-4', lost: true },
    'an invalid target never becomes a silent reply to something else')
})

test('nothing saved, or the same post, is the post being read with nothing to say', () => {
  assert.deepEqual(validReplyTarget(rows, null, 'p-4'), { reply: 'p-4', lost: false })
  assert.deepEqual(validReplyTarget(rows, 'p-4', 'p-4'), { reply: 'p-4', lost: false })
})

test('the keys a reader scrolls with are the ones that take control', () => {
  for (const key of ['ArrowDown', 'PageUp', 'Home', 'End', ' '])
    assert.ok(SCROLL_KEYS.has(key), `${key} is taking control`)
  assert.ok(!SCROLL_KEYS.has('a'), 'typing a letter is not')
})

/* -- 4b. a place is a place IN a reading, the Page included (finding 5) --- */

const aReading = (page) => ({ page, conversation: 'ent-c', topic: 't-1', revision: 0, batch: {} })

test('the Page is part of which reading a place is a place in', () => {
  const a = readingKey(aReading('this-post'))
  const b = readingKey(aReading('page-2'))
  assert.notEqual(a, b,
    'the same conversation, the same topic and the same half of it -- and still two readings')
  assert.equal(readingKey(aReading('this-post')), a, 'while the same Page is the same reading')
  assert.notEqual(a, readingKey({ ...aReading('this-post'), batch: { before: 42 } }),
    'and paging is a reading of its own, as it already was')
})

test('switching Page never writes page A\'s anchor under page B', () => {
  const [a, b] = [readingKey(aReading('this-post')), readingKey(aReading('page-2'))]
  const noThread = threadKey(null)
  /* the place measured while page A was the one being read */
  const held = { ...placesIn(noPlaces(), a, noThread), flow: { post: 'p-9', offset: -17.5 } }
  /* page B is activated. It has no place of its own yet, and A's is not its to
     inherit: what gets written down for B carries no anchor at all. */
  assert.equal(placesIn(held, b, noThread).flow, null,
    'page A\'s offset is not page B\'s place')
  /* and A's own place is still A's when the reader comes back to it */
  assert.deepEqual(placesIn(held, a, noThread).flow, { post: 'p-9', offset: -17.5 })
})

test('a thread\'s place is a place in that thread, on that Page', () => {
  const on = (page) => threadKey({ page, conversation: 'ent-c', root: 'p-1', target: 'p-4' })
  assert.notEqual(on('this-post'), on('page-2'))
  const held = { ...placesIn(noPlaces(), 'r', on('this-post')), thread: { post: 'p-6', offset: 24 } }
  assert.equal(placesIn(held, 'r', on('page-2')).thread, null)
  assert.deepEqual(placesIn(held, 'r', on('this-post')).thread, { post: 'p-6', offset: 24 },
    'and the flow underneath is untouched either way')
  assert.equal(threadKey(null), '', 'no thread open has no place of its own to keep')
})

/* -- 4c. is the addressed Page one this browser has? (finding 4) ---------- */

const sequence = [{ id: 'this-post' }, { id: 'page-2' }]

test('a Page the runtime has not read yet is UNDECIDED, not missing', () => {
  assert.equal(knownPage('page-2', [], false), null,
    'no Holder has been entered, so an empty sequence is no answer at all')
  assert.equal(knownPage('page-9', [], false), null)
  assert.equal(knownPage('page-2', sequence, false), null,
    'and a sequence read before the runtime is ready is still not the answer')
})

test('once the Pages are hydrated the question is answered', () => {
  assert.equal(knownPage('page-2', sequence, true), true)
  assert.equal(knownPage('page-9', sequence, true), false,
    'and only THEN is it a Page this browser does not have')
})

test('the Conversation Page is known before anything hydrates', () => {
  assert.equal(knownPage('this-post', [], false), true,
    "its id is the Holder's own first Page, and it is there before any of this")
})

/* -- 5. where a link inside the reading points (F6) ----------------------- */

function Link({ to }) {
  const quiet = useQuietHref()
  return createElement('a', { href: quiet(to, null, 'turn-1') }, 'x')
}

const hrefOf = (markup) => markup.match(/href="([^"]*)"/)[1].replace(/&amp;/g, '&')

test('a link inside the effective conversation keeps the origin and the Page', () => {
  const markup = renderToStaticMarkup(createElement(QuietNavigationProvider, {
    originConversation: 'ent-origin', effectiveConversation: 'ent-child', page: 'page-2',
  }, createElement(Link, { to: 'ent-child' })))
  assert.equal(hrefOf(markup), '#/c/ent-origin/turn/turn-1/qpage/page-2')
})

test('a link leaving it does not carry the suffix out', () => {
  const markup = renderToStaticMarkup(createElement(QuietNavigationProvider, {
    originConversation: 'ent-origin', effectiveConversation: 'ent-child', page: 'page-2',
  }, createElement(Link, { to: 'ent-elsewhere' })))
  assert.equal(hrefOf(markup), href('ent-elsewhere', null, 'turn-1'))
  assert.ok(!hrefOf(markup).includes('qpage'))
})

test('with no Quiet navigation above it, a link is model.href exactly', () => {
  const markup = renderToStaticMarkup(createElement(Link, { to: 'ent-anywhere' }))
  assert.equal(hrefOf(markup), href('ent-anywhere', null, 'turn-1'))
})

test('the Conversation Page is omitted from the address, so old links still read', () => {
  const markup = renderToStaticMarkup(createElement(QuietNavigationProvider, {
    originConversation: 'ent-origin', effectiveConversation: 'ent-origin', page: 'this-post',
  }, createElement(Link, { to: 'ent-origin' })))
  assert.equal(hrefOf(markup), '#/c/ent-origin/turn/turn-1')
})

/* -- 6. a post's action slot, with its own drawn body (F5) ---------------- */

const aPost = (id, number) => ({
  id, number, author: 'ent-who', author_alias: '@brian', at: 1700000000,
  parts: [{ kind: 'text', text: 'A post.' }], topics: [], answering: null,
})

test('a post hands its action slot a live accessor for its own body', () => {
  let given = null
  const markup = renderToStaticMarkup(createElement(Post, {
    turn: aPost('p-1', 1), conversation: 'ent-c', topic: null, topics: [],
    action: (body) => { given = body; return createElement('span', null, 'Deep dive') },
  }))
  assert.equal(typeof given, 'function', 'the slot is given a function, not an element')
  assert.equal(given(), null, 'and it answers for the element, which SSR never drew')
  assert.ok(markup.includes('<span>Deep dive</span>'))
  assert.ok(markup.indexOf('<span>Deep dive</span>') > markup.indexOf('qc-post-reply'),
    'the slot is in the footer, after Reply')
})

test('a post with no action slot draws exactly what it drew before', () => {
  const props = { turn: aPost('p-1', 1), conversation: 'ent-c', topic: null, topics: [] }
  const without = renderToStaticMarkup(createElement(Post, props))
  const nulled = renderToStaticMarkup(createElement(Post, { ...props, action: () => null }))
  assert.equal(without, nulled, 'a placeholder action adds nothing at all')
  assert.ok(!without.includes('Deep dive'))
})

test('the parent header links through the same helper', () => {
  const markup = renderToStaticMarkup(createElement(QuietNavigationProvider, {
    originConversation: 'ent-origin', effectiveConversation: 'ent-origin', page: 'page-3',
  }, createElement(ParentHeader, { turn: aPost('p-root', 1), conversation: 'ent-origin', topic: 't-1' })))
  assert.ok(markup.includes('#/c/ent-origin/t/t-1/turn/p-root/qpage/page-3'),
    'the pinned parent post stays on the Page the thread is read on')
})

/* -- 7. one reading column, one stream, one dock -------------------------- */

const once = (markup, what) => markup.split(what).length - 1

test('the reader draws one reading column, one stream and one dock', () => {
  const markup = renderToStaticMarkup(createElement(ConversationReader, {
    conversation: 'ent-c', originConversation: 'ent-c', page: 'this-post',
    topic: null, turn: null, me: 'ent-who', topics: [],
    facts: { data: null, loading: true, error: null, reload: () => {} },
    missingTopic: false,
    resume: { topic: null, turn: null, batch: {}, flowAnchor: null, threadAnchor: null, replyTo: null, from: 'address' }, decided: true,
    notify: () => {}, report: () => {}, onReadingPost: () => {},
  }))
  assert.equal(once(markup, 'id="qc-reading"'), 1)
  assert.equal(once(markup, 'id="qc-stream"'), 1)
  assert.equal(once(markup, 'qc-dock'), 1)
  assert.ok(!markup.includes('qc-compose'), 'and no composer until a page says what it is for')
})

test('with no bookmark provider above it the reader still draws, memory-only', () => {
  /* `useWorkspaceBookmark()` answers null when nothing named an identity and
     no provider is mounted. That is honest -- it is NOT an empty envelope that
     would look like a fresh arrival -- so the reader must neither restore from
     it nor record over it, and must certainly not throw. */
  const markup = renderToStaticMarkup(createElement(ConversationReader, {
    conversation: 'ent-c', originConversation: 'ent-c', page: 'this-post',
    topic: 't-1', turn: null, me: null, topics: [],
    facts: { data: null, loading: false, error: 'nothing read', reload: () => {} },
    missingTopic: false,
    resume: { topic: 't-1', turn: null, batch: {}, flowAnchor: null, threadAnchor: null, replyTo: null, from: 'address' }, decided: true,
    notify: () => {}, report: () => {}, onReadingPost: () => {},
  }))
  assert.ok(markup.includes('nothing read'), 'the failure is still reported')
  assert.equal(once(markup, 'id="qc-stream"'), 1)
})
