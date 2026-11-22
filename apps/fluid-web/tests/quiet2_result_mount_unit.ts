/* THE INDEPENDENT REVIEWS' FALSIFIERS, AGAINST THE REAL COMPOSITION
 * (adm-263df1ccb512: B1/F04, B3/F09, B4/F10, F12-F16, F19;
 *  adm-d84456fd4c3c: B4.1 fail-closed fresh read and delayed completion,
 *  B4.2 the host's own entry tracking, B4.3 the guarded maximised close,
 *  B4.4 resuming a saved result, N3 the ordinary viewer's close).
 *
 * The re-review extracted the hand-off's TSX declarations from a Markdown file
 * and executed them against synthetic dependencies: ten of its twenty-three
 * cases failed. Nine were the adapters themselves; the tenth was a reader they
 * named which does not exist anywhere in this source.
 *
 * EVERY CASE HERE RUNS THE CODE THE INTEGRATOR NOW CALLS
 * (`src/quiet2/results/mount.ts`), against:
 *   - the REAL viewer store (`viewer/viewers.ts`): the viewers opened, moved,
 *     parked and closed below are that store's, not a stand-in;
 *   - the REAL decisions (`results/history.ts`, `results/launch.ts`,
 *     `results/hostOpen.ts`) and the real `openResultTarget`;
 *   - the REAL fresh read (`results/refRead.ts`), over an injected `fetch`, so
 *     the route, its answer shape and its failures are this build's.
 *
 * WHAT IS SYNTHETIC is only what a page supplies -- its React state, as
 * `ResultPage`. There is no DOM, no Brain, no server, no byte and no
 * rendering, and none is claimed. The REAL history hook is composed in
 * `quiet2_result_history_unit.ts` beside this file, which is where the three
 * findings about the host's own history live.
 *
 * THE GUARD IS REAL HERE TOO. `makePage` holds one unsaved-work question open
 * exactly as `Quiet2.tsx`'s `guarded`/`setLeave` does, so what is measured is
 * the ASYNCHRONOUS and BLOCKED paths -- a pending question, Stay, a thread read
 * that fails, a column chosen after the press -- and not a synchronous stub
 * that cannot be wrong.
 *
 * AND EVERY ARTIFACT OPEN IS NOW ASYNCHRONOUS, because every artifact open
 * reads the artifact's own description first (B4.1). `press` below makes the
 * press and then lets that read answer; a case that asserts on the press alone
 * is asserting about something that has deliberately not happened yet. */
import assert from 'node:assert/strict'
import { mountResults, placedResults, resetPlacedResults, type ColumnChoice, type ResultPage } from '../src/quiet2/results/mount'
import { ANOTHER_THING, COULD_NOT_CHECK, artifactNow, type FreshArtifact } from '../src/quiet2/results/refRead'
import { BRAIN_MOVED, BRAIN_UNCONFIRMED, beginOpening, clearLaunches, holdLaunch, launchOf, type LaunchContext, type LaunchPlace } from '../src/quiet2/results/launch'
import { resultIntent } from '../src/quiet2/results/history'
import { closeSteps, type PlaceStep } from '../src/quiet2/results/hostOpen'
import { destinationOfRef, type ResolvedRef, type ResultDestination } from '../src/quiet2/results/targets'
import { leaves, openResultTarget, type MayMove, type Navigation, type Opened } from '../src/quiet2/results/opener'
import type { CentreAt } from '../src/quiet2/address'
import { heldItem } from '../src/quiet2/brain/logic'
import { closeViewer, maximised, moveViewer, openViewer, viewerOf } from '../src/quiet2/viewer/viewers'

let checks = 0
const eq = (a: unknown, b: unknown, what: string) => { assert.deepEqual(a, b, what); checks++ }
const ok = (a: unknown, what: string) => { assert.ok(a, what); checks++ }
const no = (a: unknown, what: string) => { assert.ok(!a, what); checks++ }

const BRAIN = 'fixture-corpus@instance-1'
const A = 'adm-111111111111'
const B = 'adm-222222222222'
const HERE: LaunchPlace = { conversation: 'ent-origin', centre: null }
const SAVED: LaunchPlace = { conversation: 'ent-saved', centre: null }
const ASK = 'opr-question1234'
const SOURCE = { conversation: 'ent-source', post: 'ent-post' }

const HELD = { state: 'held', name: 'review.txt', size: 20, claimed_media_type: 'text/plain' }
/** the bytes as the page's own reader gives them (`brain/logic.ts`) */
const bytes = (id = A) => heldItem(id, HELD)!
const fileRef = (id = A, over: Partial<ResolvedRef> = {}): ResolvedRef => ({
  id, type: 'file', state: 'ok', available: true, opens: 'file', file: { ...HELD }, ...over,
})
const dest = (id = A): ResultDestination => destinationOfRef(fileRef(id))
/** the same file, as it is reached FROM A POST: source and result differ */
const fromPost = (id = A): ResultDestination => destinationOfRef(fileRef(id, { conversation: SOURCE.conversation, post: SOURCE.post }))
const postDest = (): ResultDestination => ({ ...dest(), ref: SOURCE.post, target: { kind: 'post', ...SOURCE }, opens: 'post' })
const recordDest = (): ResultDestination => ({ ...dest(), ref: 'ent-record12345', target: { kind: 'record', ref: 'ent-record12345' }, opens: 'record' })
const convDest = (): ResultDestination => ({ ...dest(), ref: 'ent-conversatn1', target: { kind: 'record', ref: 'ent-conversatn1' }, opens: 'conversation' })

const launch = (place: LaunchPlace = HERE, decision: LaunchContext['decision'] = null): LaunchContext => holdLaunch({
  opening: beginOpening(), brainKey: BRAIN, place, thread: null,
  reading: { scroll: 417, offset: 12 }, reply: 'ent-reply12345', draft: 'conversation:ent-origin',
  focus: { control: 'needs-ref:' + A, fallback: { kind: 'conversation' } }, decision,
})
const asking = (): LaunchContext['decision'] => ({ form: null, question: ASK, item: 'item-1', ref: A, role: null })

/** the server answering that the exact reference asked for is held now */
const stillHeld = async (ref: string): Promise<FreshArtifact> =>
  ({ how: 'held', file: { ...HELD, ref, treatment: { view: 'text' } } })

/** WHICH BRAIN THE SERVER SERVES, as the module store `mount.ts` really reads
 *  answers (`results/serving.ts`, over `brainBinding.ts`). It is injected here
 *  for the same reason the fresh read is: a check supplies its own, and it is
 *  deliberately NOT a page member any more -- a render's own closure answering
 *  for a page that has been rebound since is re-review adm-af5263a65134's F1.
 *  `serving.ts` itself is checked against the real binding in
 *  `quiet2_result_serving_unit.ts`. */
let served: string | null = BRAIN
const serving = () => served

/** viewers this suite opened by hand, so the real store starts each case clean */
const byHand: string[] = []
function fresh() {
  served = BRAIN
  for (const row of placedResults().all()) closeViewer(row.viewer)
  for (const id of byHand.splice(0)) closeViewer(id)
  const max = maximised()
  if (max) closeViewer(max.id)
  clearLaunches()
  resetPlacedResults()
}

/* -- a page, as a shared host supplies one ---------------------------------- */

interface Seen {
  centre: CentreAt[]; replaced: (CentreAt | null)[]; back: LaunchPlace[]; tracked: CentreAt[]
  picked: string[]; posts: string[]; said: string[]; focused: unknown[]; revealed: string[]
  putBack: PlaceStep[]; returns: LaunchContext[]; leftOn: LaunchPlace[]; read: string[]
}

function makePage(over: Partial<ResultPage> & { asks?: () => boolean } = {}) {
  const r: Seen = {
    centre: [], replaced: [], back: [], tracked: [], picked: [], posts: [], said: [],
    focused: [], revealed: [], putBack: [], returns: [], leftOn: [], read: [],
  }
  let pending: { go: () => void; stay: () => void } | null = null
  let conversation = HERE.conversation!
  let at: CentreAt = null
  let choice: ColumnChoice | null = null
  const asks = over.asks ?? (() => false)
  /** exactly `Quiet2.tsx`'s `guarded(go, place, stay)`: asking is not arriving */
  const guarded = (go: () => void, stay?: () => void) => {
    if (asks()) { pending = { go, stay: stay ?? (() => {}) }; return }
    go()
  }
  const page: ResultPage = {
    /* the GRAPH key, for the viewer's source only (F2) */
    spaceKey: () => BRAIN,
    serving,
    refNow: async (path) => {
      const ref = new URL(path, 'https://fixture.invalid').searchParams.get('ref')!
      const opens = ref === SOURCE.post ? 'post' : ref === 'ent-conversatn1' ? 'conversation' : 'record'
      return { brain: { corpus_id: 'fixture-corpus', instance: 'instance-1' },
        inspection: { id: ref, state: 'ok', available: true, why: null, opens,
          ...(opens === 'post' ? SOURCE : opens === 'conversation' ? { conversation: ref } : {}) } }
    },
    origin: () => 'https://fixture.invalid',
    conversation: () => conversation,
    centreAt: () => at,
    /* the baseline's own `centreAt.current = to`, which `applyCentre` calls */
    enterCentre: (to) => { at = to; r.tracked.push(to) },
    columns: () => [],
    freeColumn: () => null,
    choose: (ask) => { choice = ask },
    invoker: () => null,
    hasControl: () => false,
    focus: (c, invoker) => { r.focused.push({ choice: c, invoker }) },
    centreGo: (to) => { at = to; r.centre.push(to) },
    centreReplace: (to) => { at = to; r.replaced.push(to) },
    /* the guarded `backTo`, with all three of the guard's ends (B4.3) -- AND
       ASKING BEFORE IT WALKS (F7), exactly as the documented host does: the
       answer's yes or no is all this route reads, because what runs after the
       move is `then`. */
    backTo: (place, then, stay, begin) => {
      r.back.push(place)
      guarded(() => {
        if (begin && !begin()) return
        conversation = place.conversation ?? conversation; at = place.centre; then()
      }, stay)
    },
    /* THE MOVE ASKS BEFORE IT MOVES (F4): exactly the documented wiring --
       `begin()` inside the guard, the reference and the report from its
       answer, and nothing moved at all where it answers null. */
    pickConversation: (k, begin, stay) => {
      r.picked.push(k)
      guarded(() => { const go = begin(); if (!go) return; conversation = go.ref; go.moved() }, stay)
      return true
    },
    openPost: (c, p, done, begin) => {
      r.posts.push(`${c}/${p}`)
      guarded(() => { const go = begin(); if (!go) return; conversation = go.ref; done('completed') }, () => done({ how: 'cancelled' }))
    },
    record: (begin, stay) => {
      guarded(() => { const go = begin(); if (!go) return; r.picked.push(`record:${go.ref}`); go.moved() }, stay)
    },
    goToPost: (c, p) => { r.posts.push(`source:${c}/${p}`) },
    reveal: (post) => { r.revealed.push(post) },
    heldItem: (ref, about) => heldItem(ref, about),
    /* the fresh read, answering that what was asked for is still held */
    artifactNow: (ref) => { r.read.push(ref); return stillHeld(ref) },
    putBack: (s) => { r.putBack.push(s) },
    offerReturn: (l) => { r.returns.push(l) },
    leaveOn: (p) => { r.leftOn.push(p) },
    say: (w) => { r.said.push(w) },
    ...over,
  }
  return {
    page, r,
    answer: (how: 'go' | 'stay') => { const q = pending!; pending = null; q[how]() },
    waiting: () => !!pending,
    chooser: () => choice,
    conversationNow: () => conversation,
    atNow: () => at,
  }
}

const settle = () => new Promise<void>((done) => { setImmediate(() => setImmediate(done)) })

/* ========================================================================== *
 * B4.1 -- THE FRESH READ IS MANDATORY, AND FAILS CLOSED
 * ========================================================================== */
{
  /* the three launch surfaces the re-review pressed: a chooser, a Brain
     record and the Latest list all press with NO request behind them, and
     each one used to open the old descriptor without reading anything */
  for (const surface of ['chooser', 'Brain record', 'Latest']) {
    fresh()
    const settled: Opened[] = []
    const host = makePage({ artifactNow: async () => ({ how: 'gone', availability: 'purged', why: 'Its contents were purged from this Brain.' }) })
    const m = mountResults(host.page)
    /* no decision: nothing to "read by", which is what used to make it unchecked */
    const press = m.openResult(dest(A), launch(HERE, null), (o) => settled.push(o))
    eq(press, { what: 'leaving', how: 'file' }, `B4.1: a ${surface} press is READ FIRST, and has not opened anything yet`)
    await settle()
    eq(settled.map((o) => o.what), ['unavailable'], `B4.1: and a purged result is UNAVAILABLE however it was pressed (${surface})`)
    no(maximised(), 'B4.1: nothing is placed from the descriptor the row was drawn with')
    eq(host.r.centre, [], 'and no history entry is owed')
  }
}
{
  /* a refusal, a failure and an answer about something else are not licence
     to reuse what is in hand: each is the SAME refusal to open */
  const failures: [string, () => Promise<FreshArtifact>][] = [
    ['401 refused', async () => ({ how: 'gone', availability: 'unreadable', why: COULD_NOT_CHECK })],
    ['the fresh answer no longer names it', async () => ({ how: 'gone', availability: 'unreadable', why: ANOTHER_THING })],
    ['offline', () => Promise.reject(new Error('offline'))],
  ]
  for (const [what, read] of failures) {
    fresh()
    const settled: Opened[] = []
    const host = makePage({ artifactNow: read })
    const m = mountResults(host.page)
    m.openResult(dest(A), launch(HERE, asking()), (o) => settled.push(o))
    await settle()
    eq(settled.map((o) => o.what), ['unavailable'], `B4.1: ${what} OPENS NOTHING -- absence is not authority to reuse the old descriptor`)
    no(maximised(), 'and no viewer is placed')
    no(settled.some(leaves), 'so the reader never left, and a draft is never discarded for it')
  }
}
{
  /* THE OPEN IS THE MODULE'S BUSINESS; `settled` IS ONLY THE REPORT (B4.1).
     The read callback used to return at once unless an observer had been
     registered, so `openResult(d, launch)` with the real asynchronous reader
     placed nothing at all. */
  fresh()
  const host = makePage()
  const m = mountResults(host.page)
  const press = m.openResult(dest(A), launch())
  eq(press, { what: 'leaving', how: 'file' }, 'B4.1: the press is being read again')
  await settle()
  ok(maximised(), 'B4.1: AND THE OPEN COMPLETES WITHOUT ANY NOTIFICATION CALLBACK')
  eq(host.r.centre.length, 1, 'with the one history entry it owes')
}
{
  /* what the read actually read replaces the descriptor; what it knows
     nothing about is carried through untouched (the route strips `source`) */
  fresh()
  const host = makePage({
    artifactNow: async (ref) => ({ how: 'held', file: { ref, state: 'held', name: 'fresh.md', size: 41, claimed_media_type: 'text/plain', treatment: { view: 'markdown' } } }),
  })
  const m = mountResults(host.page)
  m.openResult(fromPost(A), launch())
  await settle()
  const shown = maximised()
  eq(shown?.content.kind === 'file' && shown.content.item.treatment, 'markdown',
    'B4.1: the VERIFIED word from the fresh description is what the renderer is chosen by')
  eq(shown?.content.kind === 'file' && shown.content.item.url, `/api/artifacts/${A}`, 'at the exact reference asked for')
  eq(shown?.source, { kind: 'post', ...SOURCE }, 'B4.1: AND THE SOURCE THE RECORD STATED SURVIVES the description that strips it')
}
{
  /* the reader itself, against the route this build really serves */
  const asked: string[] = []
  const answering = (body: unknown, init: { ok?: boolean } = {}) => (async (url: unknown) => {
    asked.push(String(url))
    return { ok: init.ok ?? true, json: async () => body } as unknown as Response
  }) as typeof fetch
  const held = await artifactNow(A, answering({ ref: A, state: 'held', name: 'r.txt', size: 9, claimed_media_type: 'text/plain', treatment: { view: 'text' } }) as never)
  eq(asked, [`/api/artifacts/${A}?describe=1`], 'B4.1: it reads the artifact route that exists, at the exact reference')
  eq(held.how === 'held' && held.file.treatment, { view: 'text' }, 'and takes the server’s own verified word')
  eq((await artifactNow(A, answering({ ref: A, state: 'purged' }) as never)).how, 'gone', 'B4.1: `?describe=1` ANSWERS 200 FOR A PURGED REF, so the STATE is the check')
  eq((await artifactNow(A, answering({ ref: A, state: 'unknown' }) as never)).how, 'gone', 'an unknown reference is gone')
  eq((await artifactNow(A, answering({ ref: A, state: 'held-but-corrupt' }) as never)).how, 'gone', 'and so are bytes that do not read as what was stored')
  const other = await artifactNow(A, answering({ ref: B, state: 'held' }) as never)
  eq([other.how, other.how === 'gone' && other.why], ['gone', ANOTHER_THING], 'B4.1: a description of ANOTHER reference is not this press’s answer')
  /* N5 (re-review adm-efb406a34e7a): AND ONE THAT NAMES NO REFERENCE AT ALL.
     The route answers `ref` on every state it answers, so a held body without
     one does not identify these bytes -- and "it did not say" was being read
     as authority to open the descriptor in hand. */
  for (const unidentified of [
    { state: 'held', name: 'unidentified.txt', treatment: { view: 'text' } },
    { ref: null, state: 'held', name: 'unidentified.txt' },
    { ref: 17, state: 'held', name: 'unidentified.txt' },
  ]) {
    const nameless = await artifactNow(A, answering(unidentified) as never)
    eq([nameless.how, nameless.how === 'gone' && nameless.why], ['gone', ANOTHER_THING],
      `N5: a held description that does not say which reference it is about opens nothing (${JSON.stringify(unidentified.ref ?? null)})`)
  }
  const refused = await artifactNow(A, answering({ error: 'a worker grant authorises /api/worker and nothing else' }, { ok: false }) as never)
  eq([refused.how, refused.how === 'gone' && refused.why], ['gone', 'a worker grant authorises /api/worker and nothing else'],
    'B4.1: AN HTTP REFUSAL IS A REFUSAL, in the server’s own words')
  eq((await artifactNow(A, (() => { throw new Error('offline') }) as never)).how, 'gone', 'and an unreachable server opens nothing')
  eq((await artifactNow('', answering({}) as never)).how, 'gone', 'a press with no reference reads nothing and opens nothing')
}

