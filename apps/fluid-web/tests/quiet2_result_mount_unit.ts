/* THE INDEPENDENT RE-REVIEW'S FALSIFIERS, AGAINST THE REAL COMPOSITION
 * (adm-263df1ccb512: B1/F04, B3/F09, B4/F10, F12-F16 and F19).
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
 *   - the REAL bound read (`results/refRead.ts`), over an injected `fetch`, so
 *     the route, its answer shape and its failure are this build's.
 *
 * What is synthetic is only what a page supplies -- its React state, as
 * `ResultPage`. There is no DOM, no Brain, no server, no byte and no
 * rendering, and none is claimed.
 *
 * THE GUARD IS REAL HERE TOO. `makePage` holds one unsaved-work question open
 * exactly as `Quiet2.tsx`'s `guarded`/`setLeave` does, so what is measured is
 * the ASYNCHRONOUS and BLOCKED paths -- a pending question, Stay, a thread read
 * that fails, a column chosen after the press -- and not a synchronous stub
 * that cannot be wrong. */
import assert from 'node:assert/strict'
import { mountResults, placedResults, resetPlacedResults, type ColumnChoice, type ResultPage } from '../src/quiet2/results/mount'
import { refIn, refNow } from '../src/quiet2/results/refRead'
import { beginOpening, clearLaunches, holdLaunch, launchOf, type LaunchContext, type LaunchPlace } from '../src/quiet2/results/launch'
import { resultIntent } from '../src/quiet2/results/history'
import { closeSteps, type PlaceStep } from '../src/quiet2/results/hostOpen'
import { destinationOfRef, type ResolvedRef, type ResultDestination } from '../src/quiet2/results/targets'
import { leaves, type Opened } from '../src/quiet2/results/opener'
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
  centre: CentreAt[]; replaced: (CentreAt | null)[]; back: LaunchPlace[]
  picked: string[]; posts: string[]; said: string[]; focused: unknown[]
  putBack: PlaceStep[]; returns: LaunchContext[]; leftOn: LaunchPlace[]
}

