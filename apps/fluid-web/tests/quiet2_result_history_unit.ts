/* THE HOST'S OWN HISTORY, COMPOSED -- the three findings of re-review
 * adm-d84456fd4c3c that were about ORDER AND WIRING rather than about a
 * decision (B4.2, B4.3, B4.4).
 *
 * WHY THIS FILE EXISTS. The mount checks beside it supply a synthetic
 * `centreGo`/`centreReplace`/`backTo`, which cannot disagree with the page.
 * The REAL hook can, and did:
 *
 *   B4.2  the hand-off documented `if (R.applyCentre(to)) return` as the FIRST
 *         line of the centre's apply callback, so the page's own
 *         `centreAt.current = to` never ran for a result entry. The tracker
 *         stayed on the Place underneath, every maximised result looked
 *         frame-only to its own close, and the history return it owed could
 *         not be made.
 *   B4.3  `backTo` went straight to `centre.backTo`, and `centreHistory` marks
 *         the pop it makes as ALREADY ASKED. So closing a maximised result
 *         walked the history, restored the Place and gave up the viewer and its
 *         launch with the reader never asked -- and no question left at which
 *         Stay could keep them.
 *   B4.4  resuming a saved result went through the ordinary open, which PUSHED
 *         a second entry in front of the one being resumed. Back came straight
 *         back to the new one and resolved the saved result afresh: a new
 *         opening and a new viewer every time, with no way out.
 *
 * WHAT IS REAL HERE: `usePlaces`, `useCentreHistory` (its trail, its `plan`,
 * its pop handling and its asking), `mount.ts`, the viewer store, the launch
 * registry, the opener -- AND THE HAND-OFF'S OWN WRAPPERS, taken out of
 * `results/HOST-INTEGRATION.md` and executed (`quiet2_result_history_unit.mjs`
 * does the extracting). What is synthetic: the browser's `history` and
 * `popstate`, React's two hooks, and the page's setters. There is no DOM, no
 * browser and no server, and none is claimed: real Back and Forward in a real
 * browser remain unchecked and are recorded as such. */
import assert from 'node:assert/strict'
import { centreGeneration, mountResults, placedResults, resetPlacedResults, type MountedResults, type ResultPage } from '../src/quiet2/results/mount'
import {
  beginOpening, clearLaunches, holdLaunch, latestOpening, launchOf,
  type BrainKey, type Focusable, type FocusChoice, type LaunchContext, type LaunchPlace,
} from '../src/quiet2/results/launch'
import { destinationOfRef, type ResolvedRef, type ResultDestination } from '../src/quiet2/results/targets'
import type { FreshArtifact } from '../src/quiet2/results/refRead'
import { usePlaces } from '../src/quiet2/places'
import type { CentreAt } from '../src/quiet2/address'
import { heldItem } from '../src/quiet2/brain/logic'
import { closeViewer, maximised, viewerOf } from '../src/quiet2/viewer/viewers'

let checks = 0
const eq = (a: unknown, b: unknown, what: string) => { assert.deepEqual(a, b, what); checks++ }
const ok = (a: unknown, what: string) => { assert.ok(a, what); checks++ }
const no = (a: unknown, what: string) => { assert.ok(!a, what); checks++ }

/* -- what the runner beside this file supplies ------------------------------ */

interface Handoff {
  /** the initializer of `const <name> = …` in HOST-INTEGRATION.md, evaluated */
  declaration: (name: string, deps: Record<string, unknown>) => unknown
  /** one member of its `resultPage`, evaluated */
  member: (name: string, deps: Record<string, unknown>) => unknown
  text: (name: string) => string
}
const handoff = (globalThis as unknown as { handoff: Handoff }).handoff
const pendingEffects = (globalThis as unknown as { pendingEffects: (() => void)[] }).pendingEffects

/* -- the browser's own history, synthetically ------------------------------- */