/* ========================================================================== *
 * B1 / F04 -- a read that answers about another identity is refused, on BOTH
 * branches. The fresh reader cannot produce that mismatch any more (it checks
 * the ref itself, above), so the opener's own guard is checked where it is.
 * ========================================================================== */
for (const delayed of [false, true]) {
  fresh()
  let answer: ((r: { how: 'fresh'; destination: ResultDestination }) => void) | null = null
  let opened = 0
  const settled: Opened[] = []
  const l = launch()
  const press = openResultTarget(dest(A), l, {
    brainKey: BRAIN,
    origin: null,
    file: () => { opened++; return 'max' },
    read: (_d, cb) => {
      answer = cb
      return delayed ? { how: 'reading' } : { how: 'fresh', destination: dest(B) }
    },
  }, { settled: (o) => settled.push(o) })
  if (delayed) {
    answer!({ how: 'fresh', destination: dest(B) })
    eq(settled.map((o) => o.what), ['refused'], 'F04: A DELAYED READ ABOUT ANOTHER IDENTITY OPENS NOTHING (B1)')
    eq(settled[0] && 'why' in settled[0] ? settled[0].why : null,
      'That read answered about something else, so nothing was opened.', 'in the same words as the synchronous branch')
  } else {
    eq(press.what, 'refused', 'F04: and the synchronous branch refuses it too')
  }
  eq(opened, 0, 'F04: no file is opened either way')
}
{
  /* a read answering about the thing that was asked for still opens it: the
     guard is an identity check, not a refusal of delayed reads */
  fresh()
  const settled: Opened[] = []
  const host = makePage()
  const m = mountResults(host.page)
  m.openResult(dest(A), launch(HERE, asking()), (o) => settled.push(o))
  await settle()
  eq(settled.map((o) => o.what), ['opened'], 'a fresh read about the thing that was asked for opens it')
  eq(maximised()?.content.kind, 'file', 'in the page’s own viewer')
}

/* ========================================================================== *
 * B3 / F09 -- the record route must wait for the guard it really has
 * ========================================================================== */
{
  fresh()
  const settled: Opened[] = []
  const host = makePage({ asks: () => true })
  const m = mountResults(host.page)
  const r = m.openResult(recordDest(), launch(), (o) => settled.push(o))
  eq(r, { what: 'leaving', how: 'record' }, 'F09: A PENDING UNSAVED-WORK QUESTION IS NOT AN ARRIVAL (B3)')
  no(leaves(r), 'the reader has not left')
  eq(m.dockStep(r), 'wait', 'so the dock keeps the row, the form and the draft, and arms nothing')
  eq(settled, [], 'and nothing is reported while the question is open')
  await settle()
  ok(host.waiting(), 'the question is on screen')
  host.answer('stay')
  eq(settled.map((o) => o.what), ['cancelled'], 'Stay is a cancellation, and the record page is never entered')
  eq(m.dockStep(settled[0]), 'keep', 'so the dock still arms nothing')
  no(settled.some(leaves), 'nothing was left')
}
{
  fresh()
  const settled: Opened[] = []
  const host = makePage({ asks: () => true })
  const m = mountResults(host.page)
  m.openResult(recordDest(), launch(), (o) => settled.push(o))
  await settle()
  host.answer('go')
  eq(settled.map((o) => o.what), ['opened'], 'F09: and the arrival is reported when the reader actually arrives')
  eq(m.dockStep(settled[0]), 'arm', 'which is when the way back is owed')
}
{
  /* a page with nothing unfinished moves once the fresh read answers */
  fresh()
  const host = makePage()
  const m = mountResults(host.page)
  const settled: Opened[] = []
  const r = m.openResult(recordDest(), launch(), (o) => settled.push(o))
  eq(r, { what: 'leaving', how: 'record' }, 'the direct record is read first')
  await settle()
  eq(settled, [{ what: 'opened', how: 'record', where: 'max' }], 'with no question to ask, the fresh record page is entered')
}
{
  /* the conversation route, blocked and then answered -- both ends */
  fresh()
  const stayed: Opened[] = []
  const host = makePage({ asks: () => true })
  const m = mountResults(host.page)
  const r = m.openResult(convDest(), launch(), (o) => stayed.push(o))
  no(leaves(r), 'a guarded conversation press has not arrived either')
  await settle()
  host.answer('stay')
  eq(stayed.map((o) => o.what), ['cancelled'], 'and Stay keeps the page exactly as it was')
}
{
  /* the post route, whose thread read can fail after the press */
  fresh()
  const settled: Opened[] = []
  const host = makePage({ openPost: (_c, _p, done) => { setImmediate(() => done({ how: 'failed', why: 'That post could not be read.' })) } })
  const m = mountResults(host.page)
  const r = m.openResult(postDest(), launch(), (o) => settled.push(o))
  eq(r, { what: 'leaving', how: 'post' }, 'a thread being read has not arrived')
  await settle()
  eq(settled.map((o) => o.what), ['unavailable'], 'and a read that failed is a failure, never a departure')
  eq(m.dockStep(settled[0]), 'keep', 'so the decision and its draft are kept')
}

/* ========================================================================== *
 * B4 / F12 -- the history entry is the RESULT, never its source post
 * ========================================================================== */
{
  fresh()
  const host = makePage()
  const m = mountResults(host.page)
  const l = launch()
  m.openResult(fromPost(A), l)
  await settle()
  eq(host.r.centre.length, 1, 'an artifact opened from a post owes exactly one history entry')
  const entry = host.r.centre[0]
  eq(entry?.result?.target, { kind: 'artifact', ref: A },
    'F12: THE ENTRY NAMES THE DELIVERABLE (B4), not the post the bytes came from')
  eq(entry, resultIntent(BRAIN, l.opening, { kind: 'artifact', ref: A }, HERE),
    'and is byte-identical to the one entry this opening would make anywhere else')
  eq(maximised()?.source, { kind: 'post', ...SOURCE }, 'while the viewer still shows the source it came from')
  eq(placedResults().targetOf(maximised()!.id), { kind: 'artifact', ref: A }, 'source and result stay distinct')
}
{
  /* a Brain-sourced artifact still gets its own identity, not none */
  fresh()
  const host = makePage()
  const m = mountResults(host.page)
  m.openResult(dest(A), launch())
  await settle()
  eq(host.r.centre[0]?.result?.target, { kind: 'artifact', ref: A }, 'F12: a Brain-sourced result is not target-less')
}

/* ========================================================================== *
 * B4 / F13 and B4.4 -- a reload resolves against the Place the entry saved,
 * and does so IN the entry it is already standing on
 * ========================================================================== */
{
  fresh()
  const host = makePage({ destinationOfTarget: () => dest(A) })
  const m = mountResults(host.page)
  /* the entry a reload leaves behind: no live launch for its opening */
  const entry = resultIntent(BRAIN, 800, { kind: 'artifact', ref: A }, SAVED)
  no(launchOf(800), 'its launch did not survive the reload')
  m.applyCentre(entry)
  await settle()
  const shown = maximised()
  ok(shown, 'F13: the target is resolved again rather than leaving a blank centre')
  const l = placedResults().launchOf(shown!.id)
  eq(l?.place, SAVED, 'F13: AND IT OWES THE PLACE THE ENTRY SAVED (B4), not wherever the reader is now')
  no(l?.place.conversation === HERE.conversation, 'the current conversation is not substituted for the stored one')
  eq(host.r.centre, [], 'B4.4: AND NO SECOND ENTRY IS PUSHED IN FRONT OF THE ONE BEING RESUMED')
  eq(host.r.replaced.length, 1, 'B4.4: the entry the browser is standing on is corrected in place')
  eq(host.r.replaced[0]?.result?.target, { kind: 'artifact', ref: A }, 'with the saved target kept')
  eq(host.r.replaced[0]?.result?.place, SAVED, 'and the saved Place kept')
  eq(host.r.replaced[0]?.result?.opening, l?.opening, 'naming the opening that is actually showing it now')
}
{
  /* no adapter from a stored target yet: the Place is still owed, and said */
  fresh()
  const host = makePage()
  const m = mountResults(host.page)
  m.applyCentre(resultIntent(BRAIN, 900, { kind: 'artifact', ref: A }, SAVED))
  eq(host.r.returns.map((l) => l.place), [SAVED], 'with no destination adapter the saved Place is still what is offered')
  eq(host.r.said.length, 1, 'and the reader is told, rather than shown a blank centre')
}
{
  /* a live viewer is shown again -- never a second one */
  fresh()
  const host = makePage()
  const m = mountResults(host.page)
  const l = launch()
  m.openResult(dest(A), l)
  await settle()
  const id = maximised()!.id
  m.applyCentre(resultIntent(BRAIN, l.opening, { kind: 'artifact', ref: A }, HERE))
  eq(maximised()?.id, id, 'landing on a live entry shows the same viewer, not another')
}

/* ========================================================================== *
 * B4.2 -- the host's own entry tracking is never skipped
 * ========================================================================== */
{
  fresh()
  const host = makePage()
  const m = mountResults(host.page)
  const l = launch()
  m.openResult(dest(A), l)
  await settle()
  const entry = host.r.centre[0]
  /* the real hook applies what was just pushed; here that is done by hand,
     and the whole round trip through `usePlaces` is in the history suite */
  host.r.tracked.length = 0
  ok(m.applyCentre(entry), 'a result entry is this part’s to apply')
  eq(host.r.tracked.length, 1, 'B4.2: applying a result entry tells the page where the centre has moved to')
  eq(host.r.tracked[0], entry, 'B4.2: WITH THE ENTRY ITSELF, before anything is decided about it')
  eq(host.atNow(), entry, 'so the host’s own tracker is on the result, not on the Place underneath')
  /* which is the fact the close depends on: this result owns its entry */
  const plan = closeSteps({ viewer: maximised()!.id, where: 'max', launch: l },
    { owns: !!host.atNow()?.result && host.atNow()!.result!.opening === l.opening, conversation: HERE.conversation })
  eq(plan.history, { how: 'back', to: HERE }, 'B4.2: AND SO THE CLOSE CAN MAKE THE HISTORY RETURN IT OWES')
}
{
  /* an ordinary entry is tracked by the same call, and the page's own arms
     still run for it */
  fresh()
  const host = makePage()
  const m = mountResults(host.page)
  no(m.applyCentre({ sources: 'all' }), 'an ordinary entry is not this part’s')
  eq(host.r.tracked, [{ sources: 'all' }], 'B4.2: and is tracked all the same, by the one call')
}

/* ========================================================================== *
 * B4 / F14 -- a frame-only close closes the frame and nothing else
 * ========================================================================== */
{
  fresh()
  const l = launch(SAVED)                      // opened in ANOTHER conversation
  const plan = closeSteps({ viewer: 'v', where: 'max', launch: l }, { owns: false, conversation: 'ent-current' })
  eq(plan.history, null, 'F14: navigation has since left this entry, so the history is left alone')
  ok(plan.bar, 'and the explicit return bar is what owes the reader their way back')
  no(plan.then.some((s) => s.do === 'restore'),
    'F14: NOTHING NAVIGATES BEHIND THE READER (B4): no conversation and no centre move on a frame-only close')
  eq(plan.then.map((s) => s.do), ['focus', 'forget'], 'only focus and the frame itself')
}
{
  /* the same, run through the real adapters against the real store */
  fresh()
  const host = makePage()
  const m = mountResults(host.page)
  const l = launch(SAVED)
  const id = openViewer({ kind: 'file', item: bytes() }, { kind: 'brain', brainKey: BRAIN }, 'max')
  byHand.push(id)
  placedResults().place(id, l, { kind: 'artifact', ref: A }, 'max')
  /* the centre is on something else now: this close owns no entry */
  m.closeResult(id)
  no(viewerOf(id), 'F14: the frame is closed')
  eq(host.r.picked, [], 'and the reader is not navigated anywhere')
  eq(host.r.back, [], 'no history move is made')
  eq(host.r.returns.map((x) => x.place), [SAVED], 'the return bar is offered instead, with the Place it owes')
  eq(host.conversationNow(), HERE.conversation, 'the conversation the reader chose is still the one shown')
}

