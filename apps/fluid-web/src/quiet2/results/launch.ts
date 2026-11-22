/* WHERE THE READER WAS WHEN THEY OPENED A RESULT, AND WHAT RETURNS THEM
 * THERE -- apart from where the result came from, which is a different fact
 * entirely (navigation review adm-d9152e0643d7, B3).
 *
 * SOURCE IS NOT LAUNCH, and conflating them is the defect this answers.
 * Closing a result jumped to the post the bytes came FROM (`revealPost(
 * v.source.post)`), which is not where the reader was: somebody who opened a
 * review PNG from Needs you, or from the Latest list, was put in the middle of
 * whatever conversation produced it, with their decision gone and their draft
 * apparently lost. A result carries BOTH facts from now on: `ViewerSource`
 * says where the content is from (the viewer's own header uses it, and "Go to
 * source" takes it), and a `LaunchContext` says where the reader was (closing
 * and the explicit return use that).
 *
 * WHAT A LAUNCH HOLDS, AND WHAT IT MUST NEVER HOLD. Identity and position
 * only: which Brain instance, the Place that was shown, the thread and reading
 * offset, the reply target, the KEY of the existing draft store, the control
 * that was pressed and a stable fallback for it, and -- for a decision -- an
 * identity token into Needs you's own draft and outbox state. Never the draft
 * text, never an answer, never bytes, and never anything that authorises
 * anything: `historyOf` is the only shape allowed into a history entry, and it
 * is three fields wide.
 *
 * ONE OPENING, ONE TOKEN. Focus, late reads and Brain changes are all decided
 * per opening rather than from one module-global "who opened the last thing"
 * (B3, H6): a read that finishes after the reader has opened something else
 * cannot steal focus or replace the newer opening, and an opening made against
 * another Brain instance is refused rather than replayed.
 *
 * Pure (the opening counter aside, which is a plain module store like
 * `viewer/viewers.ts`), so every rule here is checkable without a browser:
 * `tests/quiet2_result_opener_unit.ts`. */
import type { CentreAt } from '../address'

/* -- which Brain ------------------------------------------------------------ */

/** The page's Brain key (`brainBinding.ts` `brainKeyOf`): `<corpus>@<instance>`.
 *  A copy served elsewhere, or one restored in place, shares the corpus and
 *  not the instance -- which is exactly the case a result opener must refuse,
 *  so the whole key is compared and never the corpus alone. */
export type BrainKey = string

export const corpusOf = (key: BrainKey | null): string | null => (key ? key.split('@')[0] || null : null)

export const sameBrain = (a: BrainKey | null, b: BrainKey | null): boolean => !!a && !!b && a === b

export type BrainVerdict = 'same' | 'other-instance' | 'other-brain' | 'unknown'

/** Whether something recorded against `was` may still be acted on now. */
export function brainVerdict(was: BrainKey | null, now: BrainKey | null): BrainVerdict {
  if (!was || !now) return 'unknown'
  if (was === now) return 'same'
  return corpusOf(was) === corpusOf(now) ? 'other-instance' : 'other-brain'
}

/** WHICH BRAIN THE SERVER SERVES THIS PAGE, AS AN ANSWER THAT CANNOT BE READ
 *  AS AN EXEMPTION (independent review adm-1cb30e65d05f, F3).
 *
 *  THE DEFECT THIS ANSWERS. A `BrainKey | null` carried two different facts in
 *  one value: "this is the Brain" and "there is no answer". Every gate here
 *  then wrote the second one off -- `launch.brainKey && …`, `if (!was) return
 *  true`, `launch?.brainKey && …` -- so a launch MADE while the page had not
 *  bound yet, or after it had moved, carried `null` and passed all of them. A
 *  press made in that state placed an artifact, navigated to a record and
 *  reported `opened`, and `entered` then wrote whatever identity the binding
 *  had acquired BY THE TIME THE READ ANSWERED. That is not fail-closed: it is
 *  the one state in which nothing can be compared being the one state in which
 *  nothing is compared.
 *
 *  So the three states are distinct values, and `null` is not among them. A
 *  key means a Brain has answered and the page is still on it; the other two
 *  mean there is no identity to act under, and they are told apart only so
 *  that the reader is told the truth about which. */
export type Serving =
  /** a Brain answered, and no other has answered since */
  | { how: 'serving'; key: BrainKey }
  /** nothing has answered yet: this page cannot say which Brain it is on */
  | { how: 'unconfirmed' }
  /** another Brain has answered since: only a reload binds this page again */
  | { how: 'moved' }