interface Held { q2c?: unknown; q2i?: number }

function browser() {
  const states: (Held | undefined)[] = [undefined]
  const listeners = new Map<string, (e: { state: unknown }) => void>()
  let index = 0
  let left = false
  const history = {
    get state() { return states[index] ?? null },
    replaceState: (s: Held) => { states[index] = s },
    pushState: (s: Held) => { states.splice(index + 1); states.push(s); index += 1 },
    /** a step out of this page's own entries LEAVES THE PAGE, as it really would */
    go: (n: number) => {
      const next = index + n
      if (next < 0 || next >= states.length) { left = true; return }
      index = next
      queueMicrotask(() => listeners.get('popstate')?.({ state: states[index] ?? null }))
    },
  }
  const win = {
    addEventListener: (k: string, f: (e: { state: unknown }) => void) => { listeners.set(k, f) },
    removeEventListener: (k: string) => { listeners.delete(k) },
    setTimeout: () => 0,
  }
  const g = globalThis as unknown as { history: unknown; window: unknown }
  g.history = history
  g.window = win
  return { entries: () => states.length, index: () => index, at: () => states[index] ?? null, left: () => left }
}

/* -- the fixture's own small facts ------------------------------------------ */

const BRAIN = 'fixture-corpus@instance-1'
const A = 'adm-111111111111'
const HERE: LaunchPlace = { conversation: 'ent-origin', centre: null }
const SAVED: LaunchPlace = { conversation: 'ent-origin', centre: null }
const HELD = { state: 'held', name: 'review.txt', size: 20, claimed_media_type: 'text/plain' }
const fileRef = (over: Partial<ResolvedRef> = {}): ResolvedRef => ({
  id: A, type: 'file', state: 'ok', available: true, opens: 'file', file: { ...HELD }, ...over,
})
const dest = (): ResultDestination => destinationOfRef(fileRef())
const stillHeld = async (ref: string): Promise<FreshArtifact> => ({ how: 'held', file: { ...HELD, ref } })
const launch = (place: LaunchPlace = HERE): LaunchContext => holdLaunch({
  opening: beginOpening(), brainKey: BRAIN, place, thread: null,
  reading: { scroll: 417, offset: 12 }, reply: 'ent-reply12345', draft: 'conversation:ent-origin',
  focus: { control: 'needs-ref:' + A, fallback: { kind: 'conversation' } }, decision: null,
})
const settle = () => new Promise<void>((done) => { setImmediate(done) })

interface Fixture {
  R: MountedResults
  centre: ReturnType<typeof usePlaces>
  page: ResultPage
  centreAt: { current: CentreAt }
  seen: { putBack: string[]; said: string[]; revealed: string[]; focused: { choice: FocusChoice; invoker: Focusable | null }[] }
  asked: () => number
  answer: (how: 'go' | 'stay') => void
  waiting: () => boolean
  tape: ReturnType<typeof browser>
  /** the fresh read this page uses, swappable WITHOUT remounting: the mount
   *  reads `page.artifactNow` once, and a resume in flight belongs to the
   *  render that began it */
  reads: (r: (ref: string) => Promise<FreshArtifact>) => void
  /** the Brain this page says it is bound to now (B4.4-R1's third binding) */
  rebind: (key: BrainKey | null) => void
  /** what `document.activeElement` was as the press left it */
  invoker: (el: Focusable | null) => void
}

/** A READ HELD OPEN, answered by hand: the whole of B4.4-R1 is what happens
 *  BETWEEN a resume's read being asked for and its answering. */
function held() {
  let give: ((f: FreshArtifact) => void) | null = null
  return {
    read: (ref: string) => new Promise<FreshArtifact>((r) => { give = (f) => r(f.how === 'held' ? { how: 'held', file: { ...HELD, ref } } : f) }),
    asked: () => !!give,
    answer: (f: FreshArtifact = { how: 'held', file: { ...HELD, ref: A } }) => { const g = give!; give = null; g(f) },
  }
}