/* ========================================================================== *
 * B4 / F15 -- a side close keeps the viewer while the return guard waits
 * ========================================================================== */
{
  fresh()
  const host = makePage({ asks: () => true })
  const m = mountResults(host.page)
  const l = launch(SAVED)                      // its way back is another conversation
  const id = openViewer({ kind: 'file', item: bytes() }, { kind: 'brain', brainKey: BRAIN }, 's1')
  byHand.push(id)
  placedResults().place(id, l, { kind: 'artifact', ref: A }, 's1')
  m.closeResult(id)
  eq(host.r.picked, [SAVED.conversation], 'the return asks for the conversation it was opened in')
  ok(host.waiting(), 'F15: and that press is GUARDED: the question is open')
  ok(viewerOf(id), 'F15: THE VIEWER IS STILL THERE WHILE THE READER IS BEING ASKED (B4, H7)')
  ok(launchOf(l.opening), 'and so is its way back')
  host.answer('stay')
  ok(viewerOf(id), 'F15: Stay keeps the viewer')
  ok(launchOf(l.opening), 'and keeps its launch, so the reader has lost nothing')
  eq(host.r.putBack, [], 'and nothing of the old Place was put back behind them')
}
{
  /* and Go finishes the close, in order: restore, focus, then the frame */
  fresh()
  const host = makePage({ asks: () => true })
  const m = mountResults(host.page)
  const l = launch(SAVED)
  const id = openViewer({ kind: 'file', item: bytes() }, { kind: 'brain', brainKey: BRAIN }, 's1')
  byHand.push(id)
  placedResults().place(id, l, { kind: 'artifact', ref: A }, 's1')
  m.closeResult(id)
  host.answer('go')
  eq(host.conversationNow(), SAVED.conversation, 'the reader is back in the conversation they opened it from')
  eq(host.r.putBack.map((s) => s.do), ['reading', 'reply', 'draft'], 'with the reading offset, the reply target and the draft KEY')
  eq(host.r.focused.length, 1, 'focus is returned once')
  no(viewerOf(id), 'F15: and ONLY THEN is the viewer given up')
  no(launchOf(l.opening), 'with its launch released')
}

/* ========================================================================== *
 * B4.3 -- a MAXIMISED close is guarded too, and Stay keeps everything
 * ========================================================================== */
{
  fresh()
  const host = makePage({ asks: () => true })
  const m = mountResults(host.page)
  const l = launch(SAVED)
  const id = openViewer({ kind: 'file', item: bytes() }, { kind: 'brain', brainKey: BRAIN }, 'max')
  byHand.push(id)
  placedResults().place(id, l, { kind: 'artifact', ref: A }, 'max')
  /* it owns the entry it is on, so this close walks the history */
  m.applyCentre(resultIntent(BRAIN, l.opening, { kind: 'artifact', ref: A }, SAVED))
  m.closeResult(id)
  eq(host.r.back, [SAVED], 'B4.3: the close asks for the history move it owes')
  ok(host.waiting(), 'B4.3: AND THAT MOVE IS ASKED ABOUT BEFORE IT IS MADE')
  ok(viewerOf(id), 'B4.3: the viewer is still there while the reader is being asked')
  ok(launchOf(l.opening), 'and so is its way back')
  eq(host.r.putBack, [], 'nothing of the old Place has been put back behind them')
  host.answer('stay')
  ok(viewerOf(id), 'B4.3: STAY KEEPS THE VIEWER')
  ok(launchOf(l.opening), 'and its launch')
  eq(host.r.putBack, [], 'and restores nothing')
  eq(host.r.returns, [], 'and claims no way back it does not need')
}
{
  /* and Go completes it -- ONE question for one close, not two */
  fresh()
  let asked = 0
  const host = makePage({ asks: () => { asked++; return asked === 1 } })
  const m = mountResults(host.page)
  const l = launch(SAVED)
  const id = openViewer({ kind: 'file', item: bytes() }, { kind: 'brain', brainKey: BRAIN }, 'max')
  byHand.push(id)
  placedResults().place(id, l, { kind: 'artifact', ref: A }, 'max')
  m.applyCentre(resultIntent(BRAIN, l.opening, { kind: 'artifact', ref: A }, SAVED))
  m.closeResult(id)
  host.answer('go')
  eq(asked, 1, 'B4.3: the reader is asked ONCE for one close: the history move took them to the whole Place')
  eq(host.r.picked, [], 'so the conversation is not pressed a second time behind the move')
  eq(host.r.putBack.map((s) => s.do), ['reading', 'reply', 'draft'], 'the rest of the Place is put back after it')
  no(viewerOf(id), 'and only then is the viewer given up')
}

/* ========================================================================== *
 * B4 / F16 -- leaving a result entry takes the overlay with it
 * ========================================================================== */
{
  fresh()
  const host = makePage()
  const m = mountResults(host.page)
  const l = launch()
  m.openResult(dest(A), l)
  await settle()
  const id = maximised()!.id
  const handled = m.applyCentre(null)
  no(handled, 'an ordinary entry is not a result entry, and the page’s own arms still run')
  no(maximised(), 'F16: THE MAXIMISED RESULT NO LONGER COVERS THE CENTRE (B4)')
  no(viewerOf(id), 'with no column to go back to, the overlay is given up')
  no(launchOf(l.opening), 'and its launch with it')
}
{
  /* a viewer the page never registered is still an overlay over the centre */
  fresh()
  const host = makePage()
  const m = mountResults(host.page)
  const id = openViewer({ kind: 'file', item: bytes() }, { kind: 'brain', brainKey: BRAIN }, 'max')
  byHand.push(id)
  m.applyCentre(null)
  no(maximised(), 'F16: including one this contract did not open')
}

/* ========================================================================== *
 * B4 / F10 -- go to source, with no column, is not a dead end
 * ========================================================================== */
{
  fresh()
  const host = makePage()
  const m = mountResults(host.page)
  m.openResult(fromPost(A), launch())
  await settle()
  const id = maximised()!.id
  m.goToSource(id, SOURCE)
  no(maximised(), 'F10: A MAXIMISED ARTIFACT NO LONGER SITS OVER THE POST IT SENDS THE READER TO (B4)')
  ok(viewerOf(id), 'F10: and nothing is closed: the viewer is parked, with its renderer’s state')
  eq(viewerOf(id)?.place, 'parked', 'which is what the store now does for a result the page has a way back to')
  eq(host.r.posts, [`source:${SOURCE.conversation}/${SOURCE.post}`], 'and the post is actually gone to')
  eq(placedResults().whereOf(id), 'none', 'the registry knows it is shown nowhere')
}
{
  /* the 3D Brain's own parking is untouched by that word */
  fresh()
  const id = openViewer({ kind: 'brain-space' }, { kind: 'brain', brainKey: BRAIN }, 'max')
  byHand.push(id)
  const host = makePage()
  const m = mountResults(host.page)
  m.goToSource(id, SOURCE)
  eq(viewerOf(id)?.place, 'parked', 'the graph parks exactly as it always did')
}

/* ========================================================================== *
 * N3 -- an ordinary maximised viewer keeps the baseline's return to its post
 * ========================================================================== */
{
  fresh()
  const host = makePage()
  const m = mountResults(host.page)
  /* a picture pressed in a post: the baseline's own `onView`, which registers
     no result and so has no launch here */
  const id = openViewer({ kind: 'file', item: bytes() }, { kind: 'post', ...SOURCE }, 'max')
  byHand.push(id)
  m.closeResult(id)
  no(viewerOf(id), 'N3: the frame closes, as it always did')
  eq(host.r.revealed, [SOURCE.post], 'N3: AND THE POST IT WAS DRAWN IN IS BROUGHT BACK INTO VIEW (the baseline’s own close)')
  eq(host.r.putBack, [], 'nothing of a launch it never had is invented')
  eq(host.r.back, [], 'and no history move is made for it')
}
{
  /* a column viewer never did it, and still does not; nor does a Brain-sourced
     one, which has no post to return to */
  fresh()
  const host = makePage()
  const m = mountResults(host.page)
  const side = openViewer({ kind: 'file', item: bytes() }, { kind: 'post', ...SOURCE }, 's1')
  const brain = openViewer({ kind: 'file', item: bytes(B) }, { kind: 'brain', brainKey: BRAIN }, 'max')
  byHand.push(side, brain)
  m.closeResult(side)
  m.closeResult(brain)
  eq(host.r.revealed, [], 'N3: only a maximised, post-sourced viewer reveals its post')
}

/* ========================================================================== *
 * the chooser, answered after the press (B3, carried)
 * ========================================================================== */
{
  fresh()
  const settled: Opened[] = []
  const host = makePage({ columns: () => ['s1', 's2'], freeColumn: () => null })
  const m = mountResults(host.page)
  const r = m.openResult(dest(A), launch(), (o) => settled.push(o))
  eq(r, { what: 'leaving', how: 'file' }, 'the press is read again before the reader is asked anything')
  await settle()
  eq(settled, [], 'B4.1: and the chooser is only reached once the read has answered')
  ok(host.chooser(), 'while the reader is choosing a column, nothing has been opened')
  host.chooser()!.decide('cancelled')
  eq(settled.map((o) => o.what), ['cancelled'], 'a placement the reader abandoned is not a departure')
  eq(host.r.centre, [], 'and owes no history entry')
}
{
  fresh()
  const settled: Opened[] = []
  const host = makePage({ columns: () => ['s1', 's2'], freeColumn: () => null })
  const m = mountResults(host.page)
  m.openResult(fromPost(A), launch(), (o) => settled.push(o))
  await settle()
  host.chooser()!.decide('s2')
  eq(settled, [{ what: 'opened', how: 'file', where: 's2' }], 'the column they chose is where it went')
  eq(host.r.centre, [], 'a column is not the centre, so it pushes no entry and runs no centre guard (H1)')
  eq(placedResults().whereOf(maximisedOrColumn('s2')), 's2', 'and the placement is registered where it actually went')
}

/* ========================================================================== *
 * B4.4-R1 (re-review adm-efb406a34e7a, BLOCKING) -- A PENDING RESUME IS BOUND
 * TO THE ENTRY IT LANDED ON. The composed version of these two cases, over
 * the REAL history hook and a real `popstate`, is in
 * `tests/quiet2_result_history_unit.ts`; here the two ASYNCHRONOUS GATES are
 * exercised directly, including the chooser one, which has no column in that
 * fixture.
 * ========================================================================== */

function savedEntry(): CentreAt {
  return { result: { brainKey: BRAIN, opening: 91, target: { kind: 'artifact', ref: A }, place: SAVED } }
}

{
  /* THE READ ANSWERS AFTER THE READER HAS GONE BACK */
  fresh()
  let give: ((f: FreshArtifact) => void) | null = null
  const host = makePage({
    destinationOfTarget: () => dest(),
    artifactNow: () => new Promise<FreshArtifact>((answer) => { give = answer }),
  })
  const m = mountResults(host.page)
  ok(m.applyCentre(savedEntry()), 'landing on a saved result entry is this part’s to handle')
  await settle()
  ok(give, 'B4.4-R1: its fresh read is in flight, and nothing is placed yet')
  no(maximised(), 'with no viewer')
  /* the reader presses Back: an ordinary entry, which this part leaves alone */
  no(m.applyCentre(null), 'Back lands on a Place, not a result')
  const replaced = host.r.replaced.length
  give!({ how: 'held', file: { ...HELD, ref: A, treatment: { view: 'text' } } })
  await settle()
  no(maximised(), 'B4.4-R1: the late answer opens NO viewer over the Place Back reached')
  eq(placedResults().all().length, 0, 'and registers nothing')
  eq(host.r.replaced.length, replaced, 'B4.4-R1: AND REPLACES NO ENTRY -- the Place the reader is on is theirs')
  eq(host.r.said, [], 'nothing is said about a resume they navigated away from')
}
{
  /* THE READER IS STILL CHOOSING A COLUMN when the centre moves */
  fresh()
  const host = makePage({
    columns: () => ['s1', 's2'], freeColumn: () => null, destinationOfTarget: () => dest(),
  })
  const m = mountResults(host.page)
  m.applyCentre(savedEntry())
  await settle()
  ok(host.chooser(), 'B4.4-R1: the resume asks which column, there being no free one')
  m.applyCentre(null)
  host.chooser()!.decide('s1')
  eq(placedResults().all().length, 0, 'B4.4-R1: a column chosen after the reader left the entry places nothing')
  eq(host.r.replaced, [], 'and nothing is written to the history for it')
}
{
  /* AND THE RESUME THAT IS STILL CURRENT IS UNTOUCHED (B4.4 preserved) */
  fresh()
  const host = makePage({ destinationOfTarget: () => dest() })
  const m = mountResults(host.page)
  m.applyCentre(savedEntry())
  await settle()
  const shown = maximised()
  ok(shown, 'B4.4 preserved: a resume whose entry is still current opens')
  eq(host.r.centre, [], 'B4.4 preserved: pushing nothing')
  eq(host.r.replaced.length, 1, 'and correcting the entry it landed on, once')
  eq(host.r.replaced[0]?.result?.target, { kind: 'artifact', ref: A }, 'with the target the entry saved')
  eq(host.r.replaced[0]?.result?.place, SAVED, 'and the Place it saved (F13)')
}

