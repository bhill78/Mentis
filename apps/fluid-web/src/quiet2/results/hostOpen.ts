/* THE HOST'S OWN MOVES, AS DECISIONS -- so that mounting the result opener is
 * CALLING these rather than designing them (independent review
 * adm-f3244dbc4bae, B1 and B4).
 *
 * WHAT WENT WRONG WITHOUT THIS FILE. The hand-off to the shared hosts was
 * prose with snippets, and the snippets did not compose into the behaviour
 * they described: the file adapter threw away the Admission it was given and
 * read `/api/artifacts/` instead of `/api/artifacts/<ref>`; it asked a post
 * for its pictures whether or not there was a post, and `picturesOf(undefined)`
 * reads `post.blocks`; closing deleted the viewer before the restore it
 * depended on; a maximised result with no column of its own had no way to
 * show its source; and landing on a result entry again was a comment. Each of
 * those is a DECISION, and a decision belongs where it can be checked.
 *
 * SO THE HOST SUPPLIES ONLY WHAT IT ALONE HAS -- its viewer store, its
 * history hook, its readers -- and this module says what to do with them, in
 * order. Every function here is pure or a plain store, checkable without a
 * browser (`tests/quiet2_result_host_unit.ts`). Nothing here renders, fetches,
 * touches a permission, a sandbox or a CSP, or reaches a byte: the host's own
 * `heldItem`, `goToPost`, `pickConversation`, `enterBrain` and `centre` are
 * the only ways anything happens.
 *
 * WHO OWNS WHAT. `Quiet2.tsx` and `GlobalDock.tsx` are the integrator's and
 * are not touched by this part; `results/HOST-INTEGRATION.md` is the patch
 * they apply, and it is written against these functions. */
import type { HeldBytes, ViewerItem } from '../../quiet/media/view'
import { postSource, type Viewable, type ViewerSource, type ViewImage } from '../viewer/types'
import { viewableOfItem } from '../viewer/viewableOfItem'
import type { CentreAt } from '../address'
import type { FileOpen, Opened } from './opener'
import { closePlan, historyStep, keepsReturnBar, type ResultResume, type Shown } from './history'
import {
  focusChoice, launchOf, placedLaunch, releaseLaunch,
  type Focusable, type FocusChoice, type LaunchContext, type LaunchPlace,
} from './launch'
import type { ResultTarget } from './targets'

/** The page's two working columns, as the viewer store names them. */
export type Column = 's1' | 's2'

/* -- opening held bytes (B1) ------------------------------------------------- */

/** WHAT THE PAGE MUST ANSWER TO OPEN HELD BYTES, and nothing more.
 *
 *  `post` and `pictures` are separate on purpose. A result's source is a post
 *  only sometimes: an artifact a run returned with no Turn to place it in, a
 *  file read from a Brain record, and a post this page has not drawn all have
 *  no Post object at all. `postOf` answers `undefined` for every one of them,
 *  and `picturesOf` reads `post.blocks` straight away -- so the post is asked
 *  for FIRST, and its pictures only where there is one. */
export interface FileReading<P> {
  /** the existing `heldItem(ref, about)`: the bytes as the viewer reads them */
  item: (ref: string, about: HeldBytes | null) => ViewerItem | null
  /** the post this page holds, or null/undefined where it holds none */
  post?: (post: string) => P | null | undefined
  /** that post's own pictures (`picturesOf`), asked only for a post there is */
  pictures?: (post: P) => readonly ViewImage[]
}

export type FileContent =
  | { content: Viewable; source: ViewerSource | null }
  | { why: string }

const NO_REF = 'That file has no reference to read: nothing was opened.'
const NOT_HELD = 'Those contents could not be opened: Mentis does not hold them.'
const NOT_THE_SAME = 'Those bytes are not the ones that were asked for.'

