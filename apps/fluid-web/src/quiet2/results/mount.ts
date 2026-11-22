/* THE HOST ADAPTERS THEMSELVES, COMPILED -- not described (re-review
 * adm-263df1ccb512, B4).
 *
 * WHY THIS FILE EXISTS. The hand-off's second version moved the host's
 * DECISIONS into `hostOpen.ts`, where they could be checked, and left the
 * ADAPTERS -- the code that calls those decisions against the page's own viewer
 * store, history hook and readers -- as TSX snippets in a Markdown file. The
 * re-review executed those exact declarations and seven of them did not
 * compose: the record adapter reported an arrival while its guard was still
 * open; the history entry was built from the source post rather than the
 * result; a reload's stored Place was thrown away for the current one; a
 * frame-only close navigated as well as closing; a side close gave up the
 * viewer while the return guard was still asking; leaving a result entry left
 * the old file maximised over the new Place; and the fresh read named a reader
 * that does not exist. Prose cannot fail a test, which is why it failed a
 * review instead.
 *
 * SO THE ADAPTERS ARE HERE, in this part's own files, against the REAL
 * `viewer/viewers.ts`, the real `results/*` decisions and the real bound read
 * (`refRead.ts`). What is left for the shared hosts is the one thing they
 * alone have: their React state. They hand it over as `ResultPage` -- each
 * member a function the baseline already has, with the guard's three ends made
 * explicit -- and call the operations here. `HOST-INTEGRATION.md` is now that
 * wiring, and `tests/quiet2_result_mount_unit.ts` runs every one of the
 * re-review's falsifiers against THIS composition.
 *
 * WHAT IS STILL NOT CLAIMED. Nothing here is mounted, so nothing here is
 * rendered: these are the real calls against the real stores, checked without
 * a browser. A combined, mounted candidate still owes its own review. */
import type { CentreAt } from '../address'
import type { Viewable, ViewerSource, ViewImage } from '../viewer/types'
import {
  closeViewer, maximised, moveViewer, openViewer, parkViewer, parkedPlaceOf, returnViewer, viewerOf,
} from '../viewer/viewers'
import type { HeldBytes, ViewerItem } from '../../quiet/media/view'
import {
  BRAIN_MOVED, beginOpening, holdLaunch, launchOf,
  type BrainKey, type DecisionLaunch, type Focusable, type FocusChoice, type LaunchContext,
  type LaunchFocus, type LaunchPlace,
} from './launch'
import { resultIntent, resumeResult, type Shown } from './history'
import {
  closeSteps, dockStep, fileContent, leaveSteps, pressed, restoreSteps, resultViewers, resumeSteps, sourceSteps,
  type CloseStep, type Column, type PlaceStep, type ResultViewers,
} from './hostOpen'
import {
  openResultTarget, type Navigation, type Opened, type OpenerHost, type Placed, type Read,
} from './opener'
import { COULD_NOT_CHECK, artifactNow, type FreshArtifact } from './refRead'
import { actionOf, type ResultDestination, type ResultTarget } from './targets'

/* -- what the page alone has ------------------------------------------------ */

/** THE READER PICKING A COLUMN, as the page's own chooser puts it. `decide` is
 *  this module's: the placement, its registration and its history entry are
 *  made here however the reader answers, so the three chooser buttons say only
 *  which column -- or that the reader cancelled. */
export interface ColumnChoice {
  content: Viewable
  source: ViewerSource
  launch: LaunchContext
  /** `'max'`, a column, or `'cancelled'`: told once */
  decide: (where: Shown | 'cancelled') => void
}

/** EVERYTHING THE SHARED HOSTS SUPPLY, and nothing else. Each member is a
 *  function `Quiet2.tsx` already has; where a baseline function hides the
 *  guard's answer behind a `void` or a `boolean`, the three ends are explicit,
 *  because reporting a pending guard as an arrival is what B3 was. */