/* ========================================================================== *
 * F1 / F2 (re-review adm-af5263a65134, BLOCKING) -- THE BRAIN IS READ WHEN THE
 * ANSWER COMES, NOT WHEN THE RENDER WAS MADE.
 *
 * The third of B4.4-R1's three bindings was the one that could never fail: the
 * hand-off answered it with a getter built inside the host component, so a
 * pending read and an open chooser asked THEIR OWN RENDER which Brain this was
 * and got the answer that render had been made with. A new mount for a new
 * Brain -- no centre move, so no generation -- left both gates open.
 *
 * Here that is exercised where it lives: `mountResults` is called twice, as a
 * host's own re-render calls it, and the serving key moves underneath BOTH, as
 * `results/serving.ts`'s module store does. The composed version, over the real
 * history and the hand-off's own expressions, is in
 * `tests/quiet2_result_history_unit.ts`.
 * ========================================================================== */
{
  /* THE OLD MOUNT'S READ, after a new mount for another INSTANCE */
  fresh()
  let give: ((f: FreshArtifact) => void) | null = null
  const host = makePage({
    destinationOfTarget: () => dest(),
    artifactNow: () => new Promise<FreshArtifact>((answer) => { give = answer }),
  })
  const first = mountResults(host.page)
  first.applyCentre(savedEntry())
  await settle()
  ok(give, 'the saved result’s read is in flight inside the first mount')
  const replaced = host.r.replaced.length
  /* the page renders again for another Brain: a new mount, NO centre move */
  mountResults(host.page)
  served = 'fixture-corpus@instance-2'
  give!({ how: 'held', file: { ...HELD, ref: A, treatment: { view: 'text' } } })
  await settle()
  no(maximised(), 'F1: THE EARLIER MOUNT’S READ OPENS NOTHING once another instance is served')
  eq(placedResults().all().length, 0, 'and registers nothing in any column')
  eq(host.r.replaced.length, replaced, 'F1: nor does it correct the entry it was bound to')
  eq(host.r.said, [], 'and says nothing: the reader asked for none of it')
}
{
  /* THE OLD MOUNT'S CHOOSER, answered after the same change */
  fresh()
  const host = makePage({
    columns: () => ['s1', 's2'], freeColumn: () => null, destinationOfTarget: () => dest(),
  })
  const first = mountResults(host.page)
  first.applyCentre(savedEntry())
  await settle()
  ok(host.chooser(), 'the resume is asking which column to use')
  mountResults(host.page)
  served = 'different-corpus@instance-1'
  host.chooser()!.decide('s1')
  await settle()
  eq(placedResults().all().length, 0, 'F1: A COLUMN CHOSEN FOR ANOTHER BRAIN’S PAGE PLACES NOTHING')
  no(maximised(), 'nor is anything maximised')
  eq(host.r.replaced, [], 'and nothing is written to the history for it')
}
{
  /* AND AN EXPLICIT PRESS IS GATED THE SAME WAY: its launch names the Brain it
     was made for, so a column the reader picks after the server has begun
     serving another one places nothing either (F1's second gate, for the arm
     that is not a resume at all) */
  fresh()
  const host = makePage({ columns: () => ['s1', 's2'], freeColumn: () => null })
  const m = mountResults(host.page)
  m.openResult(dest(A), m.launchNow(HERE, { control: null, fallback: { kind: 'conversation' } }))
  await settle()
  ok(host.chooser(), 'the press asks which column, there being no free one')
  served = 'fixture-corpus@instance-2'
  host.chooser()!.decide('s1')
  await settle()
  eq(placedResults().all().length, 0, 'F1: a press’s own late placement is refused for a Brain that has changed')
  no(maximised(), 'and nothing is maximised by it')
}
{
  /* THE SAME PRESS, WITH THE BRAIN UNCHANGED, STILL PLACES (preserved) */
  fresh()
  const host = makePage({ columns: () => ['s1', 's2'], freeColumn: () => null })
  const m = mountResults(host.page)
  m.openResult(dest(A), m.launchNow(HERE, { control: null, fallback: { kind: 'conversation' } }))
  await settle()
  host.chooser()!.decide('s1')
  await settle()
  eq(placedResults().all().length, 1, 'preserved: a chosen column still places the result it was asked about')
}
{
  /* F2: THE LAUNCH AND THE ENTRY CARRY THE SERVING KEY, instance included --
     which is what makes the comparison above possible at all. The graph key
     the hand-off used to supply is a different member now, and reaches only
     the viewer's own source. */
  fresh()
  const host = makePage()
  const m = mountResults(host.page)
  const l = m.launchNow(HERE, { control: null, fallback: { kind: 'conversation' } })
  eq(l.brainKey, BRAIN, 'F2: a launch names the Brain the SERVER serves, `<corpus>@<instance>`')
  m.openResult(dest(A), l)
  await settle()
  eq(host.r.centre[0]?.result?.brainKey, BRAIN, 'F2: and so does the history entry it writes')
  eq(maximised()?.source, { kind: 'brain', brainKey: BRAIN },
    'while the viewer’s own source is the GRAPH key member, which is all that still needs one')
}
{
  /* a page that cannot say which Brain it is on names none, and a saved entry
     of a Brain it cannot name is not resumed */
  fresh()
  served = null
  const host = makePage({ destinationOfTarget: () => dest() })
  const m = mountResults(host.page)
  eq(m.launchNow(HERE, { control: null, fallback: { kind: 'conversation' } }).brainKey, null,
    'F1/F2: an unbound or moved page names no Brain at all')
  m.applyCentre(savedEntry())
  await settle()
  no(maximised(), 'F1/F2: and resumes nothing saved against one')
  eq(host.r.said, [BRAIN_MOVED], 'telling the reader the page is showing another Brain than the server serves')
}

/* ========================================================================== *
 * N2 (recorded as discovered work, and not reachable through this adapter) --
 * closing the FIRST of two viewers returns focus to the FIRST one's invoker
 * ========================================================================== */
{
  fresh()
  const focused: string[] = []
  const first = { isConnected: true, focus: () => focused.push('first') }
  const second = { isConnected: true, focus: () => focused.push('second') }
  let next: { isConnected: boolean; focus: () => void } = first
  const host = makePage({
    columns: () => ['s1', 's2'],
    freeColumn: () => (placedResults().all().length ? 's2' : 's1'),
    invoker: () => next,
    focus: (choice, invoker) => { if (choice.how === 'invoker') (invoker as { focus: () => void } | null)?.focus() },
  })
  const m = mountResults(host.page)
  m.openResult(dest(A), launch())
  await settle()
  next = second
  m.openResult(dest(B), launch())
  await settle()
  const rows = placedResults().all()
  eq(rows.length, 2, 'two results are open beside the conversation')
  m.closeResult(rows[0].viewer)
  eq(focused, ['first'], 'N2: THE CLOSING VIEWER’S OWN INVOKER takes focus, not the last thing opened')
}

function maximisedOrColumn(where: 's1' | 's2'): string {
  const row = placedResults().all().find((v) => v.where === where)
  return row ? row.viewer : ''
}

/* ========================================================================== *
 * F3 -- A LAUNCH MADE WITH NO CONFIRMED IDENTITY IS REFUSED, THROUGH THESE
 * ADAPTERS (independent review adm-1cb30e65d05f)
 *
 * The F1/F2 gates above all read `launch.brainKey &&`, so the one launch whose
 * Brain cannot be checked -- one made before this page had confirmed which
 * Brain it is on, or after it had moved -- passed every one of them. Through
 * THIS composition that meant: a viewer opened and registered, a record
 * navigated to, `opened` reported, and a history entry written under whatever
 * identity had answered by the time the read came back.
 * ========================================================================== */
{
  /* THE PRESS ITSELF, with no column free to make it interesting: the
     maximised arm is the one that placed first and cleaned up afterwards, so
     the placement is observed where the store sees it (`invoker`, which
     `results.place` calls) and not only by what is left at the end. */
  fresh()
  served = null
  const placements: unknown[] = []
  const host = makePage({ columns: () => [], invoker: () => { placements.push(maximised()?.id ?? null); return null } })
  const m = mountResults(host.page)
  const l = m.launchNow(HERE, { control: null, fallback: { kind: 'conversation' } })
  eq(l.brainKey, null, 'a press made before the page can say which Brain it is on names none')
  const went = m.openResult(dest(A), l)
  await settle()
  eq(went, { what: 'refused', why: BRAIN_UNCONFIRMED }, 'F3: and it is REFUSED, not resolved')
  eq(host.r.read, [], 'F3: nothing is read: the gate is before the fresh read, not after it')
  eq(placements, [], 'F3: nothing is placed -- not even a viewer opened and closed again within the press')
  no(maximised(), 'nothing is maximised')
  eq(placedResults().all().length, 0, 'nothing is registered')
  eq(host.r.centre, [], 'F3: and no history entry is pushed for it')
  eq(host.r.said, [BRAIN_UNCONFIRMED], 'the reader is told the page cannot say yet, and to try again')
}
{
  /* A MOVED PAGE IS TOLD APART FROM ONE THAT HAS NOT ANSWERED YET: both refuse,
     and the reader is told which -- wait, or reload. */
  fresh()
  served = null
  const host = makePage({ serving: () => null, columns: () => ['s1', 's2'], freeColumn: () => 's1' })
  const m = mountResults(host.page)
  const went = m.openResult(dest(A), m.launchNow(HERE, { control: null, fallback: { kind: 'conversation' } }))
  await settle()
  eq(went.what, 'refused', 'F3: a free column does not make an unidentified press safe either')
  eq(placedResults().all().length, 0, 'and places nothing in it')
}
{
  /* THE RECORD ROUTE, which reaches no artifact and no bytes at all: the
     reviewer's cases 32-33. */
  fresh()
  served = null
  const host = makePage()
  const m = mountResults(host.page)
  const went = m.openResult(recordDest(), m.launchNow(HERE, { control: null, fallback: { kind: 'conversation' } }))
  await settle()
  eq(went.what, 'refused', 'F3: an unidentified press does not navigate to a record')
  eq(host.r.picked, [], 'F3: the page’s own record route is never asked -- the gate is before the target')
  no(leaves(went), 'and nothing was left, so the draft and the open form are kept')
}
{
  /* AND IT DOES NOT ACQUIRE AN IDENTITY BY FINISHING (the reviewer's cases
     38-39). The press is made while the page cannot say; the page binds while
     the read is in flight; the answer must still place nothing AND write no
     entry naming the Brain that answered in the meantime. */
  fresh()
  served = null
  let give: ((f: FreshArtifact) => void) | null = null
  const host = makePage({
    columns: () => [], artifactNow: () => new Promise<FreshArtifact>((answer) => { give = answer }),
  })
  const m = mountResults(host.page)
  const l = m.launchNow(HERE, { control: null, fallback: { kind: 'conversation' } })
  m.openResult(dest(A), l)
  await settle()
  no(give, 'F3: the read never began, because the press was refused before it')
  served = BRAIN
  await settle()
  no(maximised(), 'F3: and a Brain answering afterwards does not open what was pressed before it could')
  eq(host.r.centre, [], 'F3: nothing is written to the history under the identity that arrived later')
  eq(host.r.replaced, [], 'and nothing is corrected in place either')
}
{
  /* THE SAME PRESS, ONCE THE PAGE HAS CONFIRMED, STILL OPENS NORMALLY: the
     refusal above is a window, not a page that can no longer open a result.
     This is the whole of the startup behaviour, in this composition. */
  fresh()
  served = null
  const host = makePage({ columns: () => [] })
  const m = mountResults(host.page)
  m.openResult(dest(A), m.launchNow(HERE, { control: null, fallback: { kind: 'conversation' } }))
  await settle()
  no(maximised(), 'before the page can say: nothing')
  served = BRAIN
  const after = m.launchNow(HERE, { control: null, fallback: { kind: 'conversation' } })
  eq(after.brainKey, BRAIN, 'once confirmed, a press names the Brain the server serves')
  m.openResult(dest(A), after)
  await settle()
  ok(maximised(), 'preserved: and opens exactly as it always did')
  eq(host.r.centre[0]?.result?.brainKey, BRAIN, 'with its entry naming that same confirmed Brain')
}
{
  /* AND A SAVED ENTRY LANDED ON WHILE THE PAGE CANNOT SAY IS NOT RESUMED --
     preserved from F1/F2, and now for the same reason as everything else. */
  fresh()
  served = null
  const host = makePage({ destinationOfTarget: () => dest() })
  const m = mountResults(host.page)
  m.applyCentre(savedEntry())
  await settle()
  no(maximised(), 'F3: a resume begun with no confirmed identity places nothing')
  eq(host.r.read, [], 'and reads nothing')
}

/* ========================================================================== *
 * F4 -- A PENDING MOVE IS CHECKED WHERE IT MOVES, NOT ONLY WHERE IT WAS ASKED
 * (independent re-review adm-e2d35bd306b8, blocking)
 *
 * The press passed every gate: the launch named the Brain the server was
 * serving, and the unsaved-work guard then held the question open. The server
 * began serving another instance of the corpus, or another corpus, while the
 * reader was deciding. Answering Go moved the page anyway -- the record page
 * shown, the conversation opened and saved, an entry pushed -- and reported
 * `opened`. Each arm below answers Go AFTER the binding has changed, and asks
 * the only question that matters: did anything move?
 * ========================================================================== */
{
  /** every way the serving identity can stop being the launch's */
  const moves: [string, string | null][] = [
    ['another instance of the same corpus', 'fixture-corpus@instance-2'],
    ['another corpus', 'other-corpus@instance-1'],
    ['no identity the page can name', null],
  ]
  for (const [what, to] of moves) {
    for (const route of ['record', 'conversation'] as const) {
      fresh()
      const host = makePage({ asks: () => true })
      const m = mountResults(host.page)
      const settled: Opened[] = []
      const where = route === 'record' ? recordDest() : convDest()
      const went = m.openResult(where, launch(), (o) => settled.push(o))
      eq(went, { what: 'leaving', how: route }, `${route}: the press is guarded, so nothing has arrived yet`)
      /* AND THE READ COMES FIRST (P4, integrated here): a post, record or
         conversation press is described again before anything is asked, so the
         guard opens once that read has answered -- which is what every other
         press in this file already waits for. */
      await settle()
      ok(host.waiting(), 'and the unsaved-work question is open')
      /* the route was ASKED FOR on the press, as it always was; what has not
         happened is the move itself, which is behind the guard */
      eq(host.conversationNow(), HERE.conversation, 'nothing has moved on the press itself')

      /* the server begins serving something else WHILE the reader decides */
      served = to
      host.answer('go')

      eq(host.r.picked.filter((p) => p.startsWith('record:')), [], `F4: ${route} does not move after ${what}`)
      eq(host.conversationNow(), HERE.conversation, 'the conversation the reader was in is still the one shown')
      eq(host.r.centre, [], 'no history entry is pushed')
      eq(settled.map((o) => o.what), ['refused'], 'and the reader is told it was refused, not that they arrived')
      eq(host.r.said, [to === null ? BRAIN_UNCONFIRMED : BRAIN_MOVED], 'in that state own words, once')
      no(settled.some(leaves), 'nothing counts as a departure, so the dock and the draft are kept')
    }
  }
}
{
  /* AND A POST PRESS IS THE SAME MOVE: `openFromDock` opens a conversation. */
  for (const to of ['fixture-corpus@instance-2', null]) {
    fresh()
    const host = makePage({ asks: () => true })
    const m = mountResults(host.page)
    const settled: Opened[] = []
    m.openResult(postDest(), launch(), (o) => settled.push(o))
    await settle()
    ok(host.waiting(), 'post: the guard is open')
    served = to
    host.answer('go')
    eq(host.r.posts, [`${SOURCE.conversation}/${SOURCE.post}`], 'the route was asked for on the press')
    eq(host.conversationNow(), HERE.conversation, 'F4: but the conversation never moved')
    eq(settled.map((o) => o.what), ['refused'], 'and no arrival is reported')
  }
}
{
  /* STAY IS STILL STAY, whatever the binding did: the reader chose it, and is
     told nothing about a Brain they never navigated to. */
  for (const to of ['fixture-corpus@instance-2', BRAIN]) {
    fresh()
    const host = makePage({ asks: () => true })
    const m = mountResults(host.page)
    const settled: Opened[] = []
    m.openResult(recordDest(), launch(), (o) => settled.push(o))
    await settle()
    served = to
    host.answer('stay')
    eq(host.r.picked, [], 'Stay moves nothing')
    eq(settled.map((o) => o.what), ['cancelled'], 'and is reported as the reader own choice, not as a refusal')
  }
}
{
  /* AND THE UNCHANGED BINDING STILL GOES. The gate refuses a move whose Brain
     changed; it must not refuse one whose Brain did not, pending or not. */
  for (const route of ['record', 'conversation'] as const) {
    fresh()
    const host = makePage({ asks: () => true })
    const m = mountResults(host.page)
    const settled: Opened[] = []
    m.openResult(route === 'record' ? recordDest() : convDest(), launch(), (o) => settled.push(o))
    await settle()
    host.answer('go')
    eq(settled.map((o) => o.what), ['opened'], `preserved: ${route} opens on Go under the same Brain`)
    eq(settled.length, 1, 'exactly once')
    eq(host.r.said, [], 'and nothing is said to the reader about it')
  }
}
{
  /* AN IMMEDIATE MOVE -- no unsaved work, no question -- is unchanged. */
  fresh()
  const host = makePage()
  const m = mountResults(host.page)
  const settled: Opened[] = []
  const went = m.openResult(convDest(), launch(), (o) => settled.push(o))
  eq(went, { what: 'leaving', how: 'conversation' }, 'the direct conversation is read first (P4)')
  await settle()
  eq(settled.map((o) => o.what), ['opened'], 'preserved: an unguarded conversation press then arrives')
  eq(host.conversationNow(), 'ent-conversatn1', 'and the conversation really is the one shown')
}
{
  /* THE SECOND NET: a host that moved WITHOUT asking cannot report an arrival.
     This is not the gate -- the move has happened -- and it is here to show
     that the report alone would not have been enough. */
  fresh()
  let late: (() => void) | null = null
  const host = makePage({
    record: (begin, _stay) => { const go = begin(); late = go ? go.moved : null },
  })
  const m = mountResults(host.page)
  const settled: Opened[] = []
  m.openResult(recordDest(), launch(), (o) => settled.push(o))
  await settle()
  ok(late, 'the move began under the launch own Brain')
  served = 'other-corpus@instance-1'
  late!()
  eq(settled.map((o) => o.what), ['refused'], 'a completion reported under another Brain is not an arrival')
}