/** The key, where there is a confirmed one: for the saved entry and the resume,
 *  which hold `<corpus>@<instance>` and have always refused `null` themselves. */
export const servingKey = (s: Serving): BrainKey | null => (s.how === 'serving' ? s.key : null)

/** A CALLER THAT STILL ANSWERS WITH A KEY ALONE, READ FAIL-CLOSED. `null` is
 *  "not confirmed", never "exempt": a host that does not distinguish the two
 *  states gets the refusing one, so no wiring can open the bypass again by
 *  omission (F3). Which state it really is, where that matters to the reader,
 *  is `serving.ts`'s to say -- it is the only thing that reads the binding. */
export const servingOfKey = (key: BrainKey | null): Serving =>
  (key ? { how: 'serving', key } : { how: 'unconfirmed' })

/** WHETHER AN OPENING MADE AGAINST `was` MAY ACT WHILE THE PAGE IS `now`:
 *  `act` only for a CONFIRMED identity on both sides that is the same one.
 *
 *  An opening that named no Brain is not acted on, whatever the page can say
 *  now -- it was made in a state in which this page could not tell which Brain
 *  it was reading, and a Brain that answered afterwards is not the one it was
 *  made against. That is what "later acquire a different identity" was. */
export type Acting = 'act' | 'unconfirmed' | 'moved' | 'other-instance' | 'other-brain'

export function mayAct(was: BrainKey | null, now: Serving): Acting {
  if (now.how === 'moved') return 'moved'
  if (now.how === 'unconfirmed' || !was) return 'unconfirmed'
  if (was === now.key) return 'act'
  return corpusOf(was) === corpusOf(now.key) ? 'other-instance' : 'other-brain'
}

/** What the reader is told where a stored opening is another Brain's. The same
 *  words for another instance of the same corpus: the page was showing one
 *  Brain and the server serves another, whichever it is. */
export const BRAIN_MOVED = 'This page was showing another Brain than the server serves now. Reload the page before opening it.'

/** AND WHERE THERE IS NO ANSWER AT ALL -- a page that has not confirmed which
 *  Brain the server serves, or an opening made before it could. Deliberately
 *  the same thing a write made in that state is already told (`brainBinding.ts`
 *  `UNCONFIRMED`): not sent, not opened, try again in a moment. No new rule of
 *  authority -- the same fail-closed direction, now on the read side too. */
export const BRAIN_UNCONFIRMED = 'This page has not confirmed which Brain the server serves, so nothing was opened. Try again in a moment.'

/** The words for a refusal, in the reader's terms: what is wrong, and what to
 *  do -- wait, or reload. */
export const actingWords = (a: Acting): string => (a === 'unconfirmed' ? BRAIN_UNCONFIRMED : BRAIN_MOVED)

/* -- where the reader was --------------------------------------------------- */

/** THE PLACE A RESULT WAS OPENED FROM -- any Place, not only a conversation
 *  (focused review M2.3). A reader can open a result from a Brain record, from
 *  Manage Sources, from a file read in place or from the 3D Brain; the centre
 *  they were on is kept exactly as the history protocol already writes one
 *  (`address.ts` `CentreAt`), so returning puts back the Place they left and
 *  not a conversation they never chose. */
export interface LaunchPlace {
  /** the conversation shown under the centre, where one was */
  conversation: string | null
  /** what was over it, in the history's own terms; null is the conversation */
  centre: CentreAt | null
}

/** A DECISION THIS OPEN CAME FROM: identity only. It names the form, the exact
 *  question, the Needs you item and the reference that was pressed, so the
 *  dock can be brought back to that row with the pick and the text the reader
 *  had already made. It is a token INTO the existing draft and outbox state
 *  (`experimental/decisionOutbox.ts`, `draftKeep.ts`), never a copy of an
 *  answer and never an answer operation. */
export interface DecisionLaunch {
  /** the response set / form, where the item is a form */
  form: string | null
  /** the exact question (its expectation), as Needs you keys its drafts */
  question: string
  /** the Needs you item's key */
  item: string
  /** the reference that was opened, by its exact id */
  ref: string
  /** what part the record says that reference plays */
  role: string | null
}

/** WHAT FOCUS RETURNS TO when the control that opened the result is gone --
 *  a menu that unmounted, a dock that closed, a row that moved. Stable
 *  identity, in the restored pane, rather than a remembered element. */