export interface ResultPage {
  /** `brain.key` (`brainBinding.ts`), as this render has it */
  brainKey: () => BrainKey | null
  /** `location.origin`, for the external-URL policy */
  origin: () => string | null
  /** the conversation shown (`realId`) */
  conversation: () => string | null
  /** the entry the centre is on (`centreAt.current`) */
  centreAt: () => CentreAt | null
  /** THE ENTRY THE CENTRE HAS JUST MOVED TO, recorded by the page
   *  (`centreAt.current = to`). `applyCentre` calls this FIRST, before it
   *  decides anything and before any early return, because the host's own
   *  tracker is what `closeResult` reads to know whether this result owns the
   *  entry it is on. The hand-off used to document `if (R.applyCentre(to))
   *  return` as the apply callback's first line, which left that assignment
   *  unreached for every result entry: the tracker stayed on the Place
   *  underneath, a maximised result looked frame-only, and its close could not
   *  make the history return it owed (re-review adm-d84456fd4c3c, B4.2). The
   *  host cannot skip it now, because it is not the host that calls it. */
  enterCentre: (to: CentreAt) => void
  /** the working columns the page is showing now (`surfacePanes`) */
  columns: () => readonly Column[]
  /** a column with nothing in it (`!surfaces[s] && !inColumn(s) && !dockPanels[s]`) */
  freeColumn: () => Column | null
  /** no free column: the page asks the reader, and answers through `decide` */
  choose: (ask: ColumnChoice) => void
  /** `document.activeElement` as the press leaves it (`openedBy`) */
  invoker: () => Focusable | null
  /** a control with this stable identity is drawn now (`[data-control]`) */
  hasControl: (control: string) => boolean
  /** PUT FOCUS WHERE `focusChoice` SAYS, and -- for `{how:'invoker'}` -- on
   *  the element THIS viewer was opened from, which is handed over rather
   *  than read from a module-global. The hand-off's own `applyFocus` called
   *  `openedBy?.focus()`, which the most recent open overwrites, so closing
   *  the first of two viewers focused the second one's row (re-review
   *  adm-263df1ccb512, N2; this adapter is replaced for F14/F15 anyway, so
   *  the choice is not left reachable through it). */
  focus: (choice: FocusChoice, invoker: Focusable | null) => void

  /* the centre's own history (`places.ts`) */
  /** `centre.go(at)` */
  centreGo: (at: CentreAt) => void
  /** `centre.replace(at)` */
  centreReplace: (at: CentreAt | null) => void
  /** `centre.backTo(place, then)` BEHIND THE UNSAVED-WORK GUARD, with the
   *  guard's three ends made explicit, like every other page move here:
   *  `then` runs only once the move has actually been applied, and `stay`
   *  where the reader kept what they had.
   *
   *  THE GUARD BELONGS TO THE CONTROL THAT MOVES (re-review adm-d84456fd4c3c,
   *  B4.3). `places.ts` `backTo` delegates straight to `centreHistory`'s
   *  `back`, and that helper treats the pop it makes as ALREADY ASKED
   *  (`askFirst(asked, …)` is false for a move the page asked for) -- which is
   *  right, and means the asking has to happen here. The hand-off called
   *  `centre.backTo` directly, so closing a maximised result walked the
   *  history, restored the old Place and gave up the viewer and its launch
   *  without the reader being asked at all, and there was no question left at
   *  which Stay could keep them. */
  backTo: (place: LaunchPlace, then: () => void, stay: () => void) => void

  /* the page's navigation, each with the unsaved-work guard's three ends */
  /** `pickConversation(k, then, stay)`: false where there is no such route */
  pickConversation: (k: string, then?: () => void, stay?: () => void) => boolean
  /** `openFromDock(c, p, done)`: the thread read and its guard, reported */
  openPost: (conversation: string, post: string, done: (n: Navigation) => void) => void
  /** `enterBrain({page:'record',entry}, {from:'link'})` WITH ITS GUARD'S ENDS:
   *  `go` once the record page is actually shown, `stay` where the reader kept
   *  what they had. The baseline's own `guarded` already takes both. */
  record: (entry: string, go: () => void, stay: () => void) => void
  /** `now.current.goToPost(c, p)`: where the bytes came from */
  goToPost: (conversation: string, post: string) => void
  /** `requestAnimationFrame(() => revealPost(post))`: the post this page has
   *  already drawn, brought into view. It is the baseline viewer frame's own
   *  close for an ordinary maximised picture, kept for the viewers this
   *  contract never registered (N3). Left out, such a close simply closes. */
  reveal?: (post: string) => void