/** THE PAGE, WIRED AS THE HAND-OFF SAYS -- its centre members, its apply
 *  callback and its guard are that file's own text, evaluated. */
function fixture(opts: { unfinished?: boolean; destinationOfTarget?: ResultPage['destinationOfTarget'] } = {}): Fixture {
  for (const row of placedResults().all()) closeViewer(row.viewer)
  const max = maximised()
  if (max) closeViewer(max.id)
  clearLaunches()
  resetPlacedResults()
  pendingEffects.length = 0
  const tape = browser()

  const centreAt: { current: CentreAt } = { current: null }
  const seen = {
    putBack: [] as string[], said: [] as string[], revealed: [] as string[],
    focused: [] as { choice: FocusChoice; invoker: Focusable | null }[],
  }
  let conversation = HERE.conversation!
  let pending: { go: () => void; stay?: () => void } | null = null
  let asked = 0
  let reader: (ref: string) => Promise<FreshArtifact> = stillHeld
  let bound: BrainKey | null = BRAIN
  let invoker: Focusable | null = null

  /* the page's own guard, exactly as the hand-off patches it (B3) */
  const guarded = handoff.declaration('guarded', {
    leaving: () => ({ ask: opts.unfinished ? { title: 'Leave it unfinished?' } : null, note: null }),
    unfinished: () => null,
    setLeave: (q: { go: () => void; stay?: () => void }) => { asked += 1; pending = q },
    setNotice: (w: string) => { seen.said.push(w) },
    CENTRE: 'centre',
  }) as (go: () => void, place?: unknown, stay?: () => void) => void

  const wired: { centreGo?: (at: CentreAt) => void; centreReplace?: (at: CentreAt) => void; backTo?: ResultPage['backTo'] } = {}
  const page: ResultPage = {
    brainKey: () => bound,
    origin: () => 'https://fixture.invalid',
    conversation: () => conversation,
    centreAt: () => centreAt.current,
    /* the hand-off's own tracker member */
    enterCentre: handoff.member('enterCentre', { centreAt }) as (to: CentreAt) => void,
    columns: () => [],
    freeColumn: () => null,
    choose: () => {},
    invoker: () => invoker,
    hasControl: () => false,
    focus: (choice, from) => { seen.focused.push({ choice, invoker: from }) },
    centreGo: (at) => wired.centreGo!(at),
    centreReplace: (at) => wired.centreReplace!(at),
    backTo: (place, then, stay) => wired.backTo!(place, then, stay),
    pickConversation: (k, then, stay) => { guarded(() => { conversation = k; then?.() }, 'centre', stay); return true },
    openPost: (_c, _p, done) => done('completed'),
    record: (_e, go) => go(),
    goToPost: () => {},
    reveal: (post) => { seen.revealed.push(post) },
    heldItem: (ref, about) => heldItem(ref, about),
    artifactNow: (ref) => reader(ref),
    destinationOfTarget: opts.destinationOfTarget,
    putBack: (s) => { seen.putBack.push(s.do) },
    say: (w) => { seen.said.push(w) },
  }
  const R = mountResults(page)

  /* the page's own setters, for the arms the apply callback keeps */
  const centre = usePlaces({ c: HERE.conversation, at: null }, {
    apply: handoff.declaration('applyCentre', {
      R,
      brainLeft: { current: null as number | null },
      document: { querySelector: () => null },
      setUnread: () => {},
      keepBrainCard: { current: false },
      setBrainOpen: () => {},
      setSourcesOpen: () => {},
      setSourcesWanted: () => {},
      sourcesRead: { reload: () => {} },
      spaceRef: { current: { apply: () => null } },
      setBrainMain: () => {},
      setSourceMain: () => {},
      setSourceLast: () => {},
    }) as (to: CentreAt, from: CentreAt, how: 'push' | 'pop' | 'replace', asked: boolean) => void,
    show: (k) => { conversation = k },
    /* the BROWSER's own Back and Forward, which this page does not ask about
       here: what B4.3 is about is the page's own control, above */
    ask: () => false,
    address: () => null,
  })
  for (const effect of pendingEffects.splice(0)) effect()

  wired.centreGo = handoff.member('centreGo', { centre }) as (at: CentreAt) => void
  wired.centreReplace = handoff.member('centreReplace', { centre }) as (at: CentreAt) => void
  wired.backTo = handoff.member('backTo', { centre, guarded, CENTRE: 'centre' }) as ResultPage['backTo']

  return {
    R, centre, page, centreAt, seen, tape,
    asked: () => asked,
    waiting: () => !!pending,
    answer: (how) => { const q = pending!; pending = null; if (how === 'go') q.go(); else q.stay?.() },
    reads: (r) => { reader = r },
    rebind: (key) => { bound = key },
    invoker: (el) => { invoker = el },
  }
}

