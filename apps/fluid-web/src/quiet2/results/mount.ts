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
  BRAIN_MOVED, actingWords, beginOpening, focusChoice, holdLaunch, launchOf, mayAct, servingKey, servingOfKey,
  type BrainKey, type DecisionLaunch, type Focusable, type FocusChoice, type LaunchContext,
  type LaunchFocus, type LaunchPlace, type Serving,
} from './launch'
import { latestOpening } from './launch'
import { servingNow } from './serving'
import type { SpaceBrainKey } from '../space/contract'
import { resultIntent, resumeResult, sameResult, type ResultIntent, type Shown } from './history'
import {
  closeSteps, dockStep, fileContent, leaveSteps, pressed, restoreSteps, resultViewers, resumeSteps, sourceSteps,
  type CloseStep, type Column, type PlaceStep, type ResultViewers,
} from './hostOpen'
import {
  openResultTarget, type MayMove, type Navigation, type Opened, type OpenerHost, type Placed, type Read,
} from './opener'
import { confirmBrain } from '../../brainBinding'
import { COULD_NOT_CHECK, artifactNow, type FreshArtifact } from './refRead'
import { freshlyOpen, pressedOf } from './refNow'
import { checkResultOpen, type RefAnswer } from '../../work/freshness'
import type { WorkDetail } from '../../work/contract'
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

/** WHAT A PAGE MOVE ASKS BEFORE IT MOVES, AND GETS THE MOVE'S OWN INPUTS FROM
 *  (re-review adm-e2d35bd306b8, F4).
 *
 *  A guarded move is made in two parts: the press asks, and the reader answers
 *  Go or Stay some time later. The Brain the server serves can change in
 *  between -- another instance, another corpus, or a write refused as another
 *  Brain's -- and the page then moved anyway, because every identity check
 *  this contract had ran on the press. So the move asks THIS, inside the
 *  guard, at the moment it would move:
 *
 *    `{ ref, moved }`  go on: `ref` is what to open, and `moved` is told once
 *                      the page has ACTUALLY moved
 *    `null`            do not move at all. The reader has already been told
 *                      why, in the words of the state the page is in
 *
 *  IT IS ALSO THE ONLY SOURCE OF THE REFERENCE AND OF THE COMPLETION REPORT,
 *  which is deliberate: a host cannot make the move without asking, because
 *  without asking it has nothing to move to and nothing to report with. */
export type BeginMove = () => { ref: string; moved: () => void } | null

/** EVERYTHING THE SHARED HOSTS SUPPLY, and nothing else. Each member is a
 *  function `Quiet2.tsx` already has; where a baseline function hides the
 *  guard's answer behind a `void` or a `boolean`, the three ends are explicit,
 *  because reporting a pending guard as an arrival is what B3 was. */
export interface ResultPage {
  /** `brain.key` -- THE 3D BRAIN'S GRAPH KEY (`space/registry.ts`
   *  `spaceBrainKey`: origin, pinned proxy, corpus), and used for exactly one
   *  thing: the `ViewerSource` a file opened FROM THE BRAIN rather than from a
   *  post is shown with, whose `brainKey` is a `SpaceBrainKey` by contract.
   *
   *  IT IS NOT THIS PAGE'S BRAIN IDENTITY, and a result decision never reads
   *  it. The graph key cannot tell two serving instances of one corpus at one
   *  origin apart, and the hand-off supplied it for both jobs: a result saved
   *  against the old instance resumed against the new one (independent
   *  re-review adm-af5263a65134, F2). Which Brain the server serves is
   *  `serving.ts`'s, from `brainBinding.ts`, and is not a host member at all. */
  spaceKey: () => SpaceBrainKey | null
  /** WHICH BRAIN THE SERVER SERVES, FOR THE CHECKS ONLY -- as `artifactNow`
   *  below is, and for the same reason. The real answer is `serving.ts`'s
   *  `servingBrainKey()`, a module read of the binding every write already
   *  names, so that a read or a chooser begun by an EARLIER RENDER sees today's
   *  answer rather than the one its own render closed over (F1). A page
   *  supplies none and gets the real one. */
  serving?: () => BrainKey | null
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
   *  which Stay could keep them.
   *
   *  AND IT ASKS BEFORE IT WALKS, LIKE EVERY OTHER GUARDED MOVE (independent
   *  re-review adm-33bc95d78f7a, F7). `begin` is called INSIDE the guard,
   *  immediately before `centre.backTo`: an answer moves the history and runs
   *  `then`, and `null` leaves the history, the conversation and the viewer
   *  exactly as they are. A close is not an opening, but the Place it puts
   *  back is the OLD Brain's -- its conversation, its thread, its reply
   *  target -- and a page that has positively observed another Brain may not
   *  be sent back into it. Left out, the walk is unguarded, which is the
   *  behaviour this replaces. Only the YES OR NO of that answer is this
   *  route's: what runs after the move is `then`, which the close already
   *  supplies, so the answer's own `moved` is nothing here. */
  backTo: (place: LaunchPlace, then: () => void, stay: () => void, begin?: BeginMove) => void

  /* THE PAGE'S NAVIGATION, EACH WITH THE UNSAVED-WORK GUARD'S THREE ENDS --
     AND WITH THE MOVE ITSELF ASKING `begin` FIRST (F4). `begin` is called
     INSIDE the guard, where the page is about to move: it answers the
     reference to open and the report to make once the page has moved, or
     `null` where the Brain under the move has changed since the press and
     nothing may be moved, opened, written to the history or saved. */
  /** `pickConversation(k, begin, stay)`: false where there is no such route.
   *  `k` is still given, because whether there is a route at all is answered
   *  on the press; what `begin` answers is whether the move may be MADE. */
  pickConversation: (k: string, begin: BeginMove, stay?: () => void) => boolean
  /** `openFromDock(c, p, begin, done)`: the thread read and its guard. The
   *  conversation move it makes is the same guarded move, so it is asked the
   *  same way; `done` carries its cancellation and its missing route.
   *
   *  AND THE THREAD READ IS ASKED TOO, WHERE IT LANDS (independent re-review
   *  adm-33bc95d78f7a, F5). `begin` guards the CONVERSATION MOVE, which is
   *  only half of this route: a post not already drawn is reached by reading
   *  its thread, that read is asynchronous, and the server can begin serving
   *  another Brain while it is in flight. The old contract then applied the
   *  answer -- the thread entered, the reply target cleared, the surfaces
   *  rewritten -- and only afterwards found the completion report refused, so
   *  the page had already been changed under a Brain nobody was reading.
   *  `may` is the launch's own identity, asked at the moment the read would
   *  touch the page: words mean it is no longer the Brain served, and then
   *  NOTHING is entered, cleared or rewritten and the route reports `refused`
   *  rather than `completed`. It is the same check `begin` makes, at the
   *  route's other end, and it says nothing to the reader itself -- the
   *  opener's own report is where the words are said, once. */
  openPost: (conversation: string, post: string, done: (n: Navigation) => void, begin: BeginMove, may: MayMove) => void
  /** `enterBrain({page:'record',entry}, {from:'link'})` WITH ITS GUARD'S ENDS:
   *  `begin` immediately before the record page is shown (and the record it
   *  shows comes from its answer), `stay` where the reader kept what they had.
   *  The baseline's own `guarded` already takes both ends. */
  record: (begin: BeginMove, stay: () => void) => void
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
  /** WHO IS READING, for the result page the P4 check re-reads
   *  (`/api/work/<work>?viewer=`). Left out, the route answers to its own
   *  default viewer; what it says about READABILITY does not depend on who
   *  asks (`tests/test_result_readability_contract.py`), so leaving it out
   *  loses no truthfulness -- only the page's ordinary viewer scoping. */
  viewer?: () => string | null
  /** THE P4 READ, FOR THE CHECKS ONLY, as `artifactNow` is for the artifact
   *  route. The page supplies none and gets the real one (`api.read`). */
  resultNow?: (path: string) => Promise<WorkDetail>
  /** Test seam for the authorized exact-reference reader. Production omits it. */
  refNow?: (path: string) => Promise<RefAnswer>
  /** ASKING THE SERVER AGAIN WHICH BRAIN IT SERVES, FOR THE CHECKS ONLY. The
   *  ask itself is `brainBinding.ts`'s own `confirmBrain`, which the page
   *  already makes at startup and before an unbound write; a page supplies
   *  none and gets the real one. See `askServingAgain` below for what starts
   *  it and what bounds it. */
  confirmServing?: () => Promise<unknown>
  /** N-B's adapter from a stored target back to a destination. Left out, an
   *  entry whose viewer has gone shows its Place and says so. */
  destinationOfTarget?: (t: ResultTarget) => ResultDestination | null