/** WHAT THE HOST'S VIEWER IS GIVEN FOR A FILE OPEN, from the exact reference
 *  the destination carries.
 *
 *  THE REF IS THE IDENTITY (B1). The descriptor is only what is known ABOUT
 *  those bytes -- `heldItem` builds both the artifact address and the item's
 *  own `ref` from the first argument, so passing `''` reads another file's
 *  address, or none at all. The caller's own item is used where it has one;
 *  otherwise the descriptor is read UNDER THE GIVEN REF. */
export function fileContent<P>(o: FileOpen, page: FileReading<P>): FileContent {
  const ref = o.ref || o.item?.ref || o.file?.ref || ''
  if (!ref) return { why: NO_REF }
  const item = o.item ?? page.item(ref, o.file ?? null)
  if (!item) return { why: NOT_HELD }
  /* a caller's item for a different Admission is not this press's answer */
  if (item.ref && item.ref !== ref) return { why: NOT_THE_SAME }
  return { content: viewableOfItem(item, siblingsOf(o.source, page)), source: o.source }
}

/** THE PICTURES BESIDE IT, WHERE THERE ARE ANY (B1). A picture with no
 *  collection opens as a collection of one, which is what the dock and the
 *  Brain record already do; a Brain-sourced artifact is never given a post it
 *  does not have. */
export function siblingsOf<P>(source: ViewerSource | null, page: FileReading<P>): readonly ViewImage[] | undefined {
  const from = source ? postSource(source) : null
  if (!from?.post || !page.post || !page.pictures) return undefined
  const post = page.post(from.post)
  return post ? page.pictures(post) : undefined
}

/* -- every placed viewer's own launch (B2) ---------------------------------- */

/** A RESULT VIEWER THE PAGE ACTUALLY PLACED. */
export interface PlacedViewer {
  viewer: string
  opening: number
  target: ResultTarget | null
  where: Shown
  /** the element that opened it, for focus on the way back */
  invoker: Focusable | null
}

/** THE LAUNCHES OF THE VIEWERS THAT ARE OPEN, which is a different question
 *  from which read is newest (B2).
 *
 *  Every successful placement registers here -- maximised, a free column, the
 *  column the reader chose -- and nothing else evicts it: the first of two
 *  side viewers still returns to the row it was opened from, and the launch a
 *  history entry names is still live while its viewer is on screen. Closing
 *  the viewer is what releases it.
 *
 *  A plain store, like `viewer/viewers.ts` beside it: no React, no effects. */
export interface ResultViewers {
  /** a placement that SUCCEEDED: its launch is kept until it closes */
  place: (viewer: string, launch: LaunchContext, target: ResultTarget | null, where: Shown, invoker?: Focusable | null) => Shown
  /** the same viewer, somewhere else (maximised, restored to its column) */
  moved: (viewer: string, where: Shown) => void
  launchOf: (viewer: string) => LaunchContext | null
  targetOf: (viewer: string) => ResultTarget | null
  whereOf: (viewer: string) => Shown | null
  invokerOf: (viewer: string) => Focusable | null
  openingOf: (viewer: string) => number | null
  /** the viewer an opening made, for landing on its history entry again */
  viewerOf: (opening: number) => string | null
  /** whether this opening's launch is still live here */
  live: (opening: number) => boolean
  /** it is gone: its launch is released and returned for the close plan */
  forget: (viewer: string) => LaunchContext | null
  all: () => PlacedViewer[]
}

/** `read` is where a live launch is looked up -- `launch.ts`'s own registry by
 *  default. A viewer row holds the OPENING, never a second copy of the
 *  launch: one place decides whether a launch is still live. */