/* ========================================================================== *
 * RECOVERY -- a confirmation that failed can be recovered by pressing again
 * (independent re-review adm-e2d35bd306b8, nonblocking)
 * ========================================================================== */
{
  fresh()
  served = null                                   // the startup ask failed: unconfirmed for good
  let asked = 0
  const host = makePage({ confirmServing: async () => { asked++; served = BRAIN; return true } })
  const m = mountResults(host.page)
  const settled: Opened[] = []
  m.openResult(recordDest(), m.launchNow(HERE, { control: null, fallback: { kind: 'conversation' } }), (o) => settled.push(o))
  eq(host.r.picked, [], 'the press that found no confirmed Brain is still refused')
  eq(host.r.said, [BRAIN_UNCONFIRMED], 'and says so')
  eq(asked, 1, 'and asks the server once, which is what makes "try again" true')
  await settle()
  const second = m.openResult(recordDest(), m.launchNow(HERE, { control: null, fallback: { kind: 'conversation' } }), (o) => settled.push(o))
  eq(second.what, 'leaving', 'the next press is read first (P4), not refused')
  await settle()
  eq(settled[settled.length - 1]?.what, 'opened', 'so the NEXT press opens: the dead end is gone')
  eq(asked, 1, 'and nothing asked again once there was an answer')
}
{
  /* ONE ASK AT A TIME, and a MOVED page is never asked: only a reload binds
     that one, and asking again could not change it. */
  fresh()
  served = null
  let asked = 0
  let release: (() => void) | null = null
  const host = makePage({ confirmServing: () => new Promise<unknown>((done) => { asked++; release = () => done(null) }) })
  const m = mountResults(host.page)
  for (let i = 0; i < 3; i++) m.openResult(recordDest(), m.launchNow(HERE, { control: null, fallback: { kind: 'conversation' } }))
  await settle()
  eq(asked, 1, 'three presses while one ask is in flight start one ask, not three')
  release!()
  await settle()

  fresh()
  asked = 0
  const moved = makePage({ serving: () => null, confirmServing: async () => { asked++; return null } })
  const mm = mountResults(moved.page)
  served = BRAIN
  mm.openResult(recordDest(), launch())          // launch names BRAIN, page says nothing
  await settle()
  ok(asked <= 1, 'and a page with no answer asks at most once per press')
}
{
  /* N6 -- AND THAT BOUND IS THE PAGE'S, NOT ONE RENDER'S (independent
     re-review adm-33bc95d78f7a, nonblocking). `mountResults` runs on every
     render of the host, so an in-flight flag declared inside it was a fresh
     `false` for each render and two presses either side of one both asked. */
  fresh()
  served = null
  let asked = 0
  let release: (() => void) | null = null
  const host = makePage({ confirmServing: () => new Promise<unknown>((done) => { asked++; release = () => done(null) }) })
  const first = mountResults(host.page)
  first.openResult(recordDest(), first.launchNow(HERE, { control: null, fallback: { kind: 'conversation' } }))
  eq(asked, 1, 'the refused press asks the server once')
  const again = mountResults(host.page)          // the page re-renders: a new mount, the same page
  again.openResult(recordDest(), again.launchNow(HERE, { control: null, fallback: { kind: 'conversation' } }))
  eq(asked, 1, 'N6: a press after a re-render starts no second ask while one is in flight')
  release!()
  await settle()
}

/* ========================================================================== *
 * F5 -- THE THREAD READ ASKS TOO, WHERE IT TOUCHES THE PAGE
 * (independent re-review adm-33bc95d78f7a, blocking)
 *
 * A post press has two ends: the conversation move, which F4's `begin` guards,
 * and the thread read that lands afterwards. That read is asynchronous, and
 * the server can begin serving another Brain while it is in flight. The
 * contract applied its answer anyway -- the thread entered, the reply target
 * cleared, the surfaces rewritten -- and only THEN found the completion report
 * refused. Suppressing the report while leaving the page changed is exactly
 * what F4 said is not the same thing. Both ends ask now.
 * ========================================================================== */
{
  const gone: [string, string | null][] = [
    ['another instance of the same corpus', 'fixture-corpus@instance-2'],
    ['another corpus', 'other-corpus@instance-1'],
    ['no identity the page can name', null],
  ]
  for (const [what, to] of gone) {
    for (const overlay of [false, true]) {
      fresh()
      const entered: string[] = []
      let land: (() => void) | null = null
      let move: (() => void) | null = null
      /** the documented `openFromDock`/`showPost` pair: `begin` for the move
       *  where there is one, `may` for the read that lands after it */
      const host = makePage({
        openPost: (c, p, done: (n: Navigation) => void, begin, may: MayMove) => {
          const read = () => {
            land = () => {
              const why = may()
              if (why) { done({ how: 'refused', why }); return }
              entered.push(`${c}/${p}`)     // onEnter: the thread, the reply target, the surfaces
              done('completed')
            }
          }
          if (!overlay) { read(); return }  // already here: there is no move to make
          move = () => { const go = begin(); if (!go) return; read() }
        },
      })
      const m = mountResults(host.page)
      const settled: Opened[] = []
      const went = m.openResult(postDest(), launch(), (o) => settled.push(o))
      eq(went, { what: 'leaving', how: 'post' }, 'the post press has not arrived: its thread is being read')
      await settle()                        // the P4 read on the press answers first
      if (overlay) { move!(); eq(host.r.said, [], 'the overlay move itself was allowed, under the launch own Brain') }
      ok(land, 'and the thread read is in flight')

      /* the server begins serving something else WHILE it is */
      served = to
      land!()

      eq(entered, [], `F5: ${overlay ? 'an overlay' : 'an already-shown'} post enters nothing after ${what}`)
      eq(settled.map((o) => o.what), ['refused'], 'the press is refused, not reported as opened')
      eq(settled.length, 1, 'exactly once')
      eq(host.r.said, [to === null ? BRAIN_UNCONFIRMED : BRAIN_MOVED], 'in that state own words, once')
    }
  }
}
{
  /* PRESERVED: the same read under the same Brain still enters and opens. */
  for (const overlay of [false, true]) {
    fresh()
    const entered: string[] = []
    let land: (() => void) | null = null
    let move: (() => void) | null = null
    const host = makePage({
      openPost: (c, p, done: (n: Navigation) => void, begin, may: MayMove) => {
        const read = () => {
          land = () => {
            const why = may()
            if (why) { done({ how: 'refused', why }); return }
            entered.push(`${c}/${p}`)
            done('completed')
          }
        }
        if (!overlay) { read(); return }
        move = () => { const go = begin(); if (!go) return; read() }
      },
    })
    const m = mountResults(host.page)
    const settled: Opened[] = []
    m.openResult(postDest(), launch(), (o) => settled.push(o))
    await settle()                          // the P4 read on the press answers first
    if (overlay) move!()
    land!()
    eq(entered, [`${SOURCE.conversation}/${SOURCE.post}`], `preserved: the thread is entered under the same Brain (overlay: ${overlay})`)
    eq(settled.map((o) => o.what), ['opened'], 'and the press opened')
    eq(host.r.said, [], 'with nothing said to the reader')
  }
}

/* ========================================================================== *
 * F6 -- THE READER IS TOLD WHY, OBSERVER OR NO OBSERVER
 * (independent re-review adm-33bc95d78f7a, blocking)
 *
 * The late answer was thrown away unless a `settled` observer had been
 * registered, and the words the reader is owed were said inside the answer
 * that was never made. So a reader who answered Go at the guard, under a Brain
 * that had moved, was refused in silence: the move was correctly not made, and
 * nothing on the page said why. The observer reports an outcome to a CALLER;
 * it was never the condition for telling the READER anything.
 * ========================================================================== */
{
  for (const route of ['record', 'conversation', 'post'] as const) {
    for (const to of ['fixture-corpus@instance-2', 'other-corpus@instance-1', null]) {
      fresh()
      const host = makePage({ asks: () => true })
      const m = mountResults(host.page)
      const where = route === 'record' ? recordDest() : route === 'conversation' ? convDest() : postDest()
      /* NO third argument at all: this caller does not want to be told */
      const went = m.openResult(where, launch())
      eq(went.what, 'leaving', `${route}: the press is guarded, so nothing has arrived yet`)
      await settle()                        // the P4 read on the press answers first
      served = to
      host.answer('go')
      eq(host.conversationNow(), HERE.conversation, 'nothing moved, as F4 already required')
      eq(host.r.centre, [], 'and no history entry was pushed')
      eq(host.r.said, [to === null ? BRAIN_UNCONFIRMED : BRAIN_MOVED],
        `F6: and the reader is told why ONCE with no completion observer (${route})`)
    }
  }
}
{
  /* PRESERVED: an unchanged Brain still goes, and says nothing, with no
     observer either -- and a reader's own Stay is still silent. */
  for (const answer of ['go', 'stay'] as const) {
    fresh()
    const host = makePage({ asks: () => true })
    const m = mountResults(host.page)
    m.openResult(convDest(), launch())
    await settle()                          // the P4 read on the press answers first
    host.answer(answer)
    eq(host.conversationNow(), answer === 'go' ? 'ent-conversatn1' : HERE.conversation, `preserved: ${answer} does what it always did`)
    eq(host.r.said, [], 'and nothing is said to the reader either way')
  }
}
{
  /* and a late FAILURE is the reader's business too, observer or not */
  fresh()
  const host = makePage({ openPost: (_c, _p, done) => { setImmediate(() => done({ how: 'failed', why: 'That post could not be read.' })) } })
  const m = mountResults(host.page)
  m.openResult(postDest(), launch())
  await settle()
  eq(host.r.said, ['That post could not be read.'], 'F6: a late failure says so once, with nobody listening')
}

/* ========================================================================== *
 * F7 -- A CLOSE PUTS BACK THE OLD BRAIN'S PLACE ONLY WHILE IT IS STILL SERVED
 * (independent re-review adm-33bc95d78f7a, blocking)
 *
 * The restore supplied a `begin` that always said yes, on the grounds that a
 * close has no result identity to carry. It has one: the launch the closing
 * viewer was opened under, which the close already reads for its focus choice.
 * The close's own guard holds the question open, the server can begin serving
 * another Brain while it does, and answering Go then walked the history or
 * opened the old conversation, put the old thread and reply target back, saved
 * the workspace and gave up the viewer and its launch -- under an identity
 * nobody was being served.
 * ========================================================================== */
{
  const gone: [string, string | null][] = [
    ['another instance of the same corpus', 'fixture-corpus@instance-2'],
    ['another corpus', 'other-corpus@instance-1'],
    ['no identity the page can name', null],
  ]
  for (const [what, to] of gone) {
    /* the history-owned maximised close, and the side close that returns to
       another conversation: the two moves a close makes */
    for (const how of ['max-history', 'side-other'] as const) {
      fresh()
      const host = makePage({ asks: () => true })
      const m = mountResults(host.page)
      const l = launch(SAVED)
      const id = openViewer({ kind: 'file', item: bytes() }, { kind: 'brain', brainKey: BRAIN }, how === 'max-history' ? 'max' : 's1')
      byHand.push(id)
      placedResults().place(id, l, { kind: 'artifact', ref: A }, how === 'max-history' ? 'max' : 's1')
      if (how === 'max-history') m.applyCentre(resultIntent(BRAIN, l.opening, { kind: 'artifact', ref: A }, SAVED))
      m.closeResult(id)
      ok(host.waiting(), `${how}: the close is guarded, and the question is open`)

      /* the server begins serving something else WHILE the reader decides */
      served = to
      host.answer('go')

      eq(host.r.putBack, [], `F7: ${how} restores nothing of the old Place after ${what}`)
      eq(host.conversationNow(), HERE.conversation, 'the conversation the reader is in is untouched')
      ok(viewerOf(id), 'F7: the viewer is kept, as Stay would keep it')
      ok(launchOf(l.opening), 'and so is its way back')
      eq(host.r.said, [to === null ? BRAIN_UNCONFIRMED : BRAIN_MOVED], 'and the reason is said once')
    }
  }
}
{
  /* PRESERVED: under the same Brain, both closes complete exactly as before. */
  for (const how of ['max-history', 'side-other'] as const) {
    fresh()
    const host = makePage({ asks: () => true })
    const m = mountResults(host.page)
    const l = launch(SAVED)
    const id = openViewer({ kind: 'file', item: bytes() }, { kind: 'brain', brainKey: BRAIN }, how === 'max-history' ? 'max' : 's1')
    byHand.push(id)
    placedResults().place(id, l, { kind: 'artifact', ref: A }, how === 'max-history' ? 'max' : 's1')
    if (how === 'max-history') m.applyCentre(resultIntent(BRAIN, l.opening, { kind: 'artifact', ref: A }, SAVED))
    m.closeResult(id)
    host.answer('go')
    eq(host.r.putBack.map((s) => s.do), ['reading', 'reply', 'draft'], `preserved: ${how} puts the Place back under the same Brain`)
    no(viewerOf(id), 'and only then gives up the viewer')
    eq(host.r.said, [], 'with nothing said about identity')
  }
}
/* ========================================================================== *
 * F7-R1 -- AND THE RESTORE THAT MAKES NO MOVE AT ALL IS STILL THE OLD BRAIN'S
 * (re-review adm-e33f82f008d4, blocking)
 *
 * The gate was on the two MOVES a close makes: the history walk and the
 * conversation press. A viewer opened into a column from the conversation it
 * was launched in makes neither -- `restoreSteps` adds the conversation step
 * only where it differs -- so the close went straight to `putBack` and set the
 * old thread, position and reply target under whatever Brain the server had
 * begun serving, took the focus, and gave up the viewer and its launch. There
 * is no guard pending on this path and no browser move: the only place left to
 * ask is where the page is written to.
 * ========================================================================== */
{
  const moved: [string, string | null][] = [
    ['another instance of the same corpus', 'fixture-corpus@instance-2'],
    ['another corpus', 'other-corpus@instance-1'],
    ['no identity the page can name', null],
  ]
  for (const [what, to] of moved) {
    fresh()
    /* nothing unfinished: this close asks the reader nothing, which is the
       point -- the identity question is not the unsaved-work question */
    const host = makePage()
    const m = mountResults(host.page)
    const l = launch(HERE)                       // launched in the conversation the reader is in
    const id = openViewer({ kind: 'file', item: bytes() }, { kind: 'brain', brainKey: BRAIN }, 's1')
    byHand.push(id)
    placedResults().place(id, l, { kind: 'artifact', ref: A }, 's1')

    served = to                                  // the server begins serving something else
    m.closeResult(id)

    eq(host.r.putBack, [], `F7-R1: a side close in its own conversation puts nothing back after ${what}`)
    eq(host.r.picked, [], 'and presses no conversation, because it never needed one')
    ok(viewerOf(id), 'F7-R1: the viewer is kept, as Stay would keep it')
    ok(launchOf(l.opening), 'and so is its way back')
    eq(host.r.focused, [], 'F7-R1: and the reader’s focus is left where it is')
    eq(host.r.said, [to === null ? BRAIN_UNCONFIRMED : BRAIN_MOVED], 'with the reason said once')
  }
}
{
  /* PRESERVED: under the same Brain that very close completes as before. */
  fresh()
  const host = makePage()
  const m = mountResults(host.page)
  const l = launch(HERE)
  const id = openViewer({ kind: 'file', item: bytes() }, { kind: 'brain', brainKey: BRAIN }, 's1')
  byHand.push(id)
  placedResults().place(id, l, { kind: 'artifact', ref: A }, 's1')
  m.closeResult(id)
  eq(host.r.putBack.map((s) => s.do), ['reading', 'reply', 'draft'], 'preserved: the Place is put back under the same Brain')
  eq(host.r.focused.length, 1, 'focus is put once')
  no(viewerOf(id), 'and only then is the viewer given up')
  eq(host.r.said, [], 'with nothing said about identity')
}