  /* the page's readers -- and nothing new */
  /** `heldItem(ref, about)` */
  heldItem: (ref: string, about: HeldBytes | null) => ViewerItem | null
  /** `postOf(post)`: the post this page has drawn, where it has */
  postOf?: (post: string) => unknown
  /** `picturesOf(post)`, asked only for a post there is */
  pictures?: (post: unknown) => readonly ViewImage[]
  /** THE FRESH READ, FOR THE CHECKS ONLY. The read itself is this part's own
   *  module (`refRead.ts` `artifactNow`, over the artifact's `?describe=1`
   *  route) and is NOT a page member any more: it needs nothing the host has,
   *  and making it optional host wiring is what let three launch surfaces open
   *  an unchecked descriptor (re-review adm-d84456fd4c3c, B4.1). A check
   *  supplies its own reader here; the page supplies none and gets the real
   *  one. */
  artifactNow?: (ref: string) => Promise<FreshArtifact>
  /** N-B's adapter from a stored target back to a destination. Left out, an
   *  entry whose viewer has gone shows its Place and says so. */
  destinationOfTarget?: (t: ResultTarget) => ResultDestination | null

  /* the rest of a launch's Place, which only the page can put back */
  /** one restore step the page applies: thread, reading, reply or draft key */
  putBack: (step: PlaceStep) => void
  /** the explicit return bar still owed (`setResultReturn`) */
  offerReturn?: (l: LaunchContext) => void
  /** a result entry of another Brain: the reader is left on its Place */
  leaveOn?: (place: LaunchPlace) => void
  /** `window.open(href, …)` under `EXTERNAL_LINK` */
  external?: (href: string) => boolean
  /** `setNotice(words)` */
  say: (words: string) => void
}

/* -- the page's result viewers, for the page's life -------------------------- */

/* ONE REGISTRY, LIKE THE VIEWER STORE BESIDE IT. `mountResults` is called on
   every render of the host, so the registry cannot be made by it: a new one
   each render would lose every open viewer's way back, which is B2 again by
   another route. A plain module store, as `viewer/viewers.ts` is. */
let store = resultViewers(launchOf)
export const placedResults = (): ResultViewers => store
/** Thrown away between test cases, exactly as `clearLaunches` is. */
export const resetPlacedResults = () => { store = resultViewers(launchOf) }

const NO_DESTINATION = 'That result cannot be opened again here; the way back to where you were is below.'
const COULD_NOT_RETURN = 'That conversation could not be opened, so nothing was closed.'

/** THE DESTINATION WITH WHAT THE FRESH READ ACTUALLY READ, and nothing else
 *  touched (B4.1). The description answers about availability; the record's own
 *  facts -- where the bytes came from, the label, the basis, the Work -- are
 *  the destination's and are carried through unchanged, because the artifact
 *  route deliberately strips `source` and knows nothing of the rest. The
 *  caller's own `item` is dropped: it was built from the descriptor the row was
 *  drawn with, and the point of this read is that the fresh one stands. */
const freshly = (d: ResultDestination, fresh: Extract<FreshArtifact, { how: 'held' }>): ResultDestination =>
  ({ ...d, availability: 'ok', available: true, opens: 'file', reason: null, file: fresh.file, item: null })

/** WHAT THE HOST CALLS. Every one of these is an operation the integrator
 *  invokes; none of them is a decision the integrator has to make. */