export function resultViewers(read: (opening: number) => LaunchContext | null = launchOf): ResultViewers {
  const rows = new Map<string, PlacedViewer>()
  const row = (viewer: string) => rows.get(viewer) ?? null
  const launchOfOpening = read
  return {
    place(viewer, launch, target, where, invoker = null) {
      rows.set(viewer, { viewer, opening: launch.opening, target, where, invoker })
      placedLaunch(launch.opening)
      return where
    },
    moved(viewer, where) { const r = row(viewer); if (r) rows.set(viewer, { ...r, where }) },
    launchOf: (viewer) => { const r = row(viewer); return r ? launchOfOpening(r.opening) : null },
    targetOf: (viewer) => row(viewer)?.target ?? null,
    whereOf: (viewer) => row(viewer)?.where ?? null,
    invokerOf: (viewer) => row(viewer)?.invoker ?? null,
    openingOf: (viewer) => row(viewer)?.opening ?? null,
    viewerOf: (opening) => [...rows.values()].find((r) => r.opening === opening)?.viewer ?? null,
    live: (opening) => !!launchOfOpening(opening),
    forget(viewer) {
      const r = row(viewer)
      if (!r) return null
      const l = launchOfOpening(r.opening)
      rows.delete(viewer)
      releaseLaunch(r.opening)
      return l
    },
    all: () => [...rows.values()],
  }
}

/* -- closing a result, in order (B4) ---------------------------------------- */

/** ONE STEP OF A CLOSE, in the order it is to be taken. */
export type CloseStep =
  /** put back the thread, reading offset, reply target and draft key */
  | { do: 'restore'; launch: LaunchContext; place: PlaceStep[] }
  /** where focus goes (`focusChoice`) */
  | { do: 'focus'; choice: FocusChoice }
  /** the viewer is given up: LAST, and only once the restore has run */
  | { do: 'forget'; viewer: string }
  /** NOT A RESULT AT ALL: an ordinary maximised picture or block, closed back
   *  to the post it was drawn in, exactly as the baseline's own viewer-frame
   *  close did (`revealPost(post.post)` after the frame goes). It is here
   *  because the hand-off routed EVERY viewer-frame close through this
   *  sequence, and a viewer nothing registered has no launch and so lost that
   *  convenience (re-review adm-d84456fd4c3c, N3). */
  | { do: 'reveal'; post: string }

/** WHAT A CLOSE DOES, AS A SEQUENCE THAT CAN BE ABANDONED HALFWAY (B4, H7).
 *
 *  THE ORDER IS THE POINT. The old snippet closed the viewer and deleted its
 *  launch and then navigated, so a reader who answered the unsaved-work guard
 *  with Stay lost the viewer anyway -- the contract requires a cancelled
 *  return to keep the viewer AND its draft. Here the history move comes first
 *  and the rest goes in its `then`, which is reached only once the move has
 *  actually been applied.
 *
 *  AND THE MOVE ITSELF IS ASKED ABOUT BY WHOEVER MAKES IT (re-review
 *  adm-d84456fd4c3c, B4.3). `centreHistory`'s `back` does not ask: the pop it
 *  makes is marked as already asked, deliberately, because a move the page
 *  asked for was guarded by the control that asked for it. So `history` here
 *  is a move for the host's GUARDED `backTo` (`ResultPage.backTo(place, then,
 *  stay)`), and `then` is this sequence. A close that went straight to
 *  `centre.backTo` left no question for Stay to answer.
 *
 *  `history` is `null` where this close owes the history nothing: a side
 *  column (`historyStep` is `none`) or an entry navigation has already left
 *  (`frame-only`). Then `then` runs at once.
 *
 *  `bar` is whether the explicit return bar is still owed afterwards. */
export interface ClosePlanSteps {
  history: { how: 'back'; to: LaunchPlace } | { how: 'replace'; to: LaunchPlace } | null
  then: CloseStep[]
  bar: boolean
}