/* ========================================================================== *
 * F7-R2 -- A WALK THE BROWSER HAS NOT ANSWERED YET IS NOT A CLOSE THAT MAY
 * FINISH (re-review adm-e33f82f008d4, blocking)
 *
 * `backTo` asks before it walks, and then hands the history a continuation
 * that asked nothing. `history.go` answers late: the Brain can move while the
 * browser is answering, and the landing then gave up the viewer (F16's leave
 * arm) and ran the whole restore under an identity nobody was being served.
 * The walk is not undone -- it was allowed while the identity was good -- but
 * everything after it is refused.
 *
 * The real deferred walk, over the real history hook, is in
 * `quiet2_result_history_unit.ts`; here the landing and the continuation are
 * separated by hand so that the order itself can be asserted.
 * ========================================================================== */
{
  for (const [what, to] of [['another instance', 'fixture-corpus@instance-2'], ['no identity', null]] as [string, string | null][]) {
    fresh()
    let land: (() => void) | null = null
    const host = makePage({
      /* the browser takes the walk and answers whenever it answers */
      backTo: (_place, then, _stay, begin) => { if (begin && !begin()) return; land = then },
    })
    const m = mountResults(host.page)
    const l = launch(SAVED)
    const id = openViewer({ kind: 'file', item: bytes() }, { kind: 'brain', brainKey: BRAIN }, 'max')
    byHand.push(id)
    placedResults().place(id, l, { kind: 'artifact', ref: A }, 'max')
    m.applyCentre(resultIntent(BRAIN, l.opening, { kind: 'artifact', ref: A }, SAVED))
    m.closeResult(id)
    ok(land, 'the walk was allowed under the Brain the close was pressed under')

    /* the server begins serving something else WHILE the browser answers */
    served = to
    m.applyCentre(null)                          // the pop lands on an ordinary entry
    ok(viewerOf(id), `F7-R2: the landing does not give up the viewer after ${what}`)
    land!()                                      // and then the close's own continuation

    eq(host.r.putBack, [], 'F7-R2: and nothing of the old Place is put back')
    ok(viewerOf(id), 'the viewer is still kept')
    ok(launchOf(l.opening), 'and so is its way back')
    eq(host.r.focused, [], 'with no focus taken by a close that did not finish')
    eq(host.r.said, [to === null ? BRAIN_UNCONFIRMED : BRAIN_MOVED], 'and the reason said once for the whole close')
  }
}
{
  /* PRESERVED: under the same Brain the landing gives the viewer up and the
     continuation puts the Place back, exactly as F16 and B4.3 have it. */
  fresh()
  let land: (() => void) | null = null
  const host = makePage({ backTo: (_place, then, _stay, begin) => { if (begin && !begin()) return; land = then } })
  const m = mountResults(host.page)
  const l = launch(SAVED)
  const id = openViewer({ kind: 'file', item: bytes() }, { kind: 'brain', brainKey: BRAIN }, 'max')
  byHand.push(id)
  placedResults().place(id, l, { kind: 'artifact', ref: A }, 'max')
  m.applyCentre(resultIntent(BRAIN, l.opening, { kind: 'artifact', ref: A }, SAVED))
  m.closeResult(id)
  m.applyCentre(null)
  no(viewerOf(id), 'preserved: landing on an ordinary entry takes the maximised result off the centre (F16)')
  land!()
  eq(host.r.putBack.map((s) => s.do), ['reading', 'reply', 'draft'], 'preserved: and the Place is put back after the move')
  eq(host.r.focused.length, 1, 'focus is put once')
  eq(host.r.said, [], 'with nothing said about identity')
}
{
  /* F7-R2a (independent re-review adm-8f0c09e4f218, blocking): THE CLOSE IS
     THE PAGE'S, NOT THE RENDER'S. The documented host calls `mountResults`
     again on every render, and a render between the reader's Go and the
     browser's pop handed the landing to a mount whose marker was a fresh
     `null`: F16 gave up the viewer and forgot its launch, and the old
     continuation's refusal came too late to keep either. */
  for (const [what, to] of [['another instance', 'fixture-corpus@instance-2'], ['no identity', null]] as [string, string | null][]) {
    fresh()
    let land: (() => void) | null = null
    const host = makePage({ backTo: (_place, then, _stay, begin) => { if (begin && !begin()) return; land = then } })
    const m = mountResults(host.page)
    const l = launch(SAVED)
    const id = openViewer({ kind: 'file', item: bytes() }, { kind: 'brain', brainKey: BRAIN }, 'max')
    byHand.push(id)
    placedResults().place(id, l, { kind: 'artifact', ref: A }, 'max')
    m.applyCentre(resultIntent(BRAIN, l.opening, { kind: 'artifact', ref: A }, SAVED))
    m.closeResult(id)
    ok(land, 'the walk was allowed under the Brain the close was pressed under')

    /* THE PAGE RENDERS while the browser is answering, and the server begins
       serving something else: the landing reaches THIS mount */
    const next = mountResults(host.page)
    served = to
    ok(next.applyCentre(null), `F7-R2b: a refused landing after ${what} is handled, not left to the page`)
    ok(viewerOf(id), 'F7-R2a: and the render does not lose the close: the viewer is kept')
    land!()
    eq(host.r.putBack, [], 'F7-R2a: with nothing of the old Place put back')
    ok(launchOf(l.opening), 'the launch is kept too')
    eq(host.r.focused, [], 'and no focus taken by a close that did not finish')
    eq(host.r.said, [to === null ? BRAIN_UNCONFIRMED : BRAIN_MOVED], 'and the reason said once for the whole close')
  }
}
{
  /* AND THE RENDERS ARE NOT COUNTED: however many mounts the host makes while
     the browser is answering, the landing is still that close's. */
  fresh()
  let land: (() => void) | null = null
  /* the unsaved-work question held open by hand: Go is answered below, after a
     render, into the closure of the render that asked it */
  let go: (() => void) | null = null
  const host = makePage({ backTo: (_place, then, _stay, begin) => { go = () => { if (begin && !begin()) return; land = then } } })
  const m = mountResults(host.page)
  const l = launch(SAVED)
  const id = openViewer({ kind: 'file', item: bytes() }, { kind: 'brain', brainKey: BRAIN }, 'max')
  byHand.push(id)
  placedResults().place(id, l, { kind: 'artifact', ref: A }, 'max')
  m.applyCentre(resultIntent(BRAIN, l.opening, { kind: 'artifact', ref: A }, SAVED))
  m.closeResult(id)
  /* a render while the unsaved-work question is still on screen, and the
     reader then answers Go into the OLD render's own closure */
  mountResults(host.page)
  go!()
  ok(land, 'the walk was allowed by the question the earlier render asked')
  /* and two more renders before the browser answers */
  mountResults(host.page)
  const newest = mountResults(host.page)
  served = 'other-corpus@instance-1'
  ok(newest.applyCentre(null), 'F7-R2a: the newest mount of three still knows whose landing this is')
  ok(viewerOf(id), 'and the viewer is kept')
  land!()
  ok(launchOf(l.opening), 'with its launch')
  eq(host.r.putBack, [], 'and nothing of the old Place put back')
  eq(host.r.said, [BRAIN_MOVED], 'with the reason said once across all of them')
}
{
  /* AND THE MARKER IS ONE CLOSE'S, NOT THE MODULE'S: a refused landing takes
     it, so the NEXT centre move is an ordinary one again (F16). */
  fresh()
  let land: (() => void) | null = null
  const host = makePage({ backTo: (_place, then, _stay, begin) => { if (begin && !begin()) return; land = then } })
  const m = mountResults(host.page)
  const l = launch(SAVED)
  const id = openViewer({ kind: 'file', item: bytes() }, { kind: 'brain', brainKey: BRAIN }, 'max')
  byHand.push(id)
  placedResults().place(id, l, { kind: 'artifact', ref: A }, 'max')
  m.applyCentre(resultIntent(BRAIN, l.opening, { kind: 'artifact', ref: A }, SAVED))
  m.closeResult(id)
  served = 'other-corpus@instance-1'
  ok(m.applyCentre(null), 'the close’s own landing is refused and handled')
  ok(viewerOf(id), 'and the viewer is kept')
  land!()
  const said = host.r.said.length
  /* the reader now moves the centre themselves */
  no(m.applyCentre({ sources: 'all' }), 'F7-R2a: the move after it is nobody’s close, and the page’s own to apply')
  no(viewerOf(id), 'F16 preserved: which takes the kept result off the centre')
  eq(host.r.said.length, said, 'and says nothing more about identity')
}
{
  /* AND IT GIVES UP NOBODY'S VIEWER: the ENTRY is not applied, because the
     landing is this close's and this close may not finish (F7-R2c, independent
     re-review adm-b2c50b80e382) -- AND A DIFFERENT MAXIMISED VIEWER IS NOT
     FORGOTTEN BY IT EITHER (B2, independent re-review adm-e8508cf186c0).
     This assertion used to read `no(viewerOf(other))`, "a viewer that is not
     the close's is left, as it always was": F16's answer for a viewer with no
     column is to forget it with its launch, and a landing that applies nothing
     of the landed centre has no business doing that to a result somebody else
     opened. The B2 section below is the reachable case it cost. */
  fresh()
  let land: (() => void) | null = null
  const host = makePage({ backTo: (_place, then, _stay, begin) => { if (begin && !begin()) return; land = then } })
  const m = mountResults(host.page)
  const l = launch(SAVED)
  const closing = openViewer({ kind: 'file', item: bytes() }, { kind: 'brain', brainKey: BRAIN }, 's1')
  byHand.push(closing)
  placedResults().place(closing, l, { kind: 'artifact', ref: A }, 's1')
  m.applyCentre(resultIntent(BRAIN, l.opening, { kind: 'artifact', ref: A }, SAVED))
  m.closeResult(closing)
  ok(land, 'that close walked the history for its own entry')
  /* something else is maximised over the centre by the time the walk lands */
  const other = openViewer({ kind: 'file', item: bytes() }, { kind: 'brain', brainKey: BRAIN }, 'max')
  byHand.push(other)
  served = 'other-corpus@instance-1'
  ok(m.applyCentre(null), 'F7-R2c: a refused close’s landing is handled whoever is maximised over it')
  ok(viewerOf(other), 'B2: and a viewer that is not the close’s is kept, not forgotten by a landing nothing is applied from')
  land!()
  ok(viewerOf(closing), 'while the refused close still keeps its own viewer')
  ok(launchOf(l.opening), 'and its launch')
  eq(host.r.putBack, [], 'with nothing of the old Place put back')
  eq(host.r.said, [BRAIN_MOVED], 'and the reason said once for the whole close')
}
/* ========================================================================== *
 * F7-R2c -- WHOSE LANDING IT IS, IS THE MARKER'S ANSWER, NOT THE CENTRE'S
 * (independent re-review adm-b2c50b80e382, blocking)
 *
 * The refusal above was asked only where the close's viewer was ALSO the one
 * maximised at the moment the walk landed. The reader can take it off the
 * centre in between: the maximised frame's own Move to column action
 * (`Viewer.tsx` -> `actionsFor.moveTo` -> `Quiet2.tsx` `placeIn` ->
 * `moveViewer`), offered after Go has dismissed the leave question. Nothing is
 * maximised then, so the close was never asked at all, this arm answered
 * `false`, and the documented host's own arms wrote the page back into the OLD
 * Brain's record, source column or Sources browser -- out of the very saved
 * centre that close was walking towards.
 *
 * A column is a deliberate place, so that bypass was reachable by an ordinary,
 * careful reader, with no second host, no lost pop and no timing to arrange.
 * ========================================================================== */
{
  for (const [what, to] of [
    ['another instance', 'fixture-corpus@instance-2'],
    ['another corpus', 'other-corpus@instance-1'],
    ['no identity', null],
  ] as [string, string | null][]) {
    for (const [where, entry] of [
      ['an ordinary entry', null],
      ['the old Brain’s record', { brain: { stack: [{ page: 'record', entry: 'ent-old-record12' }], origin: { from: 'link' } } }],
      ['the old source column', { source: { view: { page: 'source', col: 'old-column' }, reading: null } }],
      ['the old Sources browser', { sources: 'all' }],
    ] as [string, CentreAt][]) {
      fresh()
      let land: (() => void) | null = null
      const host = makePage({ backTo: (_place, then, _stay, begin) => { if (begin && !begin()) return; land = then } })
      const m = mountResults(host.page)
      const l = launch(SAVED)
      const id = openViewer({ kind: 'file', item: bytes() }, { kind: 'brain', brainKey: BRAIN }, 'max')
      byHand.push(id)
      placedResults().place(id, l, { kind: 'artifact', ref: A }, 'max')
      m.applyCentre(resultIntent(BRAIN, l.opening, { kind: 'artifact', ref: A }, SAVED))
      m.closeResult(id)
      ok(land, 'the walk was allowed under the Brain the close was pressed under')

      /* THE READER MOVES THE CLOSING VIEWER INTO A WORKING COLUMN while the
         browser is answering -- the store's own move, as `placeIn` makes it */
      moveViewer(id, 's1')
      no(maximised(), 'nothing is maximised once the closing viewer has a column')

      served = to
      ok(m.applyCentre(entry), `F7-R2c: the landing of a close whose Brain moved to ${what} is refused on ${where}, not left to the page`)
      eq(viewerOf(id)?.place, 's1', 'F7-R2c: and the column the reader chose is kept')
      ok(launchOf(l.opening), 'with the launch it was opened under')
      land!()
      eq(viewerOf(id)?.place, 's1', 'the continuation does not move it either')
      ok(launchOf(l.opening), 'nor release its way back')
      eq(host.r.putBack, [], 'F7-R2c: nothing of the old Place is put back')
      eq(host.r.focused, [], 'and no focus taken by a close that did not finish')
      eq(host.r.said, [to === null ? BRAIN_UNCONFIRMED : BRAIN_MOVED], 'and the reason said once for the whole close')
      /* the walk itself is not undone: the tracker is true to where the browser
         really landed, whatever the page refused to draw (B4.2) */
      eq(host.atNow(), entry, 'and the host’s tracker still holds the entry the browser landed on')
    }
  }
}
{
  /* PRESERVED: the same move under the SAME Brain finishes the close. A
     deliberate column is not a refusal -- it is where the restore puts the
     reader back from. */
  for (const entry of [null, { sources: 'all' }] as CentreAt[]) {
    fresh()
    let land: (() => void) | null = null
    const host = makePage({ backTo: (_place, then, _stay, begin) => { if (begin && !begin()) return; land = then } })
    const m = mountResults(host.page)
    const l = launch(SAVED)
    const id = openViewer({ kind: 'file', item: bytes() }, { kind: 'brain', brainKey: BRAIN }, 'max')
    byHand.push(id)
    placedResults().place(id, l, { kind: 'artifact', ref: A }, 'max')
    m.applyCentre(resultIntent(BRAIN, l.opening, { kind: 'artifact', ref: A }, SAVED))
    m.closeResult(id)
    moveViewer(id, 's1')
    no(m.applyCentre(entry), 'preserved: an unchanged identity leaves the landed entry to the page’s own arms')
    eq(viewerOf(id)?.place, 's1', 'preserved: and the reader’s column is not disturbed by the landing')
    land!()
    eq(host.r.putBack.map((s) => s.do), ['reading', 'reply', 'draft'], 'preserved: the Place is put back after the move')
    eq(host.r.focused.length, 1, 'focus is put once')
    eq(host.r.said, [], 'with nothing said about identity')
    no(viewerOf(id), 'and the close completes: the viewer is given up')
    no(launchOf(l.opening), 'with its launch released')
  }
}
{
  /* AND A MOVED VIEWER WITH NO CLOSE IN FLIGHT IS NOBODY'S LANDING: an
     ordinary move under a moved Brain is still the page's own to apply, and
     says nothing about a close that is not happening (F7-R2a preserved). */
  fresh()
  const host = makePage()
  const m = mountResults(host.page)
  const l = launch(SAVED)
  const id = openViewer({ kind: 'file', item: bytes() }, { kind: 'brain', brainKey: BRAIN }, 'max')
  byHand.push(id)
  placedResults().place(id, l, { kind: 'artifact', ref: A }, 'max')
  moveViewer(id, 's1')
  served = 'other-corpus@instance-1'
  no(m.applyCentre({ sources: 'all' }), 'F7-R2c: no pending close, so the entry is the page’s own however the Brain has moved')
  eq(viewerOf(id)?.place, 's1', 'and the viewer keeps its column, which F16 never owed anything')
  eq(host.r.said, [], 'with nothing said about identity')
}
{
  /* AND AN UNREGISTERED PICTURE MOVED TO A COLUMN IS NOT A RESULT EITHER (N3):
     its close has no launch, so there is nothing to refuse and the landing is
     the page's own, whatever the server is serving. */
  fresh()
  let land: (() => void) | null = null
  const host = makePage({ backTo: (_place, then, _stay, begin) => { if (begin && !begin()) return; land = then } })
  const m = mountResults(host.page)
  const id = openViewer({ kind: 'file', item: bytes() }, { kind: 'post', conversation: SOURCE.conversation, post: SOURCE.post }, 'max')
  byHand.push(id)
  m.closeResult(id)
  no(viewerOf(id), 'N3 preserved: an unregistered maximised viewer closes on the press itself')
  no(land, 'and walks no history of its own')
  served = 'other-corpus@instance-1'
  no(m.applyCentre({ sources: 'all' }), 'N3 preserved: so the next landing is the page’s own')
  eq(host.r.said, [], 'and says nothing about an identity it never had')
}
{
  /* PRESERVED: a render across the same walk under the SAME Brain completes the
     close, and that landing is still the page's own to apply. */
  fresh()
  let land: (() => void) | null = null
  const host = makePage({ backTo: (_place, then, _stay, begin) => { if (begin && !begin()) return; land = then } })
  const m = mountResults(host.page)
  const l = launch(SAVED)
  const id = openViewer({ kind: 'file', item: bytes() }, { kind: 'brain', brainKey: BRAIN }, 'max')
  byHand.push(id)
  placedResults().place(id, l, { kind: 'artifact', ref: A }, 'max')
  m.applyCentre(resultIntent(BRAIN, l.opening, { kind: 'artifact', ref: A }, SAVED))
  m.closeResult(id)
  const next = mountResults(host.page)
  no(next.applyCentre(null), 'preserved: an ordinary landing is still the page’s own arms to apply')
  no(viewerOf(id), 'preserved: and it takes the maximised result off the centre (F16)')
  land!()
  eq(host.r.putBack.map((s) => s.do), ['reading', 'reply', 'draft'], 'preserved: the Place is put back after the move')
  eq(host.r.said, [], 'with nothing said about identity')
}
{
  /* AND A LANDING THAT IS NOT THAT CLOSE'S IS NOT ITS QUESTION EITHER: an
     ordinary move to another entry, with no close in flight, leaves the
     maximised result exactly as F16 has it however the Brain has moved. */
  fresh()
  const host = makePage()
  const m = mountResults(host.page)
  const l = launch(SAVED)
  const id = openViewer({ kind: 'file', item: bytes() }, { kind: 'brain', brainKey: BRAIN }, 'max')
  byHand.push(id)
  placedResults().place(id, l, { kind: 'artifact', ref: A }, 'max')
  served = 'other-corpus@instance-1'
  m.applyCentre(null)
  no(viewerOf(id), 'F16 preserved: a centre move that is nobody’s close still leaves the result entry')
  eq(host.r.said, [], 'and says nothing about a close that is not happening')
}
{
  /* AND AN ORDINARY PICTURE IS NOT A RESULT (N3): nothing registered it, so
     there is no launch to check and its close is the baseline's own. */
  fresh()
  const host = makePage()
  const m = mountResults(host.page)
  const id = openViewer({ kind: 'file', item: bytes() }, { kind: 'post', conversation: SOURCE.conversation, post: SOURCE.post }, 'max')
  byHand.push(id)
  served = 'other-corpus@instance-1'
  m.closeResult(id)
  no(viewerOf(id), 'N3 preserved: an unregistered viewer closes whatever the server is serving')
  eq(host.r.said, [], 'and says nothing about an identity it never had')
}