export interface MountedResults {
  /** the one host operation (`openResultTarget`) with this page's adapters */
  openResult: (d: ResultDestination, launch: LaunchContext, settled?: (o: Opened) => void) => Opened
  /** whether this page has a route for it at all (the dock's `has`) */
  has: (d: ResultDestination) => boolean
  /** a launch for where the reader is now */
  launchNow: (place: LaunchPlace, focus: LaunchFocus, decision?: DecisionLaunch | null, reading?: LaunchContext['reading'], thread?: LaunchContext['thread'], reply?: string | null, draft?: string | null) => LaunchContext
  /** held bytes shown, registered, and given their history entry (`onView`) */
  openView: (content: Viewable, source: ViewerSource, target: ResultTarget | null, launch: LaunchContext, settled?: (p: Placed) => void) => Shown | 'choosing'
  /** the close sequence, abandoned where the reader stays (H7) */
  closeResult: (viewer: string) => void
  /** go to source, which is not close (H3) */
  goToSource: (viewer: string, source: { conversation: string; post: string }) => void
  /** the centre's `apply`, for a result entry AND for leaving one. True where
   *  this handled the entry; false leaves the page's other arms to it. */
  applyCentre: (to: CentreAt) => boolean
  /** what the dock does with an answer, and whether the press did anything */
  dockStep: typeof dockStep
  pressed: typeof pressed
  results: ResultViewers
  /** the host as the opener sees it, for the page's own direct calls */
  host: OpenerHost
}