export function closeSteps(
  v: { viewer: string; where: Shown; launch: LaunchContext | null; source?: ViewerSource | null },
  now: { owns: boolean; conversation: string | null; invoker?: Focusable | null; has?: (control: string) => boolean },
): ClosePlanSteps {
  const has = now.has ?? (() => false)
  const forget: CloseStep = { do: 'forget', viewer: v.viewer }
  if (!v.launch) {
    /* AN ORDINARY VIEWER, NOT A RESULT (N3). Nothing registered it, so there
       is no launch, no entry and no way back to put back -- but the baseline
       took a maximised, post-sourced picture back to its own post as it
       closed, and that is kept rather than dropped by routing every close
       through here. A column viewer never did it, and still does not. */
    const from = v.where === 'max' && v.source ? postSource(v.source) : null
    return { history: null, then: from?.post ? [forget, { do: 'reveal', post: from.post }] : [forget], bar: false }
  }
  const focus: CloseStep = { do: 'focus', choice: focusChoice(v.launch, now.invoker ?? null, has) }
  const restoring = (appliedPlace: boolean): CloseStep =>
    ({ do: 'restore', launch: v.launch!, place: restoreSteps(v.launch!, { conversation: now.conversation, appliedCentre: true, appliedPlace }) })
  /* A SIDE COLUMN NEVER WALKED THE CENTRE'S HISTORY, and never pops it: there
     is no history move to have arrived anywhere, so the conversation it was
     opened in is still its own guarded press (F15). */
  if (historyStep(v.where, 'none') !== 'consume') return { history: null, then: [restoring(false), focus, forget], bar: false }
  const plan = closePlan(now.owns, true)
  /* FRAME-ONLY CLOSES THE FRAME, AND NOTHING ELSE (re-review adm-263df1ccb512,
     F14). Navigation has since left this entry: the reader is somewhere they
     chose, and `history.ts` says this close leaves the Place alone. Restoring
     the launch's Place here would navigate them away from it while the return
     bar is at the same time claiming to be what takes them back -- two moves
     for one way back, one of them unasked. So only focus and the frame. */
  if (plan === 'frame-only') return { history: null, then: [focus, forget], bar: keepsReturnBar(plan) }
  /* ONE CALL, NOT TWO. `centre.back(to, then)` is already both of
     `closePlan`'s moves: it steps back where the Place is the entry directly
     behind (`isBehind`), and otherwise this entry BECOMES the Place. So the
     host needs no `isBehindPlace` of its own -- which it has no way to answer
     -- and nothing here asks for one. */
  return { history: { how: 'back', to: v.launch.place }, then: [restoring(true), focus, forget], bar: false }
}

/* -- putting the reader back where they were (B4) --------------------------- */

/** ONE THING THE HOST PUTS BACK. Identity and position only: a draft is
 *  restored by its KEY, through the existing draft store, and never carried. */
export type PlaceStep =
  /** another conversation than the one shown: its own press, first */
  | { do: 'conversation'; conversation: string }
  /** what was over it (`CentreAt`), where the history move has not applied it */
  | { do: 'centre'; at: CentreAt | null }
  /** THE THREAD THE LAUNCH WAS IN -- OR THE ABSENCE OF ONE (independent
   *  rendered review adm-d4c77f502b8c, F3). `root: null` is "the conversation
   *  flow, in no thread", and it is a step like any other: a launch made in
   *  the flow was previously restored by SAYING NOTHING about the thread, so a
   *  reader who entered a thread after opening the result was left in that
   *  thread -- with its composer, its draft place and its "Back to
   *  conversation" bar -- by the very control that promised to put them back
   *  where they opened it. */
  | { do: 'thread'; root: string | null; at: string | null }
  | { do: 'reading'; scroll: number; offset: number | null }
  | { do: 'reply'; post: string | null }
  | { do: 'draft'; key: string }

/** WHAT RESTORING A LAUNCH'S PLACE ACTUALLY TAKES, in order (B4, H4).
 *
 *  THE CONVERSATION FIRST, WHERE IT DIFFERS. `usePlaces`'s `go`, `replace` and
 *  `back` all move within the conversation shown (`c.current`), so a launch
 *  made in another conversation needs that conversation opened as well -- the
 *  host patch adds one `backTo` to `places.ts` for exactly this, and it is
 *  three lines of the hook's own existing calls. Without that step a return
 *  from a result opened in another conversation silently lands in the wrong
 *  one, which is what "the wrapper retains the current conversation" meant.
 *
 *  `appliedCentre` is for the close path, where the history move has already
 *  put the Place back: then the centre is not applied twice. `appliedPlace`
 *  says the same of the CONVERSATION -- `places.ts` `backTo` moves to a whole
 *  Place, the conversation included, so a close that walked the history has
 *  already arrived there and must not press it again. Pressing it again would
 *  put the unsaved-work question a second time for one close, now that the
 *  history move is itself guarded (re-review adm-d84456fd4c3c, B4.3). */