/* ========================================================================== *
 * B1 -- THE PENDING CLOSE'S GATE IS ITS OWN, AND NO OTHER CLOSE TAKES IT
 * (independent re-review adm-e8508cf186c0, blocking)
 *
 * F7-R2c made the landing's permission the pending close's own marker. The
 * marker is the PAGE's, which is what F7-R2a required of it -- and that made it
 * reachable by every other close the page makes. `run`, the continuation, is
 * reached on the press itself by any close that walks no history, and it
 * cleared the module marker whoever had set it.
 *
 * So the reader has a control for it. Once Go has dismissed the leave question
 * and the maximised frame's own Move to column has put the closing result in a
 * column, nothing is maximised: the work row is no longer inert
 * (`Quiet2.tsx` `!maximised()`), and an ordinary picture open in another column
 * can be closed -- `HOST-INTEGRATION` §1.3 routes every viewer-frame close
 * through `R.closeResult`. That close took the pending close's gate with it,
 * the landing afterwards was nobody's, and the page was written back into the
 * old Brain's record, source column or Sources browser: F7-R2c again, through
 * two ordinary controls.
 * ========================================================================== */
{
  for (const [what, to] of [
    ['another instance', 'fixture-corpus@instance-2'],
    ['another corpus', 'other-corpus@instance-1'],
    ['no identity', null],
  ] as [string, string | null][]) {
    for (const [where, entry] of [
      ['an ordinary entry', null],
      ['the old Brain’s record', { brain: { stack: [{ page: 'record', entry: 'ent-old-record12' }], origin: { from: 'link' } } }],
      ['the old Sources browser', { sources: 'all' }],
    ] as [string, CentreAt][]) {
      fresh()
      let land: (() => void) | null = null
      const host = makePage({ backTo: (_place, then, _stay, begin) => { if (begin && !begin()) return; land = then } })
      const m = mountResults(host.page)
      const l = launch(SAVED)
      const id = openViewer({ kind: 'file', item: bytes() }, { kind: 'brain', brainKey: BRAIN }, 'max')
      byHand.push(id)
      placedResults().place(id, l, { kind: 'artifact', ref: A }, 'max')
      m.applyCentre(resultIntent(BRAIN, l.opening, { kind: 'artifact', ref: A }, SAVED))
      m.closeResult(id)
      ok(land, 'the walk was allowed under the Brain the close was pressed under')
      /* the reader puts the closing result in a column, and then closes an
         ORDINARY PICTURE in another one -- a viewer this contract never
         registered (N3), with no launch, no identity and no history move */
      moveViewer(id, 's1')
      const picture = openViewer({ kind: 'file', item: bytes(B) }, { kind: 'post', conversation: SOURCE.conversation, post: SOURCE.post }, 's2')
      byHand.push(picture)
      m.closeResult(picture)
      no(viewerOf(picture), 'the ordinary picture closes on the press, as it always did')

      served = to
      ok(m.applyCentre(entry), `B1: the pending close's landing on ${where} is still refused after an ordinary close, with the Brain moved to ${what}`)
      eq(viewerOf(id)?.place, 's1', 'B1: and the column the reader chose is kept')
      ok(launchOf(l.opening), 'with the launch it was opened under')
      land!()
      eq(viewerOf(id)?.place, 's1', 'the continuation does not move it either')
      ok(launchOf(l.opening), 'nor release its way back')
      eq(host.r.putBack, [], 'B1: nothing of the old Place is put back')
      eq(host.r.focused, [], 'and no focus taken by a close that did not finish')
      eq(host.r.said, [to === null ? BRAIN_UNCONFIRMED : BRAIN_MOVED], 'and the reason said once for the whole close')
      eq(host.atNow(), entry, 'and the host’s tracker still holds the entry the browser landed on')
    }
  }
}
{
  /* PRESERVED: the same two closes under the SAME Brain finish the first one.
     An ordinary close is not a refusal and does not become one. */
  fresh()
  let land: (() => void) | null = null
  const host = makePage({ backTo: (_place, then, _stay, begin) => { if (begin && !begin()) return; land = then } })
  const m = mountResults(host.page)
  const l = launch(SAVED)
  const id = openViewer({ kind: 'file', item: bytes() }, { kind: 'brain', brainKey: BRAIN }, 'max')
  byHand.push(id)
  placedResults().place(id, l, { kind: 'artifact', ref: A }, 'max')
  m.applyCentre(resultIntent(BRAIN, l.opening, { kind: 'artifact', ref: A }, SAVED))
  m.closeResult(id)
  moveViewer(id, 's1')
  const picture = openViewer({ kind: 'file', item: bytes(B) }, { kind: 'post', conversation: SOURCE.conversation, post: SOURCE.post }, 's2')
  byHand.push(picture)
  m.closeResult(picture)
  no(m.applyCentre({ sources: 'all' }), 'preserved: an unchanged identity leaves the landed entry to the page’s own arms')
  land!()
  eq(host.r.putBack.map((s) => s.do), ['reading', 'reply', 'draft'], 'preserved: the Place is put back after the move')
  no(viewerOf(id), 'preserved: and the close completes')
  no(launchOf(l.opening), 'with its launch released')
  eq(host.r.said, [], 'with nothing said about identity')
}
{
  /* AND ONE CLOSE'S WALK AT A TIME: a second close pressed while a walk is
     outstanding makes no claim on the landing. `centreHistory` refuses a second
     centre move while one of its own is in flight (`moving`), so claiming would
     buy that close nothing and cost the pending one its gate. */
  fresh()
  let tracked: CentreAt = null
  let land: (() => void) | null = null
  let refusedClaims = 0
  const host = makePage({
    centreAt: () => tracked,
    backTo: (_place, then, _stay, begin) => { if (begin && !begin()) { refusedClaims++; return } land = then },
  })
  const m = mountResults(host.page)
  const first = launch(SAVED)
  const second = launch(HERE)
  const a = openViewer({ kind: 'file', item: bytes() }, { kind: 'brain', brainKey: BRAIN }, 'max')
  const b = openViewer({ kind: 'file', item: bytes(B) }, { kind: 'brain', brainKey: BRAIN }, 's2')
  byHand.push(a, b)
  placedResults().place(a, first, { kind: 'artifact', ref: A }, 'max')
  placedResults().place(b, second, { kind: 'artifact', ref: B }, 's2')
  tracked = resultIntent(BRAIN, first.opening, { kind: 'artifact', ref: A }, SAVED)
  m.closeResult(a)
  ok(land, 'the first close walked the history for its own entry')
  /* the reader moves the first result into a column and maximises the second,
     whose entry the page's tracker now holds: its close plans a history move of
     its own -- while the first walk is still outstanding */
  moveViewer(a, 's1')
  moveViewer(b, 'max')
  tracked = resultIntent(BRAIN, second.opening, { kind: 'artifact', ref: B }, HERE)
  m.closeResult(b)
  eq(refusedClaims, 1, 'B1: the second close claims no landing while another close holds one')
  ok(viewerOf(b), 'and gives up nothing: nothing moved, so nothing is left')
  ok(launchOf(second.opening), 'nor its way back')
  served = 'other-corpus@instance-1'
  ok(m.applyCentre(null), 'B1: so the landing is still the first close’s, and is refused')
  ok(viewerOf(a), 'with the first close’s viewer kept')
  ok(launchOf(first.opening), 'and its launch')
  eq(host.r.putBack, [], 'and nothing of either Place put back')
}