/* ========================================================================== *
 * B4.2 -- the host's own entry tracking survives the result arm
 * ========================================================================== */
{
  const x = fixture()
  const l = launch()
  x.R.openResult(dest(), l)
  await settle()
  const id = maximised()?.id
  ok(id, 'the result is maximised over the centre')
  eq(x.tape.entries(), 2, 'and the real history has one entry for it')
  eq(x.tape.index(), 1, 'which is the entry the browser is on')
  eq((x.tape.at()?.q2c as { at?: CentreAt })?.at?.result?.opening, l.opening, 'the browser’s own state names this opening')
  eq(x.centreAt.current?.result?.opening, l.opening,
    'B4.2: AND SO DOES THE PAGE’S OWN TRACKER -- the result arm’s early return no longer skips it')
  eq(x.page.centreAt()?.result?.opening, l.opening, 'which is what `closeResult` reads to know it owns this entry')
}
{
  /* and an ordinary entry is tracked by the same call, with the page's own
     arms still running for it */
  const x = fixture()
  x.centre.go({ sources: 'all' })
  eq(x.centreAt.current, { sources: 'all' }, 'B4.2: an entry that is not a result is tracked exactly as before')
  eq(x.tape.entries(), 2, 'and is an entry of the browser’s history')
}

/* ========================================================================== *
 * B4.3 -- the maximised close is asked about, and Stay keeps everything
 * ========================================================================== */
{
  const x = fixture({ unfinished: true })
  const l = launch()
  x.R.openResult(dest(), l)
  await settle()
  const id = maximised()!.id
  x.R.closeResult(id)
  await settle()
  eq(x.asked(), 1, 'B4.3: CLOSING A MAXIMISED RESULT ASKS BEFORE IT MOVES THE HISTORY')
  ok(x.waiting(), 'the question is on screen')
  ok(viewerOf(id), 'B4.3: the viewer is still there while it is open')
  ok(launchOf(l.opening), 'and so is its way back')
  eq(x.seen.putBack, [], 'nothing of the old Place has been put back behind the reader')
  eq(x.tape.index(), 1, 'and the browser has not moved')
  x.answer('stay')
  await settle()
  ok(viewerOf(id), 'B4.3: STAY KEEPS THE VIEWER')
  ok(launchOf(l.opening), 'and its launch')
  eq(x.tape.index(), 1, 'B4.3: and the reader is still on their own entry')
  eq(x.centreAt.current?.result?.opening, l.opening, 'with the page still showing it')
  eq(x.seen.putBack, [], 'and nothing restored')
}
{
  /* Go completes it: ONE question, the history actually walked, and the
     viewer given up last */
  const x = fixture({ unfinished: true })
  const l = launch()
  x.R.openResult(dest(), l)
  await settle()
  const id = maximised()!.id
  x.R.closeResult(id)
  x.answer('go')
  await settle()
  eq(x.asked(), 1, 'B4.3: one close asks once -- the history move took the reader to the whole Place')
  eq(x.tape.index(), 0, 'B4.3: and the real history actually stepped back to it')
  eq(x.tape.entries(), 2, 'without adding an entry to come back to')
  no(viewerOf(id), 'the viewer is given up')
  no(launchOf(l.opening), 'with its launch')
  eq(x.seen.putBack, ['reading', 'reply', 'draft'], 'and the rest of the Place is put back after the move')
  eq(x.centreAt.current, null, 'the page is on the Place it returned to')
}