export function restoreSteps(l: LaunchContext, now: { conversation: string | null; appliedCentre?: boolean; appliedPlace?: boolean }): PlaceStep[] {
  const steps: PlaceStep[] = []
  if (!now.appliedPlace && l.place.conversation && l.place.conversation !== now.conversation) steps.push({ do: 'conversation', conversation: l.place.conversation })
  if (!now.appliedCentre) steps.push({ do: 'centre', at: l.place.centre })
  /* BOTH DIRECTIONS, ALWAYS SAID (F3): into the thread it was opened from,
     and out of a thread entered since into the flow it was opened from. The
     composer's place follows the thread (`mainPlace`), so this is also what
     points the composer back at the launch's own draft -- and neither draft is
     touched: the draft store keeps one per place, and this selects a place. */
  steps.push({ do: 'thread', root: l.thread?.root ?? null, at: l.thread?.at ?? null })
  if (l.reading) steps.push({ do: 'reading', scroll: l.reading.scroll, offset: l.reading.offset })
  steps.push({ do: 'reply', post: l.reply })
  /* THE KEY, NEVER THE TEXT: the draft is already kept by the draft store
     under this key, and restoring is pointing the composer at it again. */
  if (l.draft) steps.push({ do: 'draft', key: l.draft })
  return steps
}

/* -- go to source, including from a maximised result with no column (B4) ---- */

/** ONE STEP OF SHOWING WHERE THE BYTES CAME FROM. */
export type SourceStep =
  /** back to the column this viewer came from, so the post is visible */
  | { do: 'to-column'; column: Column }
  /** no column to go to: the viewer is PARKED -- kept, with its renderer's
   *  state and its id, shown nowhere (`viewers.ts` `parkViewer`), so the
   *  conversation underneath is actually readable and the reader can ask for
   *  it back (`parkedPlaceOf`, `returnViewer`) */
  | { do: 'park' }
  | { do: 'go-to-post'; conversation: string; post: string }

/** GO TO SOURCE IS NOT CLOSE, AND IT IS NOT A DEAD END (B4, H3).
 *
 *  A maximised result used to say "close the viewer to return to the post it
 *  came from" when it had no column of its own -- and the proposed snippet
 *  called `goToPost` while leaving the maximised overlay drawn over it, which
 *  is the same dead end with the words removed. With no column the viewer
 *  parks instead: nothing is closed, nothing is lost, and the post is on
 *  screen. */
export function sourceSteps(
  v: { where: Shown; from?: Column | null },
  source: { conversation: string; post: string },
  room: { columns: readonly Column[] },
): SourceStep[] {
  const go: SourceStep = { do: 'go-to-post', conversation: source.conversation, post: source.post }
  if (v.where !== 'max') return [go]
  if (v.from && room.columns.includes(v.from)) return [{ do: 'to-column', column: v.from }, go]
  return [{ do: 'park' }, go]
}

/* -- landing on a result entry again (B4) ----------------------------------- */

/** ONE STEP OF ARRIVING ON A RESULT ENTRY (Back, or Forward). */
export type ResumeStep =
  /** its viewer is still open: it is SHOWN again, not rebuilt */
  | { do: 'show-viewer'; viewer: string; where: Shown }
  /** no viewer for it any more (a reload, or it was closed): resolve the
   *  target again, and offer this Place as the way back */
  | { do: 'resolve'; target: ResultTarget; back: LaunchPlace }
  /** another Brain, or another instance of it: nothing is replayed */
  | { do: 'say'; words: string }
  /** the Place the entry was over becomes what is shown */
  | { do: 'leave-on'; place: LaunchPlace }

