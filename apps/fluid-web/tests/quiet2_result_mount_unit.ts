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
import { beginOpening, clearLaunches, holdLaunch, launchOf, type LaunchContext, type LaunchPlace } from '../src/quiet2/results/launch'
import { resultIntent } from '../src/quiet2/results/history'
import { closeSteps, type PlaceStep } from '../src/quiet2/results/hostOpen'
import { destinationOfRef, type ResolvedRef, type ResultDestination } from '../src/quiet2/results/targets'
import { leaves, openResultTarget, type Opened } from '../src/quiet2/results/opener'
import type { CentreAt } from '../src/quiet2/address'
import { heldItem } from '../src/quiet2/brain/logic'
import { closeViewer, maximised, openViewer, viewerOf } from '../src/quiet2/viewer/viewers'

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
const postDest = (): ResultDestination => ({ ...dest(), target: { kind: 'post', ...SOURCE }, opens: 'post' })
const recordDest = (): ResultDestination => ({ ...dest(), target: { kind: 'record', ref: 'ent-record12345' }, opens: 'record' })
const convDest = (): ResultDestination => ({ ...dest(), target: { kind: 'record', ref: 'ent-conversatn1' }, opens: 'conversation' })

const launch = (place: LaunchPlace = HERE, decision: LaunchContext['decision'] = null): LaunchContext => holdLaunch({
  opening: beginOpening(), brainKey: BRAIN, place, thread: null,
  reading: { scroll: 417, offset: 12 }, reply: 'ent-reply12345', draft: 'conversation:ent-origin',
  focus: { control: 'needs-ref:' + A, fallback: { kind: 'conversation' } }, decision,
})
const asking = (): LaunchContext['decision'] => ({ form: null, question: ASK, item: 'item-1', ref: A, role: null })

/** the server answering that the exact reference asked for is held now */
const stillHeld = async (ref: string): Promise<FreshArtifact> =>
  ({ how: 'held', file: { ...HELD, ref, treatment: { view: 'text' } } })

/** viewers this suite opened by hand, so the real store starts each case clean */
const byHand: string[] = []
function fresh() {
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
    brainKey: () => BRAIN,
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
    /* the guarded `backTo`, with all three of the guard's ends (B4.3) */
    backTo: (place, then, stay) => {
      r.back.push(place)
      guarded(() => { conversation = place.conversation ?? conversation; at = place.centre; then() }, stay)
    },
    pickConversation: (k, then, stay) => { r.picked.push(k); guarded(() => { conversation = k; then?.() }, stay); return true },
    openPost: (c, p, done) => { r.posts.push(`${c}/${p}`); guarded(() => done('completed'), () => done({ how: 'cancelled' })) },
    record: (entry, go, stay) => { r.picked.push(`record:${entry}`); guarded(go, stay) },
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

const settle = () => new Promise<void>((done) => { setImmediate(done) })

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
  host.answer('go')
  eq(settled.map((o) => o.what), ['opened'], 'F09: and the arrival is reported when the reader actually arrives')
  eq(m.dockStep(settled[0]), 'arm', 'which is when the way back is owed')
}
{
  /* a page with nothing unfinished moves on the press itself */
  fresh()
  const host = makePage()
  const m = mountResults(host.page)
  const r = m.openResult(recordDest(), launch())
  eq(r, { what: 'opened', how: 'record', where: 'max' }, 'with no question to ask, the record page is entered on the press')
}
{
  /* the conversation route, blocked and then answered -- both ends */
  fresh()
  const stayed: Opened[] = []
  const host = makePage({ asks: () => true })
  const m = mountResults(host.page)
  const r = m.openResult(convDest(), launch(), (o) => stayed.push(o))
  no(leaves(r), 'a guarded conversation press has not arrived either')
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

fresh()
console.log(`quiet2 result mount: ${checks} checks ok`)