/* ========================================================================== *
 * B4.4 -- resuming a saved result adds no entry, and Back still leaves it
 * ========================================================================== */
{
  const x = fixture({ destinationOfTarget: () => dest() })
  /* a reload: the entry the browser is standing on holds a result whose
     launch did not survive it */
  const stored: CentreAt = { result: { brainKey: BRAIN, opening: 91, target: { kind: 'artifact', ref: A }, place: SAVED } }
  x.centre.replace(stored)
  await settle()
  const shown = maximised()
  ok(shown, 'the saved result is resolved again rather than leaving a blank centre')
  eq(x.tape.entries(), 1, 'B4.4: AND NO SECOND ENTRY IS PUSHED IN FRONT OF THE ONE BEING RESUMED')
  eq(x.tape.index(), 0, 'the browser is still on the entry it landed on')
  const resumed = (x.tape.at()?.q2c as { at?: CentreAt })?.at?.result
  eq(resumed?.target, { kind: 'artifact', ref: A }, 'B4.4: the entry keeps the target it saved')
  eq(resumed?.place, SAVED, 'and the Place it saved')
  eq(resumed?.opening, placedResults().openingOf(shown!.id), 'B4.4: naming the opening that is actually showing it now')
  const openings = latestOpening()
  const viewers = placedResults().all().length
  /* the reader presses Back */
  ;(globalThis as unknown as { history: { go: (n: number) => void } }).history.go(-1)
  await settle()
  ok(x.tape.left(), 'B4.4: BACK LEAVES THE SAVED RESULT, as it would from any page opened on one')
  eq(x.tape.entries(), 1, 'B4.4: it does not land on a second entry of this page’s own making')
  eq(latestOpening(), openings, 'B4.4: and nothing is resolved afresh: no new opening')
  eq(placedResults().all().length, viewers, 'and no second viewer')
}

/* ========================================================================== *
 * B4.4-R1 (re-review adm-efb406a34e7a, BLOCKING) -- A RESUME THAT ANSWERS
 * AFTER THE READER HAS MOVED REPLACES NOTHING.
 *
 * The B4.4 correction stopped the extra push: a resume corrects the entry the
 * browser is standing on. But WHICH entry that is was read again when the
 * resume's own read answered, and by then the reader could have pressed Back.
 * The review's two reproducers are both here, over the real `usePlaces` and a
 * real `popstate`, with the read held open by hand.
 * ========================================================================== */

const press = (n: number) => (globalThis as unknown as { history: { go: (n: number) => void } }).history.go(n)
const SAVED_ENTRY: CentreAt = { result: { brainKey: BRAIN, opening: 91, target: { kind: 'artifact', ref: A }, place: SAVED } }
const placeOfEntry = (x: Fixture): CentreAt => ((x.tape.at()?.q2c as { at?: CentreAt } | undefined)?.at ?? null)