  /* the rest of a launch's Place, which only the page can put back */
  /** one restore step the page applies: thread, reading, reply or draft key */
  putBack: (step: PlaceStep) => void
  /** ONCE THE PAGE HAS DRAWN WHAT WAS JUST PUT BACK (independent rendered
   *  review adm-d4c77f502b8c, F3 and F5). Only the host knows when the pane a
   *  restore asked for exists: a restore writes the page's own state, and the
   *  element focus is meant to land on -- the control the reader pressed, the
   *  restored conversation's heading -- is not in the document until that
   *  render has happened. Nothing here waits for anything else, and a host
   *  that supplies none (every check) runs it at once, which is the old
   *  behaviour exactly. */
  after?: (fn: () => void) => void
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

/* ONE ASK IN FLIGHT FOR THE PAGE, NOT FOR THE RENDER (independent re-review
   adm-33bc95d78f7a, N6). `askServingAgain`'s bound is "at most one ask at a
   time", and it was declared inside `mountResults` -- which the host calls on
   EVERY render. Two presses either side of a render therefore each found their
   own flag false and each asked, which is the one thing that bound forbids. It
   lives beside the registry above for the same reason the registry does: the
   page outlives its renders. */
let askingServing = false

/** A CLOSE WHOSE HISTORY WALK HAS BEEN ALLOWED AND HAS NOT LANDED YET
 *  (re-review adm-e33f82f008d4, F7-R2; adm-8f0c09e4f218, F7-R2a).
 *
 *  `history.go` is answered by the browser whenever it answers, and the
 *  landing runs `applyCentre` -- which takes a maximised result off the centre
 *  (F16) -- BEFORE the close's own continuation. So the close's identity check
 *  has to be reachable from there: this is how that landing knows which close
 *  it belongs to, and whose question to ask. It is set only where the walk was
 *  allowed, and taken by the first landing after it or by the continuation
 *  itself, whichever comes first.
 *
 *  AND IT IS THE PAGE'S, NOT THE RENDER'S (F7-R2a). It was declared inside
 *  `mountResults`, which the documented host calls on EVERY render
 *  (`const R = mountResults(resultPage)`). A render between the reader's Go and
 *  the browser's pop -- the Go button's own `setLeave(null)`, a binding change,
 *  any state the page keeps -- therefore handed the landing to a mount whose
 *  marker was a fresh `null`: F16 gave up the viewer and forgot its launch, and
 *  the continuation's refusal came too late to keep either. It lives beside the
 *  viewer registry, the recovery flag and the centre generation above, and for
 *  exactly their reason: the page outlives its renders.
 *
 *  AND IT BELONGS TO ONE CLOSE, WHICH IS THE ONLY ONE THAT MAY TAKE IT OR SET
 *  IT (independent re-review adm-e8508cf186c0, B1). Being the page's made it
 *  reachable by every OTHER close the page makes, and two of them took it:
 *
 *    - every close CLEARED it. `run` is the continuation of the close that is
 *      running, and it cleared the module marker whoever had set it -- so
 *      closing an unrelated viewer, which makes no history move at all and
 *      reaches `run` on the press itself, threw away a pending close's gate.
 *      An ordinary picture in a working column is such a viewer (N3), and once
 *      the reader has moved the closing result into a column there is nothing
 *      maximised over the work row to stop them pressing its Close: the gate
 *      went, the landing afterwards was nobody's, and the page was written back
 *      into the old Brain's record, source column or Sources browser -- F7-R2c
 *      again, by a control the reader can see.
 *    - and a second close would have CLAIMED it, out of a walk the history
 *      helper refuses while the first one is outstanding (`centreHistory`
 *      `moving`), leaving the first close's landing to be asked under the
 *      second's identity and the second close waiting for a pop that will
 *      never come.
 *
 *  So the marker names its OWNER and ownership is checked at both ends: `run`
 *  takes it only where it is still this close's, and a claim is made only where
 *  no other close holds one. The landing itself still takes whatever marker is
 *  outstanding, because a landing is one close's or none (F7-R2a), and with one
 *  owner at a time there is only ever one to take.
 *
 *  AND THE OWNER IS THE OPERATION, NOT THE VIEWER (independent re-review
 *  adm-012c2c2a3987, B1-R2). Naming the viewer rejects every OTHER viewer's
 *  close, which is what B1 was about -- but it cannot tell WHICH close of the
 *  same viewer owns the pending walk, and a reader has two of those:
 *
 *    the result is closed with Close and Go while it is maximised (one walk,
 *    outstanding), the reader then moves it into a column -- its own maximised
 *    frame's Move to column, which also makes the work row live again -- and
 *    presses THAT frame's Close. A close from a column walks no history, so its
 *    continuation runs on the press itself, and `walking.viewer === viewer`
 *    matched: it cleared the first close's gate, and the pop the browser had
 *    not answered yet landed as nobody's -- the old Brain's record, source
 *    column or Sources browser written back out of the very centre the first
 *    close was walking towards, under an identity nobody is being served.
 *
 *  Each press of a Close is one OPERATION, with its own plan, its own invoker,
 *  its own words and its own identity question, and it is operations that own a
 *  pending landing. So `closeResult` numbers its own and the marker carries
 *  that number: a continuation gives up only the gate IT set, however many
 *  closes of that viewer there have been. The claim still refuses another
 *  VIEWER's close -- a later operation on the same viewer asks the same
 *  question of the same launch, so the gate it claims is the one it replaces,
 *  and each press keeps its own words -- while no operation whatever may throw
 *  another's away. */
let walking: { op: number; viewer: string; may: () => boolean } | null = null

/** WHICH CLOSE: one number per press of a Close, so the marker above can say
 *  which operation set it. Never reset -- a number given out once is never
 *  given out again, so no continuation can mistake a later close's gate for
 *  its own. */
let closes = 0

/* -- WHICH NAVIGATION IS CURRENT (re-review adm-efb406a34e7a, B4.4-R1) ------
 *
 * THE DEFECT THIS ANSWERS. Resuming a saved result corrects THE ENTRY THE
 * BROWSER IS STANDING ON, which is right -- but the read that resolves it
 * answers a moment later, and "the entry the browser is standing on" is read
 * again then. A reader who pressed Back (or Forward onto the saved result and
 * then Back) in that moment had the Place they reached REPLACED by the result
 * and a viewer drawn over it: the entry Back had just arrived at was removed
 * from its own history slot. `acceptsLate` did not catch it, because leaving a
 * result entry begins no opening of its own, so the resume was still the
 * newest one; and the page's entry tracker did not either, because it had
 * already been moved on to the Place being replaced.
 *
 * SO WHAT IS CURRENT IS COUNTED. One generation per centre move, whatever it
 * moves to, and a pending resume carries the generation, the exact entry and
 * the Brain key it was begun for. Nothing it does is allowed unless all three
 * still hold. A MODULE STORE, like the viewer registry above it: `mountResults`
 * runs on every render, so the resume is completed inside the closure of the
 * render that began it, and only something outside them both can tell it that
 * the centre has moved since. */
let generation = 0
/** how many times the centre has moved, for a resume to be judged against */
export const centreGeneration = (): number => generation

/** Thrown away between test cases, exactly as `clearLaunches` is. */
export const resetPlacedResults = () => { store = resultViewers(launchOf); generation = 0; askingServing = false; walking = null }

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
  /** THE EXPLICIT WAY BACK, TAKEN AS A GATED OPERATION (independent rendered
   *  review adm-d4c77f502b8c, F2 and F3).
   *
   *  The bar the close OFFERS is applied here and nowhere else: the launch's
   *  own serving identity is checked at the moment the page would be written
   *  to, and again after any guard the reader held open, exactly as a close's
   *  moves are. `settled` says which happened -- `returned`, so the host can
   *  take the bar down, or `refused`, so it KEEPS it: a refusal leaves the
   *  reader where they are with the way back still offered, and never consumes
   *  it. */
  takeReturn: (launch: LaunchContext, settled?: (how: 'returned' | 'refused') => void) => void
  /** go to source, which is not close (H3) */
  goToSource: (viewer: string, source: { conversation: string; post: string }) => void
  /** the centre's `apply`, for a result entry AND for leaving one. True where
   *  this handled the entry; false leaves the page's other arms to it.
   *
   *  A LANDING THIS REFUSES IS HANDLED, NOT LEFT (F7-R2b): where the entry is
   *  the landing of a close whose Brain has moved since the walk was allowed,
   *  the viewer and its launch are kept and NOTHING of the landed entry is
   *  applied -- so this answers true, and the host's own record, source and
   *  Sources arms do not run on the old Brain's saved centre. */
  applyCentre: (to: CentreAt) => boolean
  /** what the dock does with an answer, and whether the press did anything */
  dockStep: typeof dockStep
  pressed: typeof pressed
  results: ResultViewers
  /** the host as the opener sees it, for the page's own direct calls */
  host: OpenerHost
}