/* ========================================================================== *
 * B1-R2 -- THE GATE IS ONE PRESS OF CLOSE'S, NOT THE VIEWER'S
 * (independent re-review adm-012c2c2a3987, blocking)
 *
 * B1 made the marker name the viewer whose close is walking, which rejects
 * every OTHER viewer's close -- and cannot tell two closes of the SAME viewer
 * apart. The reader has two, through the controls B1 itself describes: Close
 * and Go on the maximised result starts the walk; the frame's own Move to
 * column puts that result in a column (which is what makes the work row live
 * again); and the column frame's Close is a second close of the same viewer.
 * It walks no history, so its continuation runs on the press itself, and
 * `walking.viewer === viewer` matched: the FIRST press's gate went with it, the
 * pop the browser had not answered yet landed as nobody's, and the page was
 * written back into the old Brain's record, source column or Sources browser.
 * Each press is its own operation, and the gate belongs to the operation.
 * ========================================================================== */
{
  for (const [what, to] of [
    ['another instance', 'fixture-corpus@instance-2'],
    ['another corpus', 'other-corpus@instance-1'],
    ['no identity', null],
  ] as [string, string | null][]) {
    for (const [where, entry] of [
      ['the old Brain’s record', { brain: { stack: [{ page: 'record', entry: 'ent-old-record12' }], origin: { from: 'link' } } }],
      ['the old source column', { source: { view: { page: 'source', col: 'old-column' }, reading: null } }],
      ['the old Sources browser', { sources: 'all' }],
    ] as [string, CentreAt][]) {
      fresh()
      let land: (() => void) | null = null
      const host = makePage({ backTo: (_place, then, _stay, begin) => { if (begin && !begin()) return; land = then } })
      const m = mountResults(host.page)
      const l = launch(SAVED)
      const id = openViewer({ kind: 'file', item: bytes() }, { kind: 'brain', brainKey: BRAIN }, 'max')
      byHand.push(id)
      placedResults().place(id, l, { kind: 'artifact', ref: A }, 'max')
      m.applyCentre(resultIntent(BRAIN, l.opening, { kind: 'artifact', ref: A }, SAVED))
      m.closeResult(id)
      ok(land, 'the walk was allowed under the Brain the close was pressed under')
      /* the reader moves the closing result into a column, and presses the
         column frame's own Close -- the SAME viewer, a second operation, with
         no history move of its own */
      moveViewer(id, 's1')
      no(maximised(), 'nothing is maximised once the closing viewer has a column')
      served = to
      m.closeResult(id)
      ok(viewerOf(id), 'B1-R2: the second close is refused too, and keeps the viewer')
      ok(launchOf(l.opening), 'with its launch')
      eq(host.r.putBack, [], 'and puts no Place back')
      eq(host.r.focused, [], 'and takes no focus')

      ok(m.applyCentre(entry), `B1-R2: and the first close's landing on ${where} is still ITS own, and refused, with the Brain moved to ${what}`)
      eq(viewerOf(id)?.place, 's1', 'B1-R2: the column the reader chose is kept')
      ok(launchOf(l.opening), 'with the launch it was opened under')
      land!()
      eq(viewerOf(id)?.place, 's1', 'the continuation does not move it either')
      ok(launchOf(l.opening), 'nor release its way back')
      eq(host.r.putBack, [], 'B1-R2: nothing of the old Place is put back')
      eq(host.r.focused, [], 'and no focus taken by a close that did not finish')
      /* two presses, each refused on its own and each saying so once: the words
         are per close, as they always were (F7) */
      eq(host.r.said, [to === null ? BRAIN_UNCONFIRMED : BRAIN_MOVED, to === null ? BRAIN_UNCONFIRMED : BRAIN_MOVED], 'and each press says its own reason once')
      eq(host.atNow(), entry, 'and the host’s tracker still holds the entry the browser landed on')
    }
  }
}
{
  /* PRESERVED: the same two presses under the SAME Brain finish the close --
     twice over, which is what two accepted closes of one viewer are. A later
     press of Close is not a refusal and does not become one. The launch's Place
     is the conversation the reader is in, so both restores are the same three
     steps and the second press's own column restore is comparable. */
  fresh()
  let land: (() => void) | null = null
  const host = makePage({ backTo: (_place, then, _stay, begin) => { if (begin && !begin()) return; land = then } })
  const m = mountResults(host.page)
  const l = launch(HERE)
  const id = openViewer({ kind: 'file', item: bytes() }, { kind: 'brain', brainKey: BRAIN }, 'max')
  byHand.push(id)
  placedResults().place(id, l, { kind: 'artifact', ref: A }, 'max')
  m.applyCentre(resultIntent(BRAIN, l.opening, { kind: 'artifact', ref: A }, HERE))
  m.closeResult(id)
  moveViewer(id, 's1')
  m.closeResult(id)
  no(viewerOf(id), 'preserved: the second close completes and gives up the viewer')
  no(launchOf(l.opening), 'with its launch released')
  no(m.applyCentre({ sources: 'all' }), 'preserved: an unchanged identity leaves the landed entry to the page’s own arms')
  land!()
  eq(host.r.putBack.map((s) => s.do), ['reading', 'reply', 'draft', 'reading', 'reply', 'draft'], 'preserved: each accepted close puts the Place back')
  eq(host.r.said, [], 'with nothing said about identity')
}

/* ========================================================================== *
 * B2 -- A LANDING THE PAGE DOES NOT APPLY GIVES UP NOBODY'S RESULT
 * (independent re-review adm-e8508cf186c0, blocking)
 *
 * F7-R2c left a DIFFERENT maximised viewer to F16 "exactly as it always was",
 * and F16's two answers are not alike. From a column, the viewer goes back to
 * it and keeps everything. With no column -- which is every result the reader
 * has just pressed and had opened maximised -- it is FORGOTTEN with its launch:
 * the inspection, the conversation, thread, position, reply target and draft
 * key it would have gone back to, and the pending decision it was opened to
 * answer. In a landing whose whole meaning is that NOTHING of the landed centre
 * is applied, and with the one notice spoken about the other close's Brain.
 * ========================================================================== */
{
  for (const [what, to] of [
    ['another instance', 'fixture-corpus@instance-2'],
    ['another corpus', 'other-corpus@instance-1'],
    ['no identity', null],
  ] as [string, string | null][]) {
    for (const [where, entry] of [
      ['an ordinary entry', null],
      ['the old source column', { source: { view: { page: 'source', col: 'old-column' }, reading: null } }],
    ] as [string, CentreAt][]) {
      fresh()
      let land: (() => void) | null = null
      const host = makePage({ backTo: (_place, then, _stay, begin) => { if (begin && !begin()) return; land = then } })
      const m = mountResults(host.page)
      const mine = launch(SAVED)
      const id = openViewer({ kind: 'file', item: bytes() }, { kind: 'brain', brainKey: BRAIN }, 'max')
      byHand.push(id)
      placedResults().place(id, mine, { kind: 'artifact', ref: A }, 'max')
      m.applyCentre(resultIntent(BRAIN, mine.opening, { kind: 'artifact', ref: A }, SAVED))
      m.closeResult(id)
      ok(land, 'the walk was allowed under the Brain the close was pressed under')
      moveViewer(id, 's1')
      /* and the reader opens ANOTHER result, maximised, with its own launch and
         the decision it was opened to answer -- accepted, and nothing to do
         with the close the browser has not answered yet */
      const theirs = launch(HERE, asking())
      const other = openViewer({ kind: 'file', item: bytes(B) }, { kind: 'brain', brainKey: BRAIN }, 'max')
      byHand.push(other)
      placedResults().place(other, theirs, { kind: 'artifact', ref: B }, 'max')
      eq(maximised()?.id, other, 'the freshly opened result is what is over the centre')

      served = to
      ok(m.applyCentre(entry), `B2: the landing on ${where} is refused with the Brain moved to ${what}`)
      ok(viewerOf(other), 'B2: and the separately opened result is kept, not forgotten')
      eq(viewerOf(other)?.place, 'max', 'on the centre it was opened on, since nothing of the landing was applied')
      eq(launchOf(theirs.opening)?.decision?.question, ASK, 'B2: with its launch and the decision it was opened to answer')
      land!()
      ok(viewerOf(other), 'the continuation of the refused close does not take it either')
      ok(launchOf(theirs.opening), 'nor its way back')
      eq(viewerOf(id)?.place, 's1', 'while the refused close keeps its own viewer in its column')
      ok(launchOf(mine.opening), 'and its launch')
      eq(host.r.putBack, [], 'with nothing of the old Place put back')
      eq(host.r.said, [to === null ? BRAIN_UNCONFIRMED : BRAIN_MOVED], 'and one notice, about the close’s own Brain')
    }
  }
}
{
  /* PRESERVED: a viewer maximised FROM a column still goes back to it on a
     refused landing -- that keeps its renderer state and its launch too, and is
     where its own frame put it. */
  fresh()
  let land: (() => void) | null = null
  const host = makePage({ backTo: (_place, then, _stay, begin) => { if (begin && !begin()) return; land = then } })
  const m = mountResults(host.page)
  const mine = launch(SAVED)
  const id = openViewer({ kind: 'file', item: bytes() }, { kind: 'brain', brainKey: BRAIN }, 'max')
  byHand.push(id)
  placedResults().place(id, mine, { kind: 'artifact', ref: A }, 'max')
  m.applyCentre(resultIntent(BRAIN, mine.opening, { kind: 'artifact', ref: A }, SAVED))
  m.closeResult(id)
  moveViewer(id, 's1')
  const theirs = launch(HERE)
  const other = openViewer({ kind: 'file', item: bytes(B) }, { kind: 'brain', brainKey: BRAIN }, 's2')
  byHand.push(other)
  placedResults().place(other, theirs, { kind: 'artifact', ref: B }, 's2')
  moveViewer(other, 'max')
  served = 'other-corpus@instance-1'
  ok(m.applyCentre(null), 'the landing is refused')
  eq(viewerOf(other)?.place, 's2', 'F16 preserved: a viewer maximised from a column goes back to it')
  ok(launchOf(theirs.opening), 'with its launch')
  land!()
  eq(viewerOf(id)?.place, 's1', 'and the refused close still keeps its own viewer')
}
/* ========================================================================== *
 * B2-R2 -- AND AN APPLIED LANDING DISCARDS NOBODY'S RESULT EITHER
 * (independent re-review adm-012c2c2a3987, blocking)
 *
 * B2 above answered the REFUSED landing, and the refusal is not what the loss
 * depended on. With the identity unchanged, A's landing IS applied -- and in
 * the interval between Go and the browser's answer the reader can move A into a
 * column and press another result, which the opener accepts, places maximised
 * and REPORTS AS OPENED. It has no column, so F16 forgot it with its launch:
 * the inspection the reader had just been handed, its renderer state, and its
 * way back -- the conversation, thread, position, reply target, reading
 * position and draft key they pressed it from, and the decision it was opened
 * to answer. Nothing said so: this close's one notice is about its own Brain,
 * and nothing offered that result a return.
 *
 * So where a landing belongs to a pending close, a maximised result that is NOT
 * that close's is kept. The reader's OWN Back or Forward is nobody's close and
 * leaves F16 exactly as it was: the block after this one is that control.
 * ========================================================================== */
{
  for (const [where, entry] of [
    ['an ordinary entry', null],
    ['the saved Sources browser', { sources: 'all' }],
  ] as [string, CentreAt][]) {
    fresh()
    let land: (() => void) | null = null
    const host = makePage({ backTo: (_place, then, _stay, begin) => { if (begin && !begin()) return; land = then } })
    const m = mountResults(host.page)
    const mine = launch(SAVED)
    const id = openViewer({ kind: 'file', item: bytes() }, { kind: 'brain', brainKey: BRAIN }, 'max')
    byHand.push(id)
    placedResults().place(id, mine, { kind: 'artifact', ref: A }, 'max')
    m.applyCentre(resultIntent(BRAIN, mine.opening, { kind: 'artifact', ref: A }, SAVED))
    m.closeResult(id)
    ok(land, 'the walk was allowed, and the browser has not answered it yet')
    moveViewer(id, 's1')
    /* and the reader presses ANOTHER result, which is opened maximised with the
       decision it was opened to answer and the place they pressed it from */
    const theirs = launch(HERE, asking())
    const other = openViewer({ kind: 'file', item: bytes(B) }, { kind: 'brain', brainKey: BRAIN }, 'max')
    byHand.push(other)
    placedResults().place(other, theirs, { kind: 'artifact', ref: B }, 'max')
    eq(maximised()?.id, other, 'the freshly opened result is what is over the centre')

    no(m.applyCentre(entry), `B2-R2: the landing on ${where} is applied -- the identity never moved`)
    ok(viewerOf(other), 'B2-R2: and the separately opened result is kept, not forgotten by somebody else’s close')
    eq(viewerOf(other)?.place, 'max', 'on the centre the reader opened it over')
    eq(launchOf(theirs.opening)?.decision?.question, ASK, 'B2-R2: with its launch and the decision it was opened to answer')
    land!()
    ok(viewerOf(other), 'the continuation of the completing close does not take it either')
    ok(launchOf(theirs.opening), 'nor its way back')
    /* and A's own close completes in full: its Place put back, its focus taken
       once, its viewer and launch given up */
    eq(host.r.putBack.map((s) => s.do), ['reading', 'reply', 'draft'], 'B2-R2: the close that landed still puts its own Place back')
    eq(host.r.focused.length, 1, 'and takes its own return focus once')
    no(viewerOf(id), 'and gives up its own viewer')
    no(launchOf(mine.opening), 'with its own launch')
    eq(host.r.said, [], 'with nothing said about identity')
    /* THE KEPT RESULT'S OWN WAY BACK: its close is frame-only now that the
       centre has moved on, and that is what offers the explicit return bar --
       out of the launch this landing did not throw away */
    eq(host.r.returns, [], 'B2-R2: no bar is offered while the reader is still looking at it')
    m.closeResult(other)
    eq(host.r.returns.map((l) => l.opening), [theirs.opening], 'B2-R2: and its own close offers the way back it kept')
    no(viewerOf(other), 'closing it is still an ordinary close')
  }
}
{
  /* AND F16 IS UNCHANGED FOR THE READER'S OWN NAVIGATION: a centre move that is
     nobody's close -- Back, Forward, a press -- still takes a maximised result
     with no column off the centre, exactly as it always did. */
  fresh()
  const host = makePage()
  const m = mountResults(host.page)
  const theirs = launch(HERE)
  const other = openViewer({ kind: 'file', item: bytes(B) }, { kind: 'brain', brainKey: BRAIN }, 'max')
  byHand.push(other)
  placedResults().place(other, theirs, { kind: 'artifact', ref: B }, 'max')
  no(m.applyCentre(null), 'F16 preserved: an entry nobody is closing towards is the page’s own arms’ to finish')
  no(viewerOf(other), 'F16 preserved: and takes a maximised result with no column off the centre')
  no(launchOf(theirs.opening), 'with its launch, as it always did')
  eq(host.r.said, [], 'with nothing said about identity')
}
{
  /* AND A CLOSE'S OWN VIEWER IS STILL GIVEN UP BY ITS APPLIED LANDING: the
     maximised result the landing takes off the centre is the closing one, and
     F16's answer for it is unchanged (the continuation's own forget is then the
     second half of the same close). */
  fresh()
  let land: (() => void) | null = null
  const host = makePage({ backTo: (_place, then, _stay, begin) => { if (begin && !begin()) return; land = then } })
  const m = mountResults(host.page)
  const mine = launch(SAVED)
  const id = openViewer({ kind: 'file', item: bytes() }, { kind: 'brain', brainKey: BRAIN }, 'max')
  byHand.push(id)
  placedResults().place(id, mine, { kind: 'artifact', ref: A }, 'max')
  m.applyCentre(resultIntent(BRAIN, mine.opening, { kind: 'artifact', ref: A }, SAVED))
  m.closeResult(id)
  no(m.applyCentre(null), 'F16 preserved: an applied landing is the page’s own arms’ to finish')
  no(viewerOf(id), 'F16 preserved: and takes the closing result off the centre')
  no(launchOf(mine.opening), 'with its launch, as it always did')
  land!()
  eq(host.r.said, [], 'with nothing said about identity')
}

fresh()
console.log(`quiet2 result mount: ${checks} checks ok`)