/** WHAT THE CENTRE'S `apply` DOES WITH A RESULT ENTRY (B4, H2, H8).
 *
 *  The `resolve` arm was a comment and the `live` arm did nothing, so Back and
 *  Forward were not connected to the viewer store at all: an entry whose
 *  viewer was parked or demaximised stayed hidden, and one whose viewer had
 *  gone did nothing whatever. Each arm is a step here, and the viewer it names
 *  is the one the opening actually placed. */
export function resumeSteps(r: ResultResume, viewers: Pick<ResultViewers, 'viewerOf' | 'whereOf'>): ResumeStep[] {
  if (r.how === 'other-brain') return [{ do: 'say', words: r.words }, { do: 'leave-on', place: r.place }]
  if (r.how === 'live') {
    const viewer = viewers.viewerOf(r.intent.opening)
    if (viewer) return [{ do: 'show-viewer', viewer, where: viewers.whereOf(viewer) ?? 'max' }]
    /* its launch is live and its viewer is not: the target is resolved again,
       which is the honest answer rather than a blank centre */
    return [{ do: 'resolve', target: r.intent.target, back: r.intent.place }]
  }
  return [{ do: 'resolve', target: r.intent.target, back: r.intent.place }]
}

/* -- leaving a result entry (B4) -------------------------------------------- */

/** ONE STEP OF THE CENTRE CEASING TO SHOW A RESULT. */
export type LeaveStep =
  /** it came from a column: it goes back there, still open */
  | { do: 'to-column'; viewer: string; column: Column }
  /** it had no column: the overlay is given up */
  | { do: 'forget'; viewer: string }

/** WHAT A MAXIMISED RESULT OWES WHEN THE CENTRE GOES SOMEWHERE ELSE (re-review
 *  adm-263df1ccb512, F16).
 *
 *  Back out of a result entry, or Forward onto an ordinary one, lands on a
 *  Place that is not a result -- and a maximised viewer is drawn OVER the
 *  centre. The `apply` arm that handled only `to.result` left the old file
 *  maximised over whatever the reader had just navigated to: the history moved
 *  and the screen did not. The viewer goes back to the column it was maximised
 *  from, where it has one, and is otherwise given up with its launch.
 *
 *  A parked or columned viewer is not maximised and owes nothing here, and the
 *  3D Brain is the page's own (`spaceRef.apply`), never this. */
export function leaveSteps(max: { viewer: string; from?: Column | null } | null): LeaveStep[] {
  if (!max) return []
  return max.from ? [{ do: 'to-column', viewer: max.viewer, column: max.from }] : [{ do: 'forget', viewer: max.viewer }]
}

/* -- what the dock does with the answer ------------------------------------- */

/** WHETHER THE DOCK ARMS ITS WAY BACK NOW, LATER, OR NOT AT ALL (B3).
 *
 *    arm     the reader has actually left: the return pill is owed
 *    wait    it is still happening: arm nothing, keep the row and the draft,
 *            and answer this same question again when `settled` says
 *    keep     nothing was opened: the row, the form and the draft stay
 *
 *  This is the one rule the dock needs, so that "did the reader leave?" is not
 *  answered a second way in `GlobalDock.tsx`. */
export type DockStep = 'arm' | 'wait' | 'keep'

export function dockStep(o: Opened): DockStep {
  if (o.what === 'opened') return 'arm'
  if (o.what === 'leaving' || o.what === 'placing') return 'wait'
  return 'keep'
}

/** Whether pressing it was worth it at all, for the dock's own return value:
 *  an unopenable reference and a refusal say so, and everything else is a
 *  press that did something or is still doing it. */
export const pressed = (o: Opened) => o.what !== 'unavailable' && o.what !== 'refused'
