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
import { actionOf, destinationOfRef, type ResolvedRef, type ResultDestination, type ResultTarget } from './targets'

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
  /** `centre.backTo(place, then)`: one step back to a WHOLE Place, and `then`
   *  runs only once the move has actually been applied */
  backTo: (place: LaunchPlace, then: () => void) => void

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

  /* the page's readers -- and nothing new */
  /** `heldItem(ref, about)` */
  heldItem: (ref: string, about: HeldBytes | null) => ViewerItem | null
  /** `postOf(post)`: the post this page has drawn, where it has */
  postOf?: (post: string) => unknown
  /** `picturesOf(post)`, asked only for a post there is */
  pictures?: (post: unknown) => readonly ViewImage[]
  /** the bound re-read on the press (`refRead.ts` `refNow`). Left out, the
   *  opener is `unchecked`, which is the behaviour before A4/P4 existed. */
  refNow?: (ask: string, ref: string) => Promise<ResolvedRef | null>
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

  /** a maximised result's one history entry, where it has an identity */
  const entered = (target: ResultTarget | null, launch: LaunchContext) => {
    if (!target) return
    page.centreGo(resultIntent(brainKey, launch.opening, target, launch.place))
  }

  const put = (content: Viewable, source: ViewerSource, target: ResultTarget | null, launch: LaunchContext, where: 'max' | Column): Shown => {
    const id = openViewer(content, source, where)
    const identity = identityOf(target, content)
    results.place(id, launch, identity, where, page.invoker())
    if (where === 'max') entered(identity, launch)
    return where
  }

  const openView: MountedResults['openView'] = (content, source, target, launch, settled) => {
    const columns = page.columns()
    if (!columns.length) return put(content, source, target, launch, 'max')
    const free = page.freeColumn()
    /* a column is `historyStep(…) === 'none'`: no entry, and no centre guard */
    if (free) return put(content, source, target, launch, free)
    page.choose({
      content, source, launch,
      decide: (chosen) => {
        if (chosen === 'cancelled' || chosen === 'none') { settled?.({ how: 'cancelled' }); return }
        settled?.({ how: 'completed', where: put(content, source, target, launch, chosen) })
      },
    })
    return 'choosing'
  }

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
     what became of it. */
  const host: OpenerHost = {
    brainKey,
    origin: page.origin(),
    file: (o) => {
      const read = fileContent(o, { item: page.heldItem, post: page.postOf, pictures: page.pictures })
      if ('why' in read) { page.say(read.why); return null }
      const source: ViewerSource = read.source ?? { kind: 'brain', brainKey: brainKey ?? '' }
      return openView(read.content, source, o.target, o.launch, o.settled)
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
    /* A4/P4: THE READ THAT EXISTS, by the request the row was drawn from
       (`refRead.ts`). A press with no request behind it has nothing to read
       by and says `unchecked` rather than pretending otherwise (F19). */
    read: page.refNow
      ? (ref, settled, launch?: LaunchContext): Read => {
        const ask = launch?.decision?.question ?? null
        if (!ask) return { how: 'unchecked' }
        void page.refNow!(ask, ref)
          .then((r) => settled(r ? { how: 'fresh', destination: destinationOfRef(r) } : { how: 'unchecked' }))
          .catch(() => settled({ how: 'unchecked' }))
        return { how: 'reading' }
      }
      : undefined,
    say: page.say,
  }

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
      const rest = i + 1
      if (runRestore(step.place, () => runClose(steps, rest, closing)) === 'waiting') return
    }
  }

  const closeResult: MountedResults['closeResult'] = (viewer) => {
    const launch = results.launchOf(viewer)
    const at = page.centreAt()
    const owns = !!at?.result && at.result.opening === results.openingOf(viewer)
    const plan = closeSteps(
      { viewer, where: whereOf(viewer), launch },
      { owns, conversation: page.conversation(), invoker: results.invokerOf(viewer), has: page.hasControl },
    )
    const run = () => runClose(plan.then, 0, viewer)
    /* THE HISTORY MOVE FIRST, and the rest inside its `then`: a reader who
       answers the guard with Stay never reaches the close (H7). */
    if (plan.history) page.backTo(plan.history.to, run)
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
           happens to be on now (F13). */
        const d = page.destinationOfTarget?.(step.target) ?? null
        if (!d) { page.say(NO_DESTINATION); page.offerReturn?.(launchForSaved(step.back)); continue }
        openResult(d, launchForSaved(step.back))
      } else if (step.do === 'say') page.say(step.words)
      else page.leaveOn?.(step.place)
    }
    return true
  }

  return { openResult, has, launchNow, openView, closeResult, goToSource, applyCentre, dockStep, pressed, results, host }
}

/** The restore steps a launch owes, for a host that wants them itself. */
export { restoreSteps }