function makePage(over: Partial<ResultPage> & { asks?: () => boolean } = {}) {
  const r: Seen = { centre: [], replaced: [], back: [], picked: [], posts: [], said: [], focused: [], putBack: [], returns: [], leftOn: [] }
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
    columns: () => [],
    freeColumn: () => null,
    choose: (ask) => { choice = ask },
    invoker: () => null,
    hasControl: () => false,
    focus: (c, invoker) => { r.focused.push({ choice: c, invoker }) },
    centreGo: (to) => { at = to; r.centre.push(to) },
    centreReplace: (to) => { at = to; r.replaced.push(to) },
    backTo: (place, then) => {
      r.back.push(place)
      guarded(() => { conversation = place.conversation ?? conversation; at = place.centre; then() })
    },
    pickConversation: (k, then, stay) => { r.picked.push(k); guarded(() => { conversation = k; then?.() }, stay); return true },
    openPost: (c, p, done) => { r.posts.push(`${c}/${p}`); guarded(() => done('completed'), () => done({ how: 'cancelled' })) },
    record: (entry, go, stay) => { r.picked.push(`record:${entry}`); guarded(go, stay) },
    goToPost: (c, p) => { r.posts.push(`source:${c}/${p}`) },
    heldItem: (ref, about) => heldItem(ref, about),
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
 * B1 / F04 -- the delayed fresh read must refuse another identity
 * ========================================================================== */
{
  fresh()
  let give: ((r: ResolvedRef | null) => void) | null = null
  const read: string[] = []
  const settled: Opened[] = []
  const host = makePage({
    refNow: (ask, ref) => { read.push(`${ask}:${ref}`); return new Promise<ResolvedRef | null>((resolve) => { give = resolve }) },
  })
  const m = mountResults(host.page)
  const l = launch(HERE, asking())
  const press = m.openResult(dest(A), l, (o) => settled.push(o))
  eq(press, { what: 'leaving', how: 'file' }, 'F04: while the press is being read again, nothing is opened and nothing is left')
  eq(m.dockStep(press), 'wait', 'and the dock arms nothing yet')
  eq(read, [`${ASK}:${A}`], 'the read is by the request the row was drawn from, for the exact reference')
  /* the read answers -- late -- about ANOTHER Admission */
  give!(fileRef(B))
  await settle()
  no(maximised(), 'F04: A DELAYED READ ABOUT ANOTHER IDENTITY OPENS NOTHING (B1)')
  eq(settled.map((o) => o.what), ['refused'], 'this press is refused, exactly as the synchronous branch refuses it')
  eq(settled[0] && 'why' in settled[0] ? settled[0].why : null,
    'That read answered about something else, so nothing was opened.', 'in the same words')
  no(settled.some(leaves), 'so it is never a departure')
  eq(host.r.centre, [], 'and no history entry is owed for something that was not opened')
}
{
  /* the same read answering about the SAME thing still opens it: the guard is
     an identity check, not a refusal of delayed reads */
  fresh()
  let give: ((r: ResolvedRef | null) => void) | null = null
  const settled: Opened[] = []
  const host = makePage({ refNow: () => new Promise<ResolvedRef | null>((resolve) => { give = resolve }) })
  const m = mountResults(host.page)
  m.openResult(dest(A), launch(HERE, asking()), (o) => settled.push(o))
  give!(fileRef(A))
  await settle()
  eq(settled.map((o) => o.what), ['opened'], 'a delayed read about the thing that was asked for opens it')
  eq(maximised()?.content.kind, 'file', 'in the page’s own viewer')
}
{
  /* and a read that cannot answer leaves the row in hand standing (unchecked) */
  fresh()
  const settled: Opened[] = []
  const host = makePage({ refNow: () => Promise.resolve(null) })
  const m = mountResults(host.page)
  m.openResult(dest(A), launch(HERE, asking()), (o) => settled.push(o))
  await settle()
  eq(settled.map((o) => o.what), ['opened'], 'a bound read that answers nothing is unchecked, not a refusal')
}
{
  /* a press with NO request behind it has nothing to read by, and says so by
     opening what it has -- which is what `unchecked` means */
  fresh()
  const asked: string[] = []
  const host = makePage({ refNow: (ask, ref) => { asked.push(ask + ref); return Promise.resolve(null) } })
  const m = mountResults(host.page)
  const r = m.openResult(dest(A), launch(HERE, null))
  eq(r.what, 'opened', 'a chooser or Brain-record press opens what it has')
  eq(asked, [], 'and no read is invented for it')
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
  const r = m.openResult(fromPost(A), l)
  eq(r, { what: 'opened', how: 'file', where: 'max' }, 'an artifact opened from a post is maximised')
  eq(host.r.centre.length, 1, 'and owes exactly one history entry')
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
  eq(host.r.centre[0]?.result?.target, { kind: 'artifact', ref: A }, 'F12: a Brain-sourced result is not target-less')
}

/* ========================================================================== *
 * B4 / F13 -- a reload resolves against the Place the entry saved
 * ========================================================================== */
{
  fresh()
  const host = makePage({ destinationOfTarget: () => dest(A) })
  const m = mountResults(host.page)
  /* the entry a reload leaves behind: no live launch for its opening */
  const entry = resultIntent(BRAIN, 800, { kind: 'artifact', ref: A }, SAVED)
  no(launchOf(800), 'its launch did not survive the reload')
  m.applyCentre(entry)
  const shown = maximised()
  ok(shown, 'F13: the target is resolved again rather than leaving a blank centre')
  const l = placedResults().launchOf(shown!.id)
  eq(l?.place, SAVED, 'F13: AND IT OWES THE PLACE THE ENTRY SAVED (B4), not wherever the reader is now')
  no(l?.place.conversation === HERE.conversation, 'the current conversation is not substituted for the stored one')
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
  const id = maximised()!.id
  m.applyCentre(resultIntent(BRAIN, l.opening, { kind: 'artifact', ref: A }, HERE))
  eq(maximised()?.id, id, 'landing on a live entry shows the same viewer, not another')
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
 * B4 / F16 -- leaving a result entry takes the overlay with it
 * ========================================================================== */
{
  fresh()
  const host = makePage()
  const m = mountResults(host.page)
  const l = launch()
  m.openResult(dest(A), l)
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
 * B4 / F19 -- the fresh read is a reader that exists
 * ========================================================================== */
{
  fresh()
  const host = makePage({ refNow: () => Promise.resolve(null) })
  const m = mountResults(host.page)
  ok(m.host.read, 'F19: the host has a read adapter')
  assert.doesNotThrow(() => m.host.read!(A, () => {}), 'F19: AND IT RUNS (B4): no undefined reader, no ReferenceError')
  checks++
  eq(m.host.read!(A, () => {}), { how: 'unchecked' }, 'with nothing to read by, it says so rather than pretending')
  const without = mountResults(makePage().page)
  no(without.host.read, 'a host that wires no reader simply has none, and the opener is unchecked')
}
{
  /* the reader itself, against the route this build really serves */
  const answer = {
    about: [{
      id: ASK,
      subject: [{ id: 'ent-other12345', type: 'post', available: true, state: 'ok', opens: 'post' }],
      evidence: [{ id: A, type: 'file', available: false, state: 'purged', opens: null, why: 'Its contents were purged from this Brain.' }],
    }],
  }
  const asked: string[] = []
  const fakeFetch = (async (url: unknown) => {
    asked.push(String(url))
    return { ok: true, json: async () => answer } as unknown as Response
  }) as typeof fetch
  const got = await refNow(ASK, A, fakeFetch as never)
  eq(asked, [`/fluid/api/needs-you/about?ids=${encodeURIComponent(ASK)}`], 'F19: it reads the route that exists, by the request the row was drawn from')
  eq(got?.state, 'purged', 'and takes the server’s own word for the reference now')
  eq(destinationOfRef(got!).availability, 'purged', 'which the opener reads as unavailable, so nothing is opened')
  eq(refIn(answer.about[0] as never, 'ent-nothing1234'), null, 'a reference the fresh answer no longer names is not invented')
  eq((await refNow(null, A, fakeFetch as never)), null, 'and a press with no request to read by asks nothing')
  eq(asked.length, 1, 'literally nothing: no second read')
}
{
  /* a failed read never refuses the press: the row in hand stands */
  fresh()
  const settled: Opened[] = []
  const host = makePage({ refNow: () => Promise.reject(new Error('offline')) })
  const m = mountResults(host.page)
  m.openResult(dest(A), launch(HERE, asking()), (o) => settled.push(o))
  await settle()
  eq(settled.map((o) => o.what), ['opened'], 'a bound read that failed leaves the descriptor in hand standing')
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
  eq(r, { what: 'placing' }, 'while the reader is choosing a column, nothing has been opened')
  eq(m.dockStep(r), 'wait', 'and the dock waits')
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
  host.chooser()!.decide('s2')
  eq(settled, [{ what: 'opened', how: 'file', where: 's2' }], 'the column they chose is where it went')
  eq(host.r.centre, [], 'a column is not the centre, so it pushes no entry and runs no centre guard (H1)')
  eq(placedResults().whereOf(maximisedOrColumn('s2')), 's2', 'and the placement is registered where it actually went')
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
  next = second
  m.openResult(dest(B), launch())
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
