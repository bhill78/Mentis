/* IS IT STILL THERE TO OPEN? -- asked again at the press, for a result that is
 * a POST, a BRAIN RECORD or a CONVERSATION (P4).
 *
 * A result row says what the server said when the page last read it. Between
 * that read and the press a post can be deleted, a conversation permanently
 * deleted with everything in it, a record can stop being readable, and the
 * server can come to serve another Brain entirely. Until now those were found
 * out by ARRIVING at them: the press moved the reader, the guard reported the
 * move, and the destination page then said it could not be read. The reader
 * had already lost where they were.
 *
 * So the press asks again first, and moves only on what the fresh answer says.
 *
 * NOTHING NEW IS ASKED OF THE SERVER. The re-read is the result page the row
 * came from, for the one group it is in:
 *
 *   GET /api/work/<expectation>?result_group=<group>
 *
 * which is the existing route (`workDetailPath`), and which re-runs the
 * existing reader -- `mentis.operational.result_destinations.enrich` over
 * `mentis.fluid.inspect._Resolver` -- for exactly these items, outside every
 * cache, and answers with the SERVER'S OWN WORDS in `inspection.why` /
 * `reason` and the server's own `available` and `opens`. There is no new
 * route, no new parameter, no describe mode invented for this, and NO RULE
 * ABOUT WHO MAY READ WHAT IS DECIDED HERE: the read goes through the same
 * door, as the same viewer, and this module can only ever REFUSE an open that
 * the stale row offered. It can never grant one. `available` AND `opens`
 * together govern, exactly as the row's own contract says.
 *
 * ARTIFACTS ARE NOT THIS MODULE'S. An explicit artifact open is described
 * again on the press by the opener's own `?describe=1` read; a fresh answer
 * that says this ref is now an artifact is "not the same thing", not an
 * artifact check done here.
 *
 * AN ANSWER THAT ARRIVES LATE IS NOT AUTHORITY TO MOVE ANYBODY. The reader can
 * press Back, close the panel or go somewhere else while the re-read is in
 * flight. A pending check is therefore bound to three things it was made
 * with -- how many times the reader has moved, the exact reference pressed,
 * and the Brain the page was on -- and a check that no longer holds is dropped
 * without a word and without a move, because by then the reader asked for
 * none of it.
 *
 * THE UNSAVED-WORK GUARD IS UNTOUCHED. Nothing here moves anything. A verdict
 * of `open` is handed back to the host, which opens it the way it always
 * did -- `enterBrain` for a record, the conversation/post opener for the other
 * two -- each still `guarded`, so a half-written reply is still asked about
 * and Stay still prevents the move. Refusing earlier never skips that
 * question; it only means the question is never asked for somewhere that is
 * no longer there.
 */

import { MOVED_WORDS } from '../brainBinding'
import { ResultsRefreshRequired, read as readOnce } from '../api'
import { workDetailPath } from './api'
import type { Id, ResultGroup, ResultPage, WorkDetail, WorkResult } from './contract'

/** The three result destinations this module checks. `file` is the opener's. */
export type ResultOpens = 'post' | 'record' | 'conversation'

export const RESULT_OPENS: readonly ResultOpens[] = ['post', 'record', 'conversation']

/** Whether the server's `opens` word is one of the three checked here. */
export const isResultOpens = (o: unknown): o is ResultOpens =>
  typeof o === 'string' && (RESULT_OPENS as readonly string[]).includes(o)

/** WHAT WAS PRESSED, remembered as it was pressed. */
export interface Pressed {
  /** The Work whose result page the row came from. */
  expectation: Id
  /** The result group the row is in: the one group re-read. */
  group: Id
  /** The exact reference pressed. Identity: nothing else stands for it. */
  ref: Id
  /** What the row said it would open. A different answer is not this press. */
  opens: ResultOpens
  /** The Brain the page was bound to then; null where it knew of none. */
  brain: string | null
  /** The reader's move count then (see `Now.moves`). */
  moves: number
}

/** The page as it is WHEN THE ANSWER LANDS, not when the press was made. */
export interface Now {
  /** The Brain the page is bound to now; null where it knows of none. */
  brain: string | null
  /** Another Brain has answered since the page was opened. */
  moved: boolean
  /** Counts every move the reader has made: a Back, a Forward, a new place.
   *  It need only CHANGE on a move; nothing reads its value. */
  moves: number
}

/** Where to open, taken from the fresh answer alone -- never from the row
 *  that was pressed, which is the thing being doubted. */
export type OpenAt =
  | { opens: 'post'; conversation: Id; post: Id; number: number | null }
  | { opens: 'conversation'; conversation: Id }
  | { opens: 'record'; entry: Id }

export type Checked =
  /** Still readable; open it at exactly this, by the host's ordinary guarded way. */
  | { how: 'open'; at: OpenAt; item: WorkResult }
  /** Denied, deleted, unreadable or uncheckable: say `why`, move nothing. */
  | { how: 'gone'; why: string }
  /** It is no longer the thing that was pressed: say `why`, move nothing. */
  | { how: 'changed'; why: string }
  /** The reader moved on while this was being checked: say nothing, move nothing. */
  | { how: 'dropped' }

/** The server could not be asked, or did not answer in words of its own. */
export const COULD_NOT_CHECK =
  'Mentis could not check whether that is still there, so nothing was opened.'
/** The answer was about other work: never opened on it. */
export const ANOTHER_WORK =
  'That answer was about other work, so nothing was opened.'
/** The result is no longer among this work's results. */
export const NOT_LISTED =
  'That result is no longer one of this work’s results. Read the results again.'