export type FocusFallback =
  /** the Latest list's own trigger, for a Latest launch */
  | { kind: 'latest' }
  /** the decision return pill, for a Needs you launch */
  | { kind: 'decision'; item: string }
  /** a named item and its action, where the restored pane draws it again */
  | { kind: 'item'; item: string; action?: string | null }
  /** the conversation's heading: last, and always available */
  | { kind: 'conversation' }

export interface LaunchFocus {
  /** the control that was pressed, by its own stable identity (a data
   *  attribute), where it has one */
  control: string | null
  fallback: FocusFallback
}

/** EVERYTHING NEEDED TO PUT THE READER BACK, and nothing else. */
export interface LaunchContext {
  /** which opening this is (`beginOpening`): a later one is never replaced */
  opening: number
  brainKey: BrainKey | null
  place: LaunchPlace
  /** the thread being read, and the post it was read at */
  thread: { root: string; at: string | null } | null
  /** where the column was: its scroll, and the anchor's offset in it */
  reading: { scroll: number; offset: number | null } | null
  /** the post being replied to */
  reply: string | null
  /** THE KEY of the existing draft store's entry. Never the text. */
  draft: string | null
  focus: LaunchFocus
  decision?: DecisionLaunch | null
}

/** THE ONLY PART OF A LAUNCH THAT MAY BE WRITTEN INTO A HISTORY ENTRY: which
 *  opening, which Brain, which Place. A history entry survives a reload, where
 *  the draft, the focus and the reply target do not -- so they are not
 *  promised there (H8). */
export interface LaunchMark { opening: number; brainKey: BrainKey | null; place: LaunchPlace }

export const historyOf = (l: LaunchContext): LaunchMark =>
  ({ opening: l.opening, brainKey: l.brainKey, place: l.place })

/* -- one opening at a time, and every open viewer's way back ---------------- */

/* TWO LIFETIMES, WHICH THIS REGISTRY WAS TREATING AS ONE (independent review
 * adm-f3244dbc4bae, B2).
 *
 *   A PENDING READ is over the moment the reader presses something else: a
 *   resolve that answers afterwards must not draw over what they are looking
 *   at. That is `acceptsLate`, decided from the opening NUMBER, and it needs
 *   nothing deleted to be true.
 *
 *   WHAT AN OPEN VIEWER OWES ITS READER outlives every later press. Two
 *   results open beside a conversation each return to the row they were
 *   opened from, and a return bar still owed is still owed after the next
 *   open.
 *
 * `holdLaunch` expressed the first by deleting every other launch, which
 * destroyed the second: the first of two side viewers could no longer return
 * to its live launch -- `restoreOf` fell back to the Place, as if the page had
 * been reloaded -- and the launch the history entry names was gone while its
 * viewer was still on screen. The two are separate here now: holding a launch
 * evicts nothing, and a launch is given up only when its viewer or its way
 * back actually releases it. */

let openings = 0
const live = new Map<number, LaunchContext>()
/** openings whose viewer, or whose way back, actually exists on the page */
const placed = new Set<number>()

/** AT MOST THIS MANY LAUNCHES ARE KEPT AT ONCE. Not a policy about returning:
 *  a bound, so that openings nothing ever released -- a read that never
 *  answered, a press whose placement the reader abandoned -- cannot grow for
 *  the life of the page. The oldest opening with nothing placed goes first,
 *  and a placed one is given up only when there is nothing else to drop. */
export const MAX_LIVE_LAUNCHES = 64

/** A new opening: its number is later than every earlier one. */
export function beginOpening(): number { return ++openings }

/** KEEPS THIS OPENING'S LAUNCH. It does not end any other: an open viewer's
 *  way back is not the newest press's business (B2). */
export function holdLaunch(l: LaunchContext): LaunchContext {
  live.set(l.opening, l)
  if (live.size > MAX_LIVE_LAUNCHES) {
    const others = [...live.keys()].filter((id) => id !== l.opening)
    const drop = others.find((id) => !placed.has(id)) ?? others[0]
    if (drop !== undefined) releaseLaunch(drop)
  }
  return l
}

/** THE VIEWER THIS OPENING MADE, OR THE WAY BACK IT OWES, IS REALLY THERE.
 *  Every successfully placed viewer says so -- maximised, a free column, or
 *  the column the reader chose -- so its launch is kept until it closes
 *  (`hostOpen.ts` `resultViewers` does this for the host). An opening that
 *  was never placed is still ordinary: it is simply the first to be dropped
 *  if the bound above is ever reached. */
