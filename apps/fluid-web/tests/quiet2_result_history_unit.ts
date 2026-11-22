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
import { mountResults, placedResults, resetPlacedResults, type MountedResults, type ResultPage } from '../src/quiet2/results/mount'
import { beginOpening, clearLaunches, holdLaunch, latestOpening, launchOf, type LaunchContext, type LaunchPlace } from '../src/quiet2/results/launch'
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
  seen: { putBack: string[]; said: string[]; revealed: string[] }
  asked: () => number
  answer: (how: 'go' | 'stay') => void
  waiting: () => boolean
  tape: ReturnType<typeof browser>
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
  const seen = { putBack: [] as string[], said: [] as string[], revealed: [] as string[] }
  let conversation = HERE.conversation!
  let pending: { go: () => void; stay?: () => void } | null = null
  let asked = 0

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
    brainKey: () => BRAIN,
    origin: () => 'https://fixture.invalid',
    conversation: () => conversation,
    centreAt: () => centreAt.current,
    /* the hand-off's own tracker member */
    enterCentre: handoff.member('enterCentre', { centreAt }) as (to: CentreAt) => void,
    columns: () => [],
    freeColumn: () => null,
    choose: () => {},
    invoker: () => null,
    hasControl: () => false,
    focus: () => {},
    centreGo: (at) => wired.centreGo!(at),
    centreReplace: (at) => wired.centreReplace!(at),
    backTo: (place, then, stay) => wired.backTo!(place, then, stay),
    pickConversation: (k, then, stay) => { guarded(() => { conversation = k; then?.() }, 'centre', stay); return true },
    openPost: (_c, _p, done) => done('completed'),
    record: (_e, go) => go(),
    goToPost: () => {},
    reveal: (post) => { seen.revealed.push(post) },
    heldItem: (ref, about) => heldItem(ref, about),
    artifactNow: stillHeld,
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