{
  /* REPRODUCTION 1: landing on a saved result, Back, then the read answers */
  const x = fixture({ destinationOfTarget: () => dest() })
  const read = held()
  x.reads(read.read)
  x.centre.go(SAVED_ENTRY)
  await settle()
  ok(read.asked(), 'the saved result’s own fresh read has been asked for')
  no(maximised(), 'and nothing is drawn while it is in flight')
  eq(x.tape.index(), 1, 'the browser is on the saved entry')
  const moved = centreGeneration()
  /* the reader presses Back, off the entry being resolved */
  press(-1)
  await settle()
  eq(x.tape.index(), 0, 'Back has reached the Place underneath')
  eq(x.centreAt.current, null, 'and the page is on it')
  ok(centreGeneration() > moved, 'B4.4-R1: which is one centre generation on')
  /* and NOW the read answers, successfully */
  read.answer()
  await settle()
  no(maximised(), 'B4.4-R1: NO VIEWER IS OPENED over the Place Back reached')
  eq(placedResults().all().length, 0, 'and no result is registered for it')
  eq(placeOfEntry(x), null, 'B4.4-R1: THE ENTRY BACK REACHED STILL HOLDS ITS OWN PLACE -- it is not replaced by the result')
  eq(x.centreAt.current, null, 'the page’s own tracker is left on it too')
  eq(x.tape.entries(), 2, 'with no entry added, removed or rewritten')
}
{
  /* REPRODUCTION 2: an ACTUAL saved Forward, then Back, then the read --
     `actual-Forward-late` in the review's own log */
  const x = fixture({ destinationOfTarget: () => dest() })
  x.centre.go(SAVED_ENTRY)
  await settle()
  ok(maximised(), 'the saved result is resolved the first time')
  press(-1)
  await settle()
  no(maximised(), 'Back takes it off the centre (F16)')
  /* from here the read is held open, and the reader uses their own Forward */
  const read = held()
  x.reads(read.read)
  press(1)
  await settle()
  eq(x.tape.index(), 1, 'Forward has landed on the saved result again')
  ok(read.asked(), 'which is being resolved again, its viewer having gone')
  no(maximised(), 'nothing is drawn yet')
  press(-1)
  await settle()
  eq(x.tape.index(), 0, 'and the reader presses Back again before it answers')
  read.answer()
  await settle()
  no(maximised(), 'B4.4-R1: the late answer to the Forward opens no viewer')
  eq(placeOfEntry(x), null, 'B4.4-R1: AND THE PLACE BACK REACHED IS STILL THERE')
  eq(x.centreAt.current, null, 'unchanged on the page as well')
  eq(x.tape.entries(), 2, 'and the history is the two entries it was')
}
{
  /* A DELAYED REFUSAL IS DROPPED THE SAME WAY, and says nothing: the reader
     pressed Back, and did not ask about a result they left */
  const x = fixture({ destinationOfTarget: () => dest() })
  const read = held()
  x.reads(read.read)
  x.centre.go(SAVED_ENTRY)
  await settle()
  press(-1)
  await settle()
  const said = x.seen.said.length
  read.answer({ how: 'gone', availability: 'purged', why: 'That result is no longer held.' })
  await settle()
  eq(x.seen.said.length, said, 'B4.4-R1: a refusal for an entry the reader has left is not said to them')
  no(maximised(), 'and nothing is opened by it')
  eq(placeOfEntry(x), null, 'the Place they are on is untouched')
}
{
  /* THE BRAIN IDENTITY ARM ON ITS OWN: the centre has not moved at all, and
     the page is on the very entry -- but the server now serves another
     INSTANCE of the same corpus, so the resume is still dropped */
  const x = fixture({ destinationOfTarget: () => dest() })
  const read = held()
  x.reads(read.read)
  x.centre.go(SAVED_ENTRY)
  await settle()
  const generation = centreGeneration()
  x.rebind('fixture-corpus@instance-2')
  read.answer()
  await settle()
  eq(centreGeneration(), generation, 'the centre has NOT moved: this is the Brain binding alone')
  eq(x.tape.index(), 1, 'and the browser is still on the saved entry')
  no(maximised(), 'B4.4-R1: a pending resume is bound to the Brain identity it landed with')
  eq(placeOfEntry(x)?.result?.target, { kind: 'artifact', ref: A }, 'the saved entry is left exactly as it was')
  eq(placeOfEntry(x)?.result?.opening, 91, 'its saved opening included')
}
{
  /* AND THE SUCCESSFUL RESUME IS PRESERVED (B4.4): still current when its
     read answers, it opens -- and Back and Forward repeat without entries
     being added, which is what B4.4 was about */
  const x = fixture({ destinationOfTarget: () => dest() })
  x.centre.go(SAVED_ENTRY)
  await settle()
  ok(maximised(), 'B4.4 preserved: a resume that is still current DOES open')
  eq(x.tape.entries(), 2, 'in place, pushing no second entry')
  for (const round of [1, 2]) {
    press(-1)
    await settle()
    eq(x.tape.index(), 0, `round ${round}: Back leaves the result`)
    no(maximised(), 'and takes it off the centre')
    press(1)
    await settle()
    eq(x.tape.index(), 1, `round ${round}: Forward returns to it`)
    eq(x.tape.entries(), 2, 'B4.4 preserved: with no entry added by the resume')
    const shown = maximised()
    ok(shown, 'and it is shown again')
    eq(shown?.content.kind === 'file' && shown.content.item.ref, A, 'at the exact reference the entry saved')
  }
}