export function mountResults(page: ResultPage, results: ResultViewers = placedResults()): MountedResults {
  const brainKey = page.brainKey()
  /** the fresh read: this part's own, unless a check injected one */
  const readFresh = page.artifactNow ?? ((ref: string) => artifactNow(ref))

  /* -- where the reader is, as a launch ------------------------------------ */
  const launchNow: MountedResults['launchNow'] = (place, focus, decision = null, reading = null, thread = null, reply = null, draft = null) =>
    holdLaunch({ opening: beginOpening(), brainKey, place, thread, reading, reply, draft, focus, decision })

  /** A LAUNCH FOR A PLACE THE HISTORY SAVED (F13). A reload has taken the live
   *  launch with it; what the entry holds is the Place it was over, and that
   *  Place -- not wherever the reader happens to be now -- is what the
   *  re-resolved result owes them. Nothing else is promised: no draft, no
   *  focus, no reply target (H8). */
  const launchForSaved = (back: LaunchPlace): LaunchContext =>
    holdLaunch({
      opening: beginOpening(), brainKey, place: back, thread: null, reading: null,
      reply: null, draft: null, focus: { control: null, fallback: { kind: 'conversation' } }, decision: null,
    })

  /* -- opening held bytes -------------------------------------------------- */

  /** THE RESULT'S OWN IDENTITY FOR THE HISTORY ENTRY (F12). The target the
   *  press resolved, where there is one; otherwise the Admission actually
   *  being shown -- never the post it came from, which is its SOURCE. */
  const identityOf = (target: ResultTarget | null, content: Viewable): ResultTarget | null => {
    if (target) return target
    if (content.kind === 'file' && content.item.ref) return { kind: 'artifact', ref: content.item.ref }
    return null
  }

  /** WHICH ENTRY A MAXIMISED OPEN OWES (re-review adm-d84456fd4c3c, B4.4).
   *
   *    new      an explicit press: a displacement that was not one before, so
   *             one entry is PUSHED and Back returns to where they pressed it
   *    current  a result entry the browser has already landed on, being
   *             resolved again (a reload, or Back onto a saved result): THE
   *             ENTRY ALREADY EXISTS, and its identity is corrected in place
   *
   *  Pushing on a resume is what defeated Back: landing on the saved entry
   *  made a second entry in front of it, so Back came straight back to the
   *  new one and resolved the saved result afresh -- a new opening and a new
   *  viewer every time, with no way out of it. */
  type Entry = 'new' | 'current'

  /** a maximised result's one history entry, where it has an identity */
  const entered = (target: ResultTarget | null, launch: LaunchContext, entry: Entry) => {
    if (!target) return
    const intent = resultIntent(brainKey, launch.opening, target, launch.place)
    /* THE SAVED TARGET AND THE SAVED PLACE ARE KEPT (F13): what the resumed
       entry gains is only the opening that is now showing it, so the close
       plan, the leave arm and `resumeSteps` all find the live viewer. */
    if (entry === 'current') page.centreReplace(intent)
    else page.centreGo(intent)
  }

  const put = (content: Viewable, source: ViewerSource, target: ResultTarget | null, launch: LaunchContext, where: 'max' | Column, entry: Entry): Shown => {
    const id = openViewer(content, source, where)
    const identity = identityOf(target, content)
    results.place(id, launch, identity, where, page.invoker())
    if (where === 'max') entered(identity, launch, entry)
    return where
  }

  const place = (content: Viewable, source: ViewerSource, target: ResultTarget | null, launch: LaunchContext, settled: ((p: Placed) => void) | undefined, entry: Entry): Shown | 'choosing' => {
    const columns = page.columns()
    if (!columns.length) return put(content, source, target, launch, 'max', entry)
    const free = page.freeColumn()
    /* a column is `historyStep(…) === 'none'`: no entry, and no centre guard */
    if (free) return put(content, source, target, launch, free, entry)
    page.choose({
      content, source, launch,
      decide: (chosen) => {
        if (chosen === 'cancelled' || chosen === 'none') { settled?.({ how: 'cancelled' }); return }
        settled?.({ how: 'completed', where: put(content, source, target, launch, chosen, entry) })
      },
    })
    return 'choosing'
  }

  const openView: MountedResults['openView'] = (content, source, target, launch, settled) =>
    place(content, source, target, launch, settled, 'new')

  /* -- a guarded move's ACTUAL outcome (F09) ------------------------------- */

  /** WHAT A GUARDED PAGE MOVE REALLY ANSWERS (B3, F09).
   *
   *  `enterBrain`, `pickConversation` and `openFromDock` are all `guarded`:
   *  asking is not arriving, and the reader can answer Stay. So the move is
   *  made with both ends, and what the adapter returns is what has actually
   *  happened by the time it returns -- `completed` only where the page moved
   *  on the press itself, `requested` where the question is still open, and
   *  `failed` where there was no route. The answer that comes later reaches
   *  `settled`, once. */
  const guardedMove = (settled: (n: Navigation) => void, ask: (say: (n: Navigation) => void) => boolean | void): Navigation => {
    let onPress: Navigation | null = null
    let returned = false
    let said = false
    const say = (n: Navigation) => {
      if (said) return
      said = true
      if (returned) settled(n)
      else onPress = n
    }
    const could = ask(say)
    returned = true
    if (could === false) return 'failed'
    return onPress ?? 'requested'
  }

  /* -- the host --------------------------------------------------------------
     Each adapter is the page's existing reader or route, and says honestly
     what became of it. `entry` is the one thing that differs between an
     explicit press and a resume, and it travels WITH THE HOST so that it is
     still right when the fresh read answers a moment later: the opener's own
     recursion after a read carries the host it was given, and nothing else
     here has to remember which press this was (B4.4). */
  const hostFor = (entry: Entry): OpenerHost => ({
    brainKey,
    origin: page.origin(),
    file: (o) => {
      const read = fileContent(o, { item: page.heldItem, post: page.postOf, pictures: page.pictures })
      if ('why' in read) { page.say(read.why); return null }
      const source: ViewerSource = read.source ?? { kind: 'brain', brainKey: brainKey ?? '' }
      return place(read.content, source, o.target, o.launch, o.settled, entry)
    },
    post: (conversation, post, settled) =>
      guardedMove(settled, (say) => { page.openPost(conversation, post, say) }),
    /* THE RECORD PAGE IS GUARDED LIKE EVERY OTHER CENTRE MOVE (F09). The
       baseline's `enterBrain` is `guarded(() => centre.go(…))`: a pending
       unsaved-work question is not an arrival, and Stay prevents the move
       altogether. Reporting `'completed'` on the press was the original
       false departure, on the one route that still had it. */
    record: (entry, settled) => guardedMove(settled, (say) => { page.record(entry, () => say('completed'), () => say({ how: 'cancelled' })) }),
    conversation: (ref, settled) => guardedMove(settled, (say) => page.pickConversation(ref, () => say('completed'), () => say({ how: 'cancelled' }))),
    external: page.external,
    /* A4/P4: THE ARTIFACT'S OWN DESCRIPTION, ON EVERY EXPLICIT ARTIFACT OPEN,
       AND FAIL-CLOSED (re-review adm-d84456fd4c3c, B4.1).

       The read is `refRead.ts`'s, not the host's: it needs nothing a page has,
       so there is no wiring to leave out and no surface that opens unchecked.
       Whatever the press came from -- Needs you, the result chooser, a Brain
       record, the Latest list -- the exact reference is described again before
       anything is placed, and only "this reference is held here now" lets the
       open through. A refusal, a state that is not `held`, a description of
       something else and a network failure are all `gone`: the reader is told,
       and the descriptor in hand is never placed as though it had been
       checked. */
    read: (d, settled): Read => {
      const t = d.target
      /* only artifacts reach here (`actionOf` 'file'); other routes keep their
         own guarded readers and are not described */
      if (t.kind !== 'artifact') return { how: 'unchecked' }
      void readFresh(t.ref)
        .then((f) => settled(f.how === 'held'
          ? { how: 'fresh', destination: freshly(d, f) }
          : { how: 'gone', why: f.why }))
        .catch(() => settled({ how: 'gone', why: COULD_NOT_CHECK }))
      return { how: 'reading' }
    },
    say: page.say,
  })

  const host = hostFor('new')
  /** the same host, for an entry the browser is already standing on */
  const resuming = hostFor('current')

  const openResult: MountedResults['openResult'] = (d, launch, settled) =>
    openResultTarget(d, launch, host, { settled })

  const has: MountedResults['has'] = (d) => {
    switch (actionOf(d)) {
      case 'file': return !!host.file
      case 'post': return !!host.post
      case 'record': return !!host.record
      case 'conversation': return !!host.conversation
      case 'external': return !!host.external
      case 'commit': return true
      case 'unavailable': return false
    }
  }

  /* -- where a viewer is, as the real store has it ------------------------- */

  const whereOf = (viewer: string): Shown => {
    const v = viewerOf(viewer)
    if (!v) return 'none'
    return v.place === 'parked' ? 'none' : v.place
  }

  /* -- closing, awaiting the guard (F14, F15) ------------------------------ */

  /** The page's own part of a restore. `centre` is the history's and is left
   *  to it; the conversation is handled by the caller, because it is guarded. */
  const applyPlace = (steps: readonly PlaceStep[]) => {
    for (const p of steps) {
      if (p.do === 'conversation') continue
      if (p.do === 'centre') { page.centreReplace(p.at); continue }
      page.putBack(p)
    }
  }

  /** RUNS A RESTORE, AND SAYS WHETHER IT HAS FINISHED (F15).
   *
   *  A launch made in another conversation needs that conversation opened, and
   *  THAT PRESS IS GUARDED: the reader can be asked about unsaved work and can
   *  answer Stay. The old sequence called `pickConversation` and carried on
   *  regardless, so the viewer was closed and its launch released while the
   *  question was still on screen -- and Stay then kept neither. Everything
   *  after the move runs inside the move's own success. */
  const runRestore = (steps: readonly PlaceStep[], then: () => void): 'waiting' | 'done' => {
    const first = steps[0]
    if (first?.do !== 'conversation') { applyPlace(steps); return 'done' }
    const rest = steps.slice(1)
    const could = page.pickConversation(first.conversation, () => { applyPlace(rest); then() }, () => {})
    /* no route to it: nothing is restored and nothing is given up either */
    if (could === false) { page.say(COULD_NOT_RETURN); return 'waiting' }
    return 'waiting'
  }

  const runClose = (steps: readonly CloseStep[], from: number, closing: string) => {
    for (let i = from; i < steps.length; i++) {
      const step = steps[i]
      if (step.do === 'forget') { closeViewer(step.viewer); results.forget(step.viewer); continue }
      /* THE CLOSING VIEWER'S OWN INVOKER, from the registry (N2) */
      if (step.do === 'focus') { page.focus(step.choice, results.invokerOf(closing)); continue }
      /* AN ORDINARY PICTURE, BACK TO ITS OWN POST (N3): the baseline's own
         close, kept for a viewer this contract never registered. */
      if (step.do === 'reveal') { page.reveal?.(step.post); continue }
      const rest = i + 1
      if (runRestore(step.place, () => runClose(steps, rest, closing)) === 'waiting') return
    }
  }

  const closeResult: MountedResults['closeResult'] = (viewer) => {
    const launch = results.launchOf(viewer)
    const at = page.centreAt()
    const owns = !!at?.result && at.result.opening === results.openingOf(viewer)
    const plan = closeSteps(
      { viewer, where: whereOf(viewer), launch, source: viewerOf(viewer)?.source ?? null },
      { owns, conversation: page.conversation(), invoker: results.invokerOf(viewer), has: page.hasControl },
    )
    const run = () => runClose(plan.then, 0, viewer)
    /* THE HISTORY MOVE FIRST, BEHIND ITS OWN GUARD, and the rest inside its
       `then`: a reader who answers with Stay never reaches the close, and
       keeps the viewer, its launch and their place in the history (H7; B4.3).
       NOTHING IS DONE ON STAY -- not a restore step, not a forget, not the
       return bar -- because nothing has been left. */
    if (plan.history) page.backTo(plan.history.to, run, () => {})
    else run()
    if (plan.bar && launch) page.offerReturn?.(launch)
  }

  /* -- go to source (F10) -------------------------------------------------- */

  const goToSource: MountedResults['goToSource'] = (viewer, source) => {
    const v = viewerOf(viewer)
    for (const step of sourceSteps({ where: whereOf(viewer), from: v?.from ?? null }, source, { columns: page.columns() })) {
      if (step.do === 'to-column') { moveViewer(viewer, step.column); results.moved(viewer, step.column) }
      /* PARKED BECAUSE THE PAGE HAS KEPT A WAY BACK TO IT (F10): the store
         parks anything on that word, so an artifact with no column stops
         sitting over the very post it is sending the reader to. */
      else if (step.do === 'park') { parkViewer(viewer, 'kept'); results.moved(viewer, 'none') }
      else page.goToPost(step.conversation, step.post)
    }
  }

  /* -- landing on an entry, and leaving one (F13, F16) --------------------- */

  const applyCentre: MountedResults['applyCentre'] = (to) => {
    /* THE HOST'S OWN TRACKER FIRST, WHATEVER THIS ENTRY IS (B4.2). The page
       is told where the centre has moved to before anything is decided, so
       the early return below cannot leave `centreAt.current` behind: that
       tracker is what `closeResult` reads to know whether this result owns
       the entry it is on, and a stale one makes every maximised result look
       frame-only. It is this module that calls it, so no wiring can skip it. */
    page.enterCentre(to)
    if (!to?.result) {
      /* THE CENTRE SHOWS SOMETHING ELSE NOW (F16): a maximised result is
         drawn over the centre, so it goes back to its column or is given up.
         The 3D Brain is the page's own arm and is never touched here. */
      const max = maximised()
      const mine = max && max.content.kind !== 'brain-space' ? { viewer: max.id, from: max.from } : null
      for (const step of leaveSteps(mine)) {
        if (step.do === 'to-column') { moveViewer(step.viewer, step.column); results.moved(step.viewer, step.column) }
        else { closeViewer(step.viewer); results.forget(step.viewer) }
      }
      return false
    }
    const resume = resumeResult({ result: to.result }, { brainKey, live: (o) => !!launchOf(o), words: BRAIN_MOVED })
    for (const step of resumeSteps(resume, results)) {
      if (step.do === 'show-viewer') {
        /* the same viewer, shown again -- never a second one */
        const was = parkedPlaceOf(step.viewer)
        if (was) returnViewer(step.viewer, was.place, was.from)
        else if (step.where !== 'max') moveViewer(step.viewer, 'max')
        results.moved(step.viewer, 'max')
      } else if (step.do === 'resolve') {
        /* A RELOAD OWES THE PLACE THE ENTRY SAVED, not the one the reader
           happens to be on now (F13) -- AND IT IS A RESUME, NOT A PRESS
           (B4.4): the browser is already standing on this entry, so the
           entry it is standing on is corrected in place and no second one is
           pushed in front of it. Back still leaves the saved result. */
        const d = page.destinationOfTarget?.(step.target) ?? null
        if (!d) { page.say(NO_DESTINATION); page.offerReturn?.(launchForSaved(step.back)); continue }
        openResultTarget(d, launchForSaved(step.back), resuming, {})
      } else if (step.do === 'say') page.say(step.words)
      else page.leaveOn?.(step.place)
    }
    return true
  }

  return { openResult, has, launchNow, openView, closeResult, goToSource, applyCentre, dockStep, pressed, results, host }
}

/** The restore steps a launch owes, for a host that wants them itself. */
export { restoreSteps }