export function mountResults(page: ResultPage, results: ResultViewers = placedResults()): MountedResults {
  /** WHICH BRAIN THE SERVER SERVES, ASKED AGAIN EVERY TIME IT MATTERS (F1).
   *  Not captured here: a mount belongs to one render, and the whole defect
   *  was a render's own answer outliving the render. Every reader below calls
   *  this, so the oldest pending closure and the newest press read the same
   *  module store. */
  /** AND IN WHICH OF ITS THREE STATES (F3): a confirmed Brain, no answer yet,
   *  or moved. A page that supplies its own key getter is read fail-closed
   *  through `servingOfKey` -- a check that answers `null` is a page that
   *  cannot say, never a page that is exempt. */
  const servingState: () => Serving = page.serving ? () => servingOfKey(page.serving!()) : servingNow
  const serving = (): BrainKey | null => servingKey(servingState())
  /** THE GRAPH KEY, and nothing but the viewer's source (F2). */
  const spaceKey = page.spaceKey()
  /** ONCE THE PAGE HAS DRAWN IT, or at once where the host says nothing. */
  const after = (fn: () => void) => { if (page.after) page.after(fn); else fn() }
  /** the fresh read: this part's own, unless a check injected one */
  const readFresh = page.artifactNow ?? ((ref: string) => artifactNow(ref))

  /** A WAY OUT OF A CONFIRMATION THAT FAILED (re-review adm-e2d35bd306b8,
   *  recovery limitation). A page whose one startup ask failed -- the server
   *  answered 503 while it was starting, say -- is `unconfirmed` for the rest
   *  of its life: it refuses every result press with "try again in a moment",
   *  and nothing here ever asked again, so trying again was the same refusal
   *  for ever. The ask is the page's own `confirmBrain`: a read of
   *  `/fluid/api/needs-you/brain` that binds the page where the server names a
   *  Brain and changes nothing where it does not.
   *
   *  WHAT STARTS IT, AND WHAT BOUNDS IT -- because this is not a retry loop
   *  and must not become one. A READER'S PRESS that was refused for want of a
   *  confirmed Brain starts it, and nothing else does: no timer, no poll, no
   *  wake, and nothing retries the press itself. At most one ask is in flight;
   *  a press made while one is already going starts none. A page that has
   *  MOVED is never asked, because only a reload binds that one. The press
   *  that started it is still refused -- the answer is not waited for -- and
   *  what it buys is that the NEXT press has something to find. */
  const askAgain = page.confirmServing ?? (() => confirmBrain())
  const askServingAgain = () => {
    /* THE FLAG IS THE PAGE'S, NOT THIS MOUNT'S (N6): `mountResults` runs on
       every render, so a flag declared here was a fresh `false` for each one
       and two presses across a render both asked. */
    if (askingServing || servingState().how !== 'unconfirmed') return
    askingServing = true
    let answer: Promise<unknown>
    /* started on the press, not on a microtask after it: the press is refused
       either way, and the point is that the ask is already going */
    try { answer = Promise.resolve(askAgain()) } catch { askingServing = false; return }
    void answer.catch(() => null).then(() => { askingServing = false })
  }

  /* -- where the reader is, as a launch ------------------------------------ */
  const launchNow: MountedResults['launchNow'] = (place, focus, decision = null, reading = null, thread = null, reply = null, draft = null) =>
    holdLaunch({ opening: beginOpening(), brainKey: serving(), place, thread, reading, reply, draft, focus, decision })

  /** A LAUNCH FOR A PLACE THE HISTORY SAVED (F13). A reload has taken the live
   *  launch with it; what the entry holds is the Place it was over, and that
   *  Place -- not wherever the reader happens to be now -- is what the
   *  re-resolved result owes them. Nothing else is promised: no draft, no
   *  focus, no reply target (H8). */
  const launchForSaved = (back: LaunchPlace): LaunchContext =>
    holdLaunch({
      opening: beginOpening(), brainKey: serving(), place: back, thread: null, reading: null,
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

  /** WHAT A PENDING RESUME IS BOUND TO (re-review adm-efb406a34e7a, B4.4-R1).
   *
   *  A resume is begun by landing on a result entry and finished when its read
   *  answers. Between the two the reader can move: their own Back, their own
   *  Forward, a press of the page's. So the resume records WHICH ENTRY it is
   *  resolving and WHEN -- the centre's generation at the moment it landed, the
   *  entry exactly as the history holds it, and the Brain key this page was
   *  bound to -- and `holds` requires all three to be true still. */
  interface Resume {
    /** `centreGeneration()` when this entry was landed on */
    generation: number
    /** the entry being resolved, as `resumeResult` read it */
    entry: ResultIntent
    /** the Brain the server was serving then, instance included */
    brainKey: BrainKey | null
  }

  /** WHICH ENTRY A MAXIMISED OPEN OWES (re-review adm-d84456fd4c3c, B4.4).
   *
   *    'new'    an explicit press: a displacement that was not one before, so
   *             one entry is PUSHED and Back returns to where they pressed it
   *    a Resume a result entry the browser has already landed on, being
   *             resolved again (a reload, or Back or Forward onto a saved
   *             result): THE ENTRY ALREADY EXISTS, and its identity is
   *             corrected in place -- for as long as it is still the entry
   *             the browser is standing on
   *
   *  Pushing on a resume is what defeated Back: landing on the saved entry
   *  made a second entry in front of it, so Back came straight back to the
   *  new one and resolved the saved result afresh -- a new opening and a new
   *  viewer every time, with no way out of it. Replacing WHATEVER IS CURRENT
   *  WHEN THE READ ANSWERS is what defeated it the other way round, and is
   *  what `holds` refuses. */
  type Entry = 'new' | Resume

  /** WHETHER A RESUME MAY STILL ACT (B4.4-R1). An explicit press always may:
   *  it is acting on the entry it is itself about to make. A resume may only
   *  while the centre has not moved since it landed, while the entry it is
   *  resolving is still the one the page is on, and while the Brain is the
   *  same one. Otherwise the reader is somewhere they chose, and that Place is
   *  theirs: nothing is placed, nothing is replaced, and nothing is said --
   *  there is nothing to tell them about a resume they navigated away from. */
  const holds = (entry: Entry, launch?: LaunchContext | null): boolean => {
    /* THE BRAIN THE SERVER SERVES NOW, read through the module (F1): not the
       mount's own captured answer and not this render's getter, so a read or a
       chooser begun by an earlier render is judged against today's Brain even
       though the centre has not moved and this closure never will again. */
    const now = servingState()
    /* AN OPENING MAY ACT LATE ONLY UNDER THE IDENTITY IT WAS MADE WITH -- the
       same rule `openResultTarget` applies on the press, applied again when the
       answer actually comes back, because that is when F1's placements
       happened. AN OPENING THAT NAMED NO BRAIN IS NOT EXEMPT FROM IT (F3):
       `launch?.brainKey &&` let a read or a chooser begun while this page could
       not say which Brain it was on place its content whatever had answered in
       the meantime, which is both the bypass and how such an operation came to
       be written into the history under an identity it never had. */
    if (mayAct(launch?.brainKey ?? null, now) !== 'act') return false
    if (entry === 'new') return true
    /* the centre has moved since this entry was landed on */
    if (entry.generation !== generation) return false
    /* and -- read from the page's own tracker, which `applyCentre` sets before
       it decides anything -- it is still standing on this very entry */
    const at = page.centreAt()
    if (!at?.result || !sameResult(at.result, entry.entry)) return false
    /* THE EXACT BRAIN IDENTITY, instance included: a page whose server has
       begun serving another Brain -- or another instance of the same corpus,
       or one it can no longer name at all -- replays nothing. A resume that
       landed with no identity is refused by the same rule, rather than matching
       a second absence of one. */
    return mayAct(entry.brainKey, now) === 'act'
  }

  /** a maximised result's one history entry, where it has an identity */
  const entered = (target: ResultTarget | null, launch: LaunchContext, entry: Entry) => {
    if (!target) return
    /* THE ENTRY NAMES THE LAUNCH'S OWN IDENTITY, AND IS WRITTEN ONLY WHILE THAT
       IS STILL WHAT IS SERVED (F3). `serving()` at this moment is the identity
       the page has NOW, which for an opening made before the page bound is one
       it never had: writing it here is how an unidentified operation acquired a
       known Brain at completion. The two are the same string wherever this is
       reached at all, because the gate above admits nothing else -- which is
       the point: it is checked rather than assumed. */
    if (mayAct(launch.brainKey, servingState()) !== 'act') return
    const intent = resultIntent(launch.brainKey, launch.opening, target, launch.place)
    /* THE SAVED TARGET AND THE SAVED PLACE ARE KEPT (F13): what the resumed
       entry gains is only the opening that is now showing it, so the close
       plan, the leave arm and `resumeSteps` all find the live viewer. */
    if (entry === 'new') { page.centreGo(intent); return }
    /* AND ONLY THE ENTRY THIS RESUME WAS BOUND TO IS CORRECTED (B4.4-R1):
       never whatever entry happens to be current when the read answers. */
    if (holds(entry, launch)) page.centreReplace(intent)
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
        /* THE READER'S CHOICE ALSO COMES BACK LATER (B4.4-R1): a resume whose
           entry has been navigated away from while the chooser was open places
           nothing, exactly as its read would not have -- AND NEITHER DOES ANY
           CHOICE, PRESS OR RESUME, ONCE THE SERVER SERVES ANOTHER BRAIN (F1).
           A column placement applies no centre entry, so this gate is the only
           one a chosen column ever passes. */
        if (!holds(entry, launch)) { settled?.({ how: 'cancelled' }); return }
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
  /*  AND WHAT IT ASKS BEFORE IT MOVES (re-review adm-e2d35bd306b8, F4). The
   *  guard can stay open for as long as the reader takes to answer, and the
   *  Brain the server serves can change while it is. `may` is the opener's own
   *  check, carrying the LAUNCH's identity, and it is asked here, inside the
   *  guard, at the moment the route would run -- so a move whose Brain has
   *  moved is never made, rather than made and then reported as something
   *  else. It is asked again when the move reports, which is the cheap second
   *  net for a host that moved without asking: such a host still cannot report
   *  an arrival. */
  const guardedMove = (
    settled: (n: Navigation) => void,
    may: MayMove,
    ref: string,
    ask: (begin: BeginMove, say: (n: Navigation) => void) => boolean | void,
  ): Navigation => {
    let onPress: Navigation | null = null
    let returned = false
    let said = false
    const say = (n: Navigation) => {
      if (said) return
      said = true
      if (returned) settled(n)
      else onPress = n
    }
    /* AND AN ARRIVAL IS NOT REPORTED UNDER A BRAIN THAT HAS MOVED EITHER.
       This is the second net, not the gate: it keeps a host that moved
       without asking from reporting that it arrived, which is all a report
       can do. Suppressing the report is why `begin` exists -- it is not a
       substitute for it. Every other answer passes through untouched. */
    const report = (n: Navigation) => {
      const how = typeof n === 'string' ? n : n.how
      if (how !== 'completed') { say(n); return }
      const late = may()
      say(late ? { how: 'refused', why: late } : n)
    }
    const begin: BeginMove = () => {
      const why = may()
      if (why) { say({ how: 'refused', why }); return null }
      return { ref, moved: () => report('completed') }
    }
    const could = ask(begin, report)
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
    /* ASKED, NOT REMEMBERED (F1). `openResultTarget` checks this against the
       launch's own Brain before it resolves anything, and it is re-entered
       when a fresh read answers -- which is exactly the moment the page may
       have been rebound since. A captured key makes that second check say
       what the first one said, whatever has happened in between. */
    get brainKey() { return serving() },
    /* AND WHICH STATE THAT ANSWER IS (F3): the opener refuses an opening made
       with no confirmed identity, which a key alone cannot tell it. Read at
       every call, like the key beside it and for the same reason. */
    serving: servingState,
    spaceKey,
    origin: page.origin(),
    file: (o) => {
      const read = fileContent(o, { item: page.heldItem, post: page.postOf, pictures: page.pictures })
      if ('why' in read) { page.say(read.why); return null }
      const source: ViewerSource = read.source ?? { kind: 'brain', brainKey: spaceKey ?? '' }
      return place(read.content, source, o.target, o.launch, o.settled, entry)
    },
    /* BOTH ENDS OF THIS ROUTE ASK (F5): `begin` guards the conversation move,
       and `may` is the same check for the thread read that lands afterwards,
       before it touches the page at all. */
    post: (conversation, post, settled, may) =>
      guardedMove(settled, may, conversation, (begin, say) => { page.openPost(conversation, post, say, begin, may) }),
    /* THE RECORD PAGE IS GUARDED LIKE EVERY OTHER CENTRE MOVE (F09). The
       baseline's `enterBrain` is `guarded(() => centre.go(…))`: a pending
       unsaved-work question is not an arrival, and Stay prevents the move
       altogether. Reporting `'completed'` on the press was the original
       false departure, on the one route that still had it. */
    record: (ref, settled, may) => guardedMove(settled, may, ref, (begin, say) => { page.record(begin, () => say({ how: 'cancelled' })) }),
    conversation: (ref, settled, may) => guardedMove(settled, may, ref, (begin, say) => page.pickConversation(ref, begin, () => say({ how: 'cancelled' }))),
    external: page.external,
    /* AND A WAY OUT OF A CONFIRMATION THAT FAILED (recovery limitation): the
       opener asks this when a press found no confirmed Brain at all, so that
       pressing again is a recovery rather than the same refusal. */
    confirm: askServingAgain,
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
    read: (d, settled, launch): Read => {
      const t = d.target
      /* A POST, A BRAIN RECORD OR A CONVERSATION IS ASKED ABOUT AGAIN TOO (P4,
         discovered work ent-ad53f85e4add). Their guarded readers report the
         guard and the move, never whether the target is still readable, so a
         denied, deleted or unreadable one used to be found out by ARRIVING at
         it. `refNow.ts` turns this destination into the one result-page read
         that answers for it; only "still there, and still the same kind of
         thing" lets the open through, and the answer carries the server's own
         words. Without a Work/group it uses the exact-reference reader; a
         failure or refusal never falls back to the old destination. */
      if (t.kind !== 'artifact') {
        const p = pressedOf(d, launch?.brainKey ?? null, centreGeneration())
        if (!p) return { how: 'unchecked' }
        const answer = (r: Read) => {
          if (launch && launch.opening === latestOpening() && holds(entry, launch)) settled(r)
        }
        void checkResultOpen(p, {
          viewer: page.viewer?.() ?? null,
          /* asked when the ANSWER lands, never before: a reader who moved on
             is dropped here exactly as a late resume is above. */
          now: () => ({ brain: serving(), moved: false, moves: centreGeneration() }),
          read: page.resultNow,
          readRef: page.refNow,
        }).then((c) => {
          if (c.how === 'dropped') return
          answer(c.how === 'open'
            ? { how: 'fresh', destination: freshlyOpen(d, c) }
            : { how: 'gone', why: c.why })
        }).catch(() => answer({ how: 'gone', why: COULD_NOT_CHECK }))
        return { how: 'reading' }
      }
      /* AND AN ANSWER FOR AN ENTRY THE READER HAS LEFT IS NOT AN ANSWER AT ALL
         (re-review adm-efb406a34e7a, B4.4-R1). This is where a resume becomes
         asynchronous, so it is where it is dropped: the open never happens, no
         viewer is made, no entry is replaced and the reader is told nothing,
         because they asked for none of it -- they pressed Back. An explicit
         press is unaffected; its own lateness is `acceptsLate`'s. */
      /* AND AN ANSWER FOR A BRAIN THE SERVER NO LONGER SERVES IS NOT AN ANSWER
         EITHER (F1): this closure belongs to the render that began the read,
         and `holds` reads the Brain through the module rather than through
         that render, so a page rebound without any centre move drops it. */
      const answer = (r: Read) => { if (holds(entry, launch)) settled(r) }
      void readFresh(t.ref)
        .then((f) => answer(f.how === 'held'
          ? { how: 'fresh', destination: freshly(d, f) }
          : { how: 'gone', why: f.why }))
        .catch(() => answer({ how: 'gone', why: COULD_NOT_CHECK }))
      return { how: 'reading' }
    },
    say: page.say,
  })

  const host = hostFor('new')

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
    /* PARKED IS NOWHERE, AND SO IS THE MAGNET'S CANVAS (integration with the
       TEST baseline 90f5642, which added `'canvas'` to the viewer store's
       places). `Shown` is where a RESULT can be shown -- maximised, or one of
       the two working columns -- and a viewer on the Magnet canvas is in
       neither, so it displaces no centre and owns no history entry. Nothing
       here claims a result can be placed there. */
    return v.place === 'parked' || v.place === 'canvas' ? 'none' : v.place
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
  const runRestore = (steps: readonly PlaceStep[], then: () => void, may: CloseMay): 'waiting' | 'done' => {
    const first = steps[0]
    /* AND A RESTORE THAT NEEDS NO CONVERSATION PRESS IS STILL THE OLD BRAIN'S
       (re-review adm-e33f82f008d4, F7-R1 and F7-R2).

       THE DEFECT THIS ANSWERS: the gate was on the two MOVES a close makes --
       the history walk and the conversation press -- and this arm makes
       neither, so it put the page back with nothing asked. Two normal closes
       reach it. A viewer opened into a column from the conversation it was
       launched in restores its thread, position and reply target WITHOUT a
       conversation step, because the reader is already in that conversation
       (`restoreSteps`: the step is added only where it differs); and the
       history-owned close reaches it a second time, in the continuation the
       browser runs after its `history.go` lands -- an answer that arrives
       later, under whatever Brain is being served THEN.

       So the question is asked here too, where the page is actually written
       to, and a refusal stops the whole close: `waiting` returns out of
       `runClose` with the steps after this one -- the focus and the forget --
       not taken, so the viewer, its launch and the reader's current thread,
       position and reply target are kept exactly as Stay keeps them. The
       words are the close's own, said once for the whole close. */
    if (first?.do !== 'conversation') {
      if (!steps.length) return 'done'          // nothing to put back: no move to ask about
      if (!may()) return 'waiting'              // refused, and the reader told: nothing is put back
      applyPlace(steps)
      return 'done'
    }
    const rest = steps.slice(1)
    /* AND THE RESTORE ASKS BEFORE IT MOVES, UNDER THE CLOSING RESULT'S OWN
       LAUNCH (independent re-review adm-33bc95d78f7a, F7).

       THE DEFECT THIS ANSWERS: the restore supplied a `begin` that always said
       yes -- "a close has no result identity to carry" -- and so the one
       always-yes answer in this module was the one that put an OLD Brain's
       conversation, thread and reply target back. The guard holds the question
       open for as long as the reader takes, and the server can begin serving
       another Brain while it does; answering Go then opened that conversation,
       pushed a history entry, saved the workspace and gave up the viewer and
       its launch, under an identity nobody was being served. A close DOES have
       an identity: it is the launch the closing viewer was opened under, which
       `closeResult` already reads for its focus choice. `begin` carries it. */
    const could = page.pickConversation(
      first.conversation,
      () => (may() ? { ref: first.conversation, moved: () => { applyPlace(rest); then() } } : null),
      () => {},
    )
    /* no route to it: nothing is restored and nothing is given up either */
    if (could === false) { page.say(COULD_NOT_RETURN); return 'waiting' }
    return 'waiting'
  }

  /** THE CLOSING VIEWER, AS IT WAS WHEN THE PLAN WAS MADE (re-review
   *  adm-efb406a34e7a, N2). Its registry row does not survive the close: the
   *  guarded history move runs FIRST, and landing on an ordinary entry takes
   *  a maximised result off the centre (F16) -- which forgets the row. So by
   *  the time the focus step ran, `results.invokerOf(viewer)` was null and the
   *  element the plan had chosen was never focused. */
  interface Closing { invoker: Focusable | null; launch: LaunchContext | null }

  /** THE CLOSING RESULT'S OWN IDENTITY CHECK, for the moves a close makes
   *  (F7). The launch is the one the viewer was opened under, held from the
   *  plan like the invoker beside it, and read HERE rather than captured: the
   *  question is what the server serves at the moment the page would move, not
   *  what it served when the close was pressed.
   *
   *  A viewer with no launch -- an ordinary picture this contract never
   *  registered (N3) -- has no identity to check and is closed as it always
   *  was. Words are said once, by this, because a close has no opener report
   *  to carry them. */
  type CloseMay = () => boolean

  const closeMay = (closing: Closing, said: { yet: boolean }): CloseMay => () => {
    const launch = closing.launch
    if (!launch) return true
    const late = mayAct(launch.brainKey, servingState())
    if (late === 'act') return true
    if (!said.yet) { said.yet = true; page.say(actingWords(late)) }
    return false
  }

  const runClose = (steps: readonly CloseStep[], from: number, closing: Closing, may: CloseMay) => {
    for (let i = from; i < steps.length; i++) {
      const step = steps[i]
      if (step.do === 'forget') { closeViewer(step.viewer); results.forget(step.viewer); continue }
      /* THE CLOSING VIEWER'S OWN INVOKER, HELD FROM THE PLAN (N2) -- and the
         choice decided against the element that is actually there NOW: a
         guarded restore can unmount the pane the invoker was in, and `{how:
         'invoker'}` with nothing to focus is how H6's return was lost. */
      /* AND DECIDED ONCE THE RESTORED PANE IS ACTUALLY DRAWN (independent
         rendered review adm-d4c77f502b8c, F5). The restore above writes the
         host's state; the control this close means to return focus to is in
         the pane that state produces, and asking for it in the same tick
         found nothing and left focus on the document body. The CHOICE is made
         then too, for the same reason: `hasControl` and `isConnected` are
         questions about the document as it will be. */
      if (step.do === 'focus') {
        after(() => {
          const choice = closing.launch ? focusChoice(closing.launch, closing.invoker, page.hasControl) : step.choice
          page.focus(choice, closing.invoker)
        })
        continue
      }
      /* AN ORDINARY PICTURE, BACK TO ITS OWN POST (N3): the baseline's own
         close, kept for a viewer this contract never registered. */
      if (step.do === 'reveal') { page.reveal?.(step.post); continue }
      const rest = i + 1
      if (runRestore(step.place, () => runClose(steps, rest, closing, may), may) === 'waiting') return
    }
  }

  const closeResult: MountedResults['closeResult'] = (viewer) => {
    /* THIS PRESS, TOLD APART FROM EVERY OTHER CLOSE OF THE SAME VIEWER
       (B1-R2): the gate a close sets is given up by this operation's own
       continuation and by nobody else's. */
    const op = ++closes
    const launch = results.launchOf(viewer)
    const at = page.centreAt()
    const owns = !!at?.result && at.result.opening === results.openingOf(viewer)
    /* READ ONCE, HERE, AND CARRIED (N2): the plan's focus choice and the
       element it is about are the same fact, so they cannot disagree by the
       time the close reaches its focus step. */
    const closing: Closing = { invoker: results.invokerOf(viewer), launch }
    const plan = closeSteps(
      { viewer, where: whereOf(viewer), launch, source: viewerOf(viewer)?.source ?? null },
      { owns, conversation: page.conversation(), invoker: closing.invoker, has: page.hasControl },
    )
    /* ONE IDENTITY CHECK FOR THE WHOLE CLOSE, SAYING ITS WORDS ONCE (F7):
       the history walk, the conversation return and the restore that writes
       the old place back are three parts of one close, each asked where it
       happens, and a reader is told once that the Brain under it has moved. */
    const may = closeMay(closing, { yet: false })
    const run = () => {
      /* the walk this close launched has landed (or there was none): whatever
         happens next is no longer its landing (F7-R2) -- AND IT IS THIS
         CLOSE'S MARKER THAT GOES, NEVER ANOTHER CLOSE'S (B1), WHICH IS THIS
         OPERATION'S AND NOT MERELY THIS VIEWER'S (B1-R2). This arm is
         reached on the press itself by every close that makes no history move:
         an ordinary picture in a column, a result that does not own the entry
         it is on, a frame-only close, AND THE SAME RESULT'S OWN COLUMN CLOSE
         after its maximised Close and Go has been answered. Clearing the
         module marker there threw away the gate of a close whose walk the
         browser had not answered yet -- another viewer's, or an earlier press
         of this one's -- and that walk then landed as nobody's. */
      if (walking?.op === op) walking = null
      runClose(plan.then, 0, closing, may)
    }
    /* THE HISTORY MOVE FIRST, BEHIND ITS OWN GUARD, and the rest inside its
       `then`: a reader who answers with Stay never reaches the close, and
       keeps the viewer, its launch and their place in the history (H7; B4.3).
       NOTHING IS DONE ON STAY -- not a restore step, not a forget, not the
       return bar -- because nothing has been left.
       AND NOTHING IS DONE UNDER ANOTHER BRAIN EITHER (F7): the check is asked
       inside that guard, at the moment the history would be walked, and a
       refusal keeps the viewer, its launch and the reader's place exactly as
       Stay does -- with the reason said once.
       AND THE WALK IT ALLOWS IS NOT THE WHOLE CLOSE (F7-R2): the browser
       answers `history.go` on its own time, so an allowed walk is remembered
       as THIS close's, and its landing -- which reaches `applyCentre` before
       `run` -- is asked again there. */
    if (plan.history) {
      page.backTo(plan.history.to, run, () => {}, () => {
        if (!may()) return null                 // refused, and the reader told: nothing moves
        /* AND ONE CLOSE'S WALK AT A TIME (B1). `centreHistory` refuses a second
           centre move while a walk of its own is outstanding (`moving`), so a
           claim made here would not buy this close a landing -- it would only
           take the pending close's gate away and leave this close waiting for a
           pop the helper never asked for. Nothing moves, nothing is given up
           and nothing is said: the helper's own answer to this press was
           already to do nothing, and this is that answer told truthfully.

           THE SAME VIEWER PRESSED AGAIN MAY STILL CLAIM, and that is not the
           ownership B1-R2 is about: this press asks the same question of the
           same launch as the one it replaces, so the landing stays gated by an
           identical gate and each press keeps its own words. What no close may
           do is leave the landing UNGATED, which is the continuation's arm
           above -- and that one is now this operation's alone. */
        if (walking && walking.viewer !== viewer) return null
        walking = { op, viewer, may }
        return { ref: plan.history!.to.conversation ?? '', moved: () => {} }
      })
    } else run()
    if (plan.bar && launch) page.offerReturn?.(launch)
  }

  /* -- taking the explicit way back (F2, F3) ------------------------------- */

  /** THE RETURN BAR'S OWN PRESS, GATED BY THE LAUNCH IT CARRIES.
   *
   *  THE DEFECT THIS ANSWERS (independent rendered review adm-d4c77f502b8c,
   *  F2). The bar was applied by the host directly -- the launch's
   *  `restoreSteps` through `centre.replace`, `putBack` and the ordinary
   *  `pickConversation` wrapper -- and nothing on that path ever asked which
   *  Brain the server serves. Every other way out of a result asks: the
   *  opener on the press, `closeResult` for each of its moves, `applyCentre`
   *  for a landing. So a page whose server had begun serving another Brain
   *  (the real 409 `BrainChanged`, which the page itself was already warning
   *  about) still took the old Brain's conversation, centre, thread, reading
   *  position and reply target back when this control was pressed, and
   *  consumed the offer on the way. The control remaining visible is not
   *  authority, and this operation does not infer it from that.
   *
   *  ASKED AT APPLICATION TIME, AND AGAIN AFTER A HELD GUARD. The identity is
   *  the launch's own `brainKey`, read against the module's serving store at
   *  the moment the page would be written to -- never captured when the bar
   *  was drawn -- and `runRestore`'s conversation press asks the same question
   *  inside its guard, so a reader who leaves the unsaved-work question open
   *  while the server moves is refused then rather than on the strength of the
   *  earlier answer.
   *
   *  A REFUSAL KEEPS THE OFFER. `settled('refused')` and nothing else: the
   *  reader stays where they are, with the reason said once and the way back
   *  still on the page, because the alternative is consuming the one control
   *  that claims to be the way back without taking anybody anywhere. */
  const takeReturn: MountedResults['takeReturn'] = (launch, settled) => {
    const closing: Closing = { invoker: null, launch }
    const may = closeMay(closing, { yet: false })
    if (!may()) { settled?.('refused'); return }
    const steps = restoreSteps(launch, { conversation: page.conversation() })
    /* FOCUS LAST, AND ONLY ONCE THE RESTORED PANE IS DRAWN (F5): this
       operation's own target is the launch's -- the control it was opened
       from, where that is still in the document, else the launch's own stable
       fallback -- and never a module-global "what opened the last thing". */
    const done = () => {
      after(() => page.focus(focusChoice(launch, null, page.hasControl), null))
      settled?.('returned')
    }
    if (runRestore(steps, done, may) === 'done') done()
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
    /* THE CENTRE HAS MOVED, AND THAT IS COUNTED FIRST (B4.4-R1). Every entry
       the centre arrives at -- a result, a Place, a push, a pop, a replace --
       is one generation on, so a resume begun against an earlier one can tell
       that the reader is no longer where it was asked for. It is counted
       before anything is decided and before any early return, for the same
       reason the tracker below is. */
    generation += 1
    /* THE HOST'S OWN TRACKER FIRST, WHATEVER THIS ENTRY IS (B4.2). The page
       is told where the centre has moved to before anything is decided, so
       the early return below cannot leave `centreAt.current` behind: that
       tracker is what `closeResult` reads to know whether this result owns
       the entry it is on, and a stale one makes every maximised result look
       frame-only. It is this module that calls it, so no wiring can skip it. */
    page.enterCentre(to)
    /* THE LANDING OF A WALK A CLOSE LAUNCHED IS THAT CLOSE'S (F7-R2), and it
       is this landing or none: taken here, whatever the entry turns out to be,
       so a walk the browser answers late cannot be read as a later move's. */
    const closing = walking
    walking = null
    if (!to?.result) {
      /* THE CENTRE SHOWS SOMETHING ELSE NOW (F16): a maximised result is
         drawn over the centre, so it goes back to its column or is given up.
         The 3D Brain is the page's own arm and is never touched here. */
      const max = maximised()
      let mine = max && max.content.kind !== 'brain-space' ? { viewer: max.id, from: max.from } : null
      /* UNLESS THIS IS A CLOSE THAT MAY NO LONGER FINISH (F7-R2). The walk was
         allowed and cannot be recalled, but everything it was walking TOWARDS
         can still be refused -- and giving up this viewer is the close's own
         first effect, not the history's. The Brain moved while the browser was
         answering, so the viewer and its launch are kept exactly as Stay keeps
         them, the reader is told once, and the continuation that follows this
         asks the same question and puts nothing back.

         AND WHOSE LANDING THIS IS, IS THE MARKER'S ANSWER -- NOT THE CENTRE'S
         (independent re-review adm-b2c50b80e382, F7-R2c).

         THE DEFECT THIS ANSWERS: the question was asked only where the close's
         viewer was ALSO the viewer maximised right now. `mine` is read from the
         centre, and the reader can take the closing viewer off the centre while
         the browser is answering: the viewer's own Move to column action is in
         the maximised frame, offered after Go dismisses the leave question, and
         `placeIn` moves it. `maximised()` was then null, so `mine` was null, so
         the close was never asked at all and this arm answered `false` -- and
         the host's other arms wrote the page back into the OLD Brain's record,
         source column or Sources browser out of the very saved centre that
         close was walking towards. A column is a deliberate place, so the
         bypass was reachable by an ordinary, careful reader.

         The marker is what says this landing is that close's: it was set by
         this close's own allowed walk and is taken once, above. So the
         PERMISSION is asked of the close -- its launch, through `may` -- as
         soon as there is one, whatever is or is not on the centre now. What
         `mine` still decides is only which viewer is drawn over the centre:
         the close keeps its own viewer (nothing is given up by a close that
         may not finish), and a viewer that is NOT this close's is F16's to
         leave exactly as it always was. The viewer that moved to a column is
         neither -- it is not maximised, so F16 owes it nothing and its
         deliberate place stands. */
      const refused = !!closing && !closing.may()
      if (refused && mine && closing!.viewer === mine.viewer) mine = null
      for (const step of leaveSteps(mine)) {
        if (step.do === 'to-column') { moveViewer(step.viewer, step.column); results.moved(step.viewer, step.column) }
        /* AND A LANDING THE PAGE DOES NOT APPLY GIVES UP NOBODY'S RESULT
           (independent re-review adm-e8508cf186c0, B2).

           THE DEFECT THIS ANSWERS: F7-R2c stopped a refused close giving up its
           OWN viewer and left a DIFFERENT maximised viewer to F16 "exactly as
           it always was". But F16's two answers are not alike. A viewer
           maximised FROM a column goes back to that column and keeps
           everything -- its renderer state, its launch, its way back -- which
           is a preservation. A viewer with no column is FORGOTTEN, with its
           launch, and for a result the reader has just pressed and had opened
           maximised that is the whole of what they opened: the inspection, the
           launch's conversation, thread, position, reply target and draft key,
           and the pending decision it was opened to answer. It went silently --
           the one notice is about the OTHER close's Brain -- in a landing whose
           entire meaning is that NOTHING of the landed centre is applied. The
           centre the reader is on does not change, so there is nothing new for
           that viewer to be covering, and no reason to take it off at all.

           So a refused landing leaves it maximised rather than forgetting it.
           Preservation is the point: a result that has a column still goes back
           to it, because that keeps everything too and is where its own frame
           put it; a result that has none keeps the centre it was opened on.
           What this gives up is the F16 tidiness of never leaving a result over
           a centre that has moved underneath -- and the centre has NOT moved
           here as far as the page is concerned, which is what the refusal
           means. */
        else if (refused) continue
        /* AND NEITHER DOES A LANDING THE PAGE DOES APPLY, WHERE THE RESULT IS
           NOT THE ONE BEING CLOSED (independent re-review adm-012c2c2a3987,
           B2-R2).

           THE DEFECT THIS ANSWERS: B2 above answered the REFUSED landing, and
           the refusal is not what the loss depended on. The reader presses
           Close and Go on a maximised result, the browser takes its own time
           over `history.go`, and in that interval they move the closing result
           into a column -- which makes the work row live again -- and open
           another result, which the opener accepts, places maximised and
           REPORTS AS OPENED (`{what: 'opened', where: 'max'}`). The identity
           has not moved, so the first close's landing is applied; F16 then saw
           a maximised viewer with no column over an ordinary centre and
           forgot it with its launch. What went was the whole of the inspection
           the reader had just been given: the viewer and its renderer state,
           and the launch that is its way back -- the conversation, thread,
           position, reply target, reading position and draft key they were on
           when they pressed it, and the decision it was opened to answer. The
           notices said nothing of it, because this close's own words are about
           its own Brain, and nothing offered that result a return.

           F16 IS STILL F16 FOR THE READER'S OWN NAVIGATION: a Back or Forward
           that is nobody's close (`closing` is null) leaves a maximised result
           exactly as it always did, because the reader asked to be somewhere
           the result is drawn over. What is different here is that the centre
           move is the TAIL of an operation the reader began BEFORE they opened
           this result, and the opener has already told them it is open: a
           later navigation cannot be allowed to take what an earlier one's
           answer arriving late gives up. The close's own viewer is unaffected
           (it is forgotten by this arm or by its own continuation, as before),
           and a result WITH a column still goes back to it above.

           So the accepted result keeps its viewer, its renderer state and its
           complete launch, and its way back is the one every maximised result
           has: its own Close, which is frame-only once the centre has moved on
           and therefore offers the explicit return bar out of the launch kept
           here. No second bar is offered now, because the reader has not left
           that result -- it is still the thing in front of them. */
        else if (closing && closing.viewer !== step.viewer) continue
        else { closeViewer(step.viewer); results.forget(step.viewer) }
      }
      /* AND A REFUSED LANDING IS NOT AN ENTRY FOR THE PAGE TO APPLY EITHER
         (independent re-review adm-8f0c09e4f218, F7-R2b).

         THE DEFECT THIS ANSWERS: keeping the viewer was only the close's own
         first effect. `false` is this module saying "not mine -- your other
         arms have it", and the documented host's other arms are the landed
         entry itself: `setBrainMain(to.brain)`, `setSourceMain(to.source)`,
         `setSourcesOpen(!!to?.sources)` and the rest of `applyCentre`. So the
         refusal kept the viewer and then let the page be written back to the
         OLD Brain's record, source column or Sources browser anyway -- out of
         the saved centre this very close was walking towards, under an identity
         nobody is being served. Protecting `runRestore` does not reach this
         arm: it runs before the continuation.

         So a refusal is HANDLED here, and says so. Nothing of the landed entry
         is applied, and the reader keeps the place they are actually on, as
         Stay keeps it. What is NOT undone is the browser's own history walk:
         it was allowed while the identity was good, `enterCentre` above has
         already recorded where it landed and the generation is already counted,
         so the tracker stays true to the move that really happened (B4.2). */
      return refused
    }
    /* WHICH BRAIN IS BEING SERVED AS THIS ENTRY IS LANDED ON (F2). The saved
       entry holds `<corpus>@<instance>`, so a copy of the same corpus restored
       in place, or served by another process at the same origin, is
       `other-instance` here and is not replayed -- which the graph key the
       hand-off used to supply could not tell apart at all. */
    const now = serving()
    const resume = resumeResult({ result: to.result }, { brainKey: now, live: (o) => !!launchOf(o), words: BRAIN_MOVED })
    /* WHAT A RESUME STARTED HERE IS BOUND TO (B4.4-R1): this entry, this
       generation of the centre, this Brain. The host carries it, so the open
       that finishes after the read still knows which entry it was for. */
    const resuming = hostFor({ generation, entry: to.result, brainKey: now })
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

  return { openResult, has, launchNow, openView, closeResult, takeReturn, goToSource, applyCentre, dockStep, pressed, results, host }
}

/** The restore steps a launch owes, for a host that wants them itself. */
export { restoreSteps }