/* ========================================================================== *
 * N2 (re-review adm-efb406a34e7a, nonblocking, CONFIRMED) -- the closing
 * viewer's own invoker actually reaches the page, over the real history move.
 *
 * `closeResult`'s guarded `backTo` runs FIRST, its pop lands on an ordinary
 * entry, and the leave arm (F16) forgets the registry row -- so reading
 * `results.invokerOf(viewer)` at the focus step read null, and the element the
 * plan had chosen was never focused.
 * ========================================================================== */
{
  const x = fixture({ unfinished: false })
  const el: Focusable = { isConnected: true }
  x.invoker(el)
  const l = launch()
  x.R.openResult(dest(), l)
  await settle()
  const id = maximised()!.id
  ok(placedResults().invokerOf(id) === el, 'the registry holds the control the press came from')
  x.R.closeResult(id)
  await settle()
  eq(x.tape.index(), 0, 'the close walked the real history back to the Place')
  no(placedResults().invokerOf(id), 'and the registry row is gone by the time focus is put')
  eq(x.seen.focused.length, 1, 'focus is put once')
  eq(x.seen.focused[0].choice, { how: 'invoker' }, 'N2: at the control that was pressed (H6)')
  ok(x.seen.focused[0].invoker === el, 'N2: AND THE ELEMENT ITSELF REACHES THE PAGE, held from the plan')
}
{
  /* and where the restore has taken that control off the page, the choice
     falls through rather than focusing nothing */
  const x = fixture({ unfinished: false })
  const el: Focusable = { isConnected: true }
  x.invoker(el)
  x.R.openResult(dest(), launch())
  await settle()
  const id = maximised()!.id
  el.isConnected = false
  x.R.closeResult(id)
  await settle()
  eq(x.seen.focused[0].choice, { how: 'fallback', fallback: { kind: 'conversation' } },
    'N2: a control that is no longer connected falls through to the launch’s own fallback (H6)')
}

/* ========================================================================== *
 * the wrappers themselves are the hand-off's, not this file's
 * ========================================================================== */
{
  ok(/centreAt\.current = to/.test(handoff.text('applyCentre') + handoff.text('resultPage')),
    'B4.2: the hand-off records the entry through `enterCentre`')
  ok(/guarded\(/.test(handoff.text('resultPage')), 'B4.3: and asks before the history move it documents')
  const apply = handoff.text('applyCentre')
  ok(apply.indexOf('R.applyCentre') > 0, 'the apply callback the checks above ran is the one it documents')
}

for (const row of placedResults().all()) closeViewer(row.viewer)
clearLaunches()
resetPlacedResults()
console.log(`quiet2 result history: ${checks} checks ok`)