/** The reference still resolves, but to something else than was pressed. */
export const NOT_THE_SAME =
  'What that opens has changed since it was shown. Read the results again.'
/** The results moved under the read itself. */
export const RESULTS_MOVED =
  'This work’s results have changed. Read them again.'

/** The one group of a fresh result page, by its exact id. */
export function groupIn(page: ResultPage | null | undefined, group: Id): ResultGroup | null {
  return page?.groups?.find((g) => g.id === group) ?? null
}

/** The one row of a fresh result page, by its exact reference. */
export function itemIn(page: ResultPage | null | undefined, group: Id, ref: Id): WorkResult | null {
  return groupIn(page, group)?.items?.find((i) => i.ref === ref) ?? null
}

/** WHERE THE FRESH ANSWER SAYS TO GO, or null where it does not say enough to
 *  go anywhere. A post needs the conversation it is in; a conversation needs
 *  itself; a record needs its own id. Nothing is filled in from the row that
 *  was pressed, and nothing is guessed. */
export function atOf(item: WorkResult | null | undefined): OpenAt | null {
  const i = item?.inspection
  if (!item || !i) return null
  if (i.opens === 'post') {
    const conversation = i.conversation ?? null
    const post = i.post ?? item.ref
    if (!conversation || !post) return null
    return { opens: 'post', conversation, post, number: i.number ?? null }
  }
  if (i.opens === 'conversation') {
    const conversation = i.conversation ?? item.ref
    return conversation ? { opens: 'conversation', conversation } : null
  }
  if (i.opens === 'record') return { opens: 'record', entry: i.id || item.ref }
  return null
}

/** What came back from the re-read, as the host saw it. */
export type Answer =
  | { ok: true; detail: WorkDetail }
  /** The read failed. `refresh` marks the server's own `ResultsRefreshRequired`. */
  | { ok: false; why?: string | null; refresh?: boolean }

/** THE WHOLE DECISION, as a function of what was pressed, what came back and
 *  where the reader is now. Fail-closed at every step: only the last line
 *  opens anything, and only on what the fresh answer itself said. */
export function verdict(p: Pressed, answer: Answer, now: Now): Checked {
  /* THE READER FIRST. Somebody who has moved on since the press is not told
     anything and is not moved: they asked for none of this any more. */
  if (now.moves !== p.moves) return { how: 'dropped' }
  /* A PRESS THAT KNEW WHICH BRAIN IT WAS ON NEVER OPENS ON ANOTHER. A press
     that knew of none claims none, so it refuses nothing on that ground. */
  if (now.moved || (p.brain !== null && now.brain !== null && now.brain !== p.brain)) {
    return { how: 'gone', why: MOVED_WORDS }
  }
  if (!answer.ok) {
    return answer.refresh
      ? { how: 'changed', why: answer.why || RESULTS_MOVED }
      : { how: 'gone', why: answer.why || COULD_NOT_CHECK }
  }
  const detail = answer.detail
  if (!detail || typeof detail !== 'object') return { how: 'gone', why: COULD_NOT_CHECK }
  /* THE ANSWER MUST BE ABOUT THE WORK THAT WAS PRESSED. */
  if (detail.expectation !== p.expectation) return { how: 'gone', why: ANOTHER_WORK }
  const page = detail.result_groups
  if (!page || !Array.isArray(page.groups)) return { how: 'gone', why: COULD_NOT_CHECK }
  if (!groupIn(page, p.group)) return { how: 'changed', why: NOT_LISTED }
  const item = itemIn(page, p.group, p.ref)
  if (!item) return { how: 'changed', why: NOT_LISTED }
  /* AN ARTIFACT IS NOT CHECKED HERE. If this reference now answers as one,
     it is not what was pressed, and the opener's own describe read owns it. */
  if (item.kind === 'artifact' || item.artifact) return { how: 'changed', why: NOT_THE_SAME }
  const i = item.inspection
  if (!i || i.id !== p.ref) return { how: 'gone', why: COULD_NOT_CHECK }
  /* THE SERVER'S OWN WORDS, AND ITS OWN TWO FLAGS. */
  if (!item.available || !i.available || !i.opens) {
    return { how: 'gone', why: i.why || item.reason || COULD_NOT_CHECK }
  }
  if (!isResultOpens(i.opens) || i.opens !== p.opens) return { how: 'changed', why: NOT_THE_SAME }
  const at = atOf(item)
  if (!at) return { how: 'gone', why: i.why || item.reason || COULD_NOT_CHECK }
  return { how: 'open', at, item }
}

/** The path the re-read asks: the existing result page, one group of it. */
export const freshGroupPath = (p: Pressed, viewer: Id | null): string =>
  workDetailPath(p.expectation, viewer, { resultGroup: p.group })

/** What the host supplies. `now` is asked when the answer lands, never before. */
export interface Checking {
  viewer: Id | null
  now: () => Now
  /** Defaults to the ordinary one-shot read (`api.read`). */
  read?: (path: string) => Promise<WorkDetail>
}

/** ASK AGAIN, THEN DECIDE. Never throws: a read that failed is an answer
 *  (`gone`), because a press must end in a word either way. */
export async function checkResultOpen(p: Pressed, deps: Checking): Promise<Checked> {
  const get = deps.read ?? ((path: string) => readOnce<WorkDetail>(path))
  let answer: Answer
  try {
    answer = { ok: true, detail: await get(freshGroupPath(p, deps.viewer)) }
  } catch (e) {
    answer = e instanceof ResultsRefreshRequired
      ? { ok: false, why: e.message, refresh: true }
      : { ok: false, why: e instanceof Error ? e.message : null }
  }
  return verdict(p, answer, deps.now())
}