export function placedLaunch(opening: number): LaunchContext | null {
  const l = live.get(opening)
  if (l) placed.add(opening)
  return l ?? null
}

export const isPlaced = (opening: number): boolean => placed.has(opening)

export const launchOf = (opening: number): LaunchContext | null => live.get(opening) ?? null
export const latestOpening = () => openings
/** Its viewer closed, its return was taken, or its read failed. */
export function releaseLaunch(opening: number) { live.delete(opening); placed.delete(opening) }
/** The openings still held, oldest first: for the host's own bookkeeping. */
export const liveLaunches = (): number[] => [...live.keys()]
/** Thrown away between suites, so one case's opening is not the next's. */
export function clearLaunches() { live.clear(); placed.clear(); openings = 0 }

/** WHETHER A READ THAT FINISHED LATE MAY STILL ACT. Only the newest opening,
 *  and only in the Brain it was made against: an answer arriving after the
 *  reader opened something else, or after the server began serving another
 *  Brain, is dropped rather than drawn over what they are looking at.
 *
 *  AN OPENING THAT NAMED NO BRAIN IS NOT AN EXCEPTION TO THAT (F3). `if (!was)
 *  return true` let the one opening whose Brain cannot be checked through every
 *  late gate there is; it is `mayAct`'s `unconfirmed` now, like any other state
 *  with no identity to act under. A caller that supplies only `brainKey` is
 *  read through `servingOfKey`, so omitting the state cannot reopen it. */
export function acceptsLate(opening: number, now: { latest: number; brainKey?: BrainKey | null; serving?: Serving }, was: BrainKey | null): boolean {
  if (opening !== now.latest) return false
  return mayAct(was, now.serving ?? servingOfKey(now.brainKey ?? null)) === 'act'
}

/* -- focus ------------------------------------------------------------------ */

/** Just enough of an element to decide about it, so the decision is checkable
 *  without a DOM. */
export interface Focusable { isConnected: boolean }

export type FocusChoice =
  /** the very control that was pressed, still in the page */
  | { how: 'invoker' }
  /** that control by its stable identity, drawn again in the restored pane */
  | { how: 'control'; control: string }
  /** the launch's fallback */
  | { how: 'fallback'; fallback: FocusFallback }

/** WHERE FOCUS GOES WHEN A RESULT IS CLOSED (B3, H6). The element that opened
 *  it, where it is still connected; else the same control by identity, where
 *  the restored pane draws one; else the launch's own stable fallback. It is
 *  the LAUNCH'S fallback, not a module-global: two things opened from
 *  different places return to different controls. */
export function focusChoice(l: LaunchContext, invoker: Focusable | null, has: (control: string) => boolean): FocusChoice {
  if (invoker && invoker.isConnected) return { how: 'invoker' }
  if (l.focus.control && has(l.focus.control)) return { how: 'control', control: l.focus.control }
  return { how: 'fallback', fallback: l.focus.fallback }
}

/* -- returning -------------------------------------------------------------- */

/** WHAT A STORED LAUNCH CAN STILL RESTORE (H8). A reload leaves the history
 *  entry and takes the live launch with it: what is left is the Place, which
 *  is honest, and not a draft or a focus that no longer exists. */
export type Restore =
  /** the launch is this page's and live: Place, thread, reading, reply, draft */
  | { how: 'live'; launch: LaunchContext }
  /** no live launch (a reload): its saved Place, and nothing promised beyond */
  | { how: 'place'; place: LaunchPlace }
  /** another Brain, or another instance of it: nothing is replayed */
  | { how: 'other-brain'; words: string }

export function restoreOf(mark: LaunchMark, now: { brainKey: BrainKey | null; launch: (opening: number) => LaunchContext | null }): Restore {
  if (brainVerdict(mark.brainKey, now.brainKey) !== 'same') return { how: 'other-brain', words: BRAIN_MOVED }
  const l = now.launch(mark.opening)
  return l ? { how: 'live', launch: l } : { how: 'place', place: mark.place }
}

/** The explicit way back to a decision, in the reader's words. The pill's own
 *  words stay Needs you's (`GlobalDock.tsx`); this is what the shared host
 *  restores for it: the Place AND the pending item, never one without the
 *  other (B3, H4). */
export const RETURN_RESTORES = ['place', 'item'] as const
