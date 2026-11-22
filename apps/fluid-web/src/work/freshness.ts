/* Press-time readability for posts, records and conversations (P4).
 * Work launches re-read their exact group and follow its opaque item cursors.
 * Only a complete group can prove a member absent; refresh, malformed pages,
 * cycles or the 100-page bound refuse without claiming absence.
 * Direct launches use /fluid/api/result-ref, backed by the same inspection
 * resolver and existing interface read boundary. It returns its Brain identity
 * with the exact inspection. No Work/group or target is invented.
 * Stored association identity and resolved navigation identity stay distinct.
 * A live serving-instance binding and centre generation gate every answer;
 * navigation and its unsaved-work guard remain the host's responsibility.
 */
import { MOVED_WORDS, brainKeyOf, type BrainId } from '../brainBinding'
import { ResultsRefreshRequired, read as readOnce, type Id } from '../api'
import { workDetailPath } from './api'
import type { ResultGroup, ResultPage, WorkDetail, WorkResult } from './contract'

/** The three result destinations this module checks. `file` is the opener's. */
export type ResultOpens = 'post' | 'record' | 'conversation'

export const RESULT_OPENS: readonly ResultOpens[] = ['post', 'record', 'conversation']

/** Whether the server's `opens` word is one of the three checked here. */
export const isResultOpens = (o: unknown): o is ResultOpens =>
  typeof o === 'string' && (RESULT_OPENS as readonly string[]).includes(o)

/** WHAT WAS PRESSED, remembered as it was pressed. */
export interface Pressed {
  /** The Work whose result page the row came from. */
  expectation: Id | null
  /** The result group the row is in: the one group re-read. */
  group: Id | null
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
  return Array.isArray(page?.groups) ? page.groups.find((g) => g && g.id === group) ?? null : null
}

/** The one row of a fresh result page, by its exact reference. */
export function itemIn(page: ResultPage | null | undefined, group: Id, ref: Id): WorkResult | null {
  const items = groupIn(page, group)?.items
  return Array.isArray(items) ? items.find((i) => i && i.ref === ref) ?? null : null
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
  /* Unknown, moved and different serving identities all refuse. */
  if (now.moved || !p.brain || !now.brain || now.brain !== p.brain) {
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
  if (!validPage(page)) return { how: 'gone', why: COULD_NOT_CHECK }
  if (!p.group) return { how: 'gone', why: COULD_NOT_CHECK }
  if (!groupIn(page, p.group)) return { how: 'changed', why: NOT_LISTED }
  const item = itemIn(page, p.group, p.ref)
  if (!item) return groupIn(page, p.group)!.next_items_after || groupIn(page, p.group)!.omitted_items
    ? { how: 'gone', why: COULD_NOT_CHECK } : { how: 'changed', why: NOT_LISTED }
  return itemVerdict(p, item)
}

function validPage(page: ResultPage | null | undefined): page is ResultPage {
  return !!page && Array.isArray(page.groups) && page.groups.every((g) =>
    !!g && typeof g.id === 'string' && Array.isArray(g.items) &&
    g.items.every((i) => !!i && typeof i.ref === 'string') &&
    Number.isInteger(g.omitted_items) && g.omitted_items >= 0 &&
    (g.next_items_after === null || typeof g.next_items_after === 'string'))
}

function itemVerdict(p: Pressed, item: WorkResult): Checked {
  /* AN ARTIFACT IS NOT CHECKED HERE. If this reference now answers as one,
     it is not what was pressed, and the opener's own describe read owns it. */
  if (item.kind === 'artifact' || item.artifact) return { how: 'changed', why: NOT_THE_SAME }
  const i = item.inspection
  if (!i || i.id !== p.ref) return { how: 'gone', why: COULD_NOT_CHECK }
  /* THE SERVER'S OWN WORDS, AND ITS OWN TWO FLAGS. */
  if (item.available !== true || i.available !== true || i.state !== 'ok' || !i.opens) {
    return { how: 'gone', why: i.why || item.reason || COULD_NOT_CHECK }
  }
  if (!isResultOpens(i.opens) || i.opens !== p.opens) return { how: 'changed', why: NOT_THE_SAME }
  const at = atOf(item)
  if (!at) return { how: 'gone', why: i.why || item.reason || COULD_NOT_CHECK }
  return { how: 'open', at, item }
}

/** The path the re-read asks: the existing result page, one group of it. */
export const freshGroupPath = (p: Pressed, viewer: Id | null, itemsAfter: string | null = null): string =>
  workDetailPath(p.expectation!, viewer, { resultGroup: p.group, itemsAfter })

export const freshRefPath = (ref: Id): string => `/fluid/api/result-ref?ref=${encodeURIComponent(ref)}`
export interface RefAnswer { inspection: WorkResult['inspection']; brain: BrainId }

/** What the host supplies. `now` is asked when the answer lands, never before. */
export interface Checking {
  viewer: Id | null
  now: () => Now
  /** Defaults to the ordinary one-shot read (`api.read`). */
  read?: (path: string) => Promise<WorkDetail>
  readRef?: (path: string) => Promise<RefAnswer>
}

/** ASK AGAIN, THEN DECIDE. Never throws: a read that failed is an answer
 *  (`gone`), because a press must end in a word either way. */
export async function checkResultOpen(p: Pressed, deps: Checking): Promise<Checked> {
  const get = deps.read ?? ((path: string) => readOnce<WorkDetail>(path))
  try {
    const initial = deps.now()
    const before = verdict(p, { ok: false }, initial)
    if (before.how === 'dropped' || !p.brain || !initial.brain || initial.moved || initial.brain !== p.brain) return before
    if (!p.expectation || !p.group) {
      const got = await (deps.readRef ?? ((path: string) => readOnce<RefAnswer>(path)))(freshRefPath(p.ref))
      const now = deps.now()
      const gate = verdict(p, { ok: false }, now)
      if (gate.how === 'dropped' || now.moved || !now.brain || now.brain !== p.brain) return gate
      if (!got || brainKeyOf(got.brain) !== p.brain) return { how: 'gone', why: COULD_NOT_CHECK }
      const i = got.inspection
      return itemVerdict(p, { ref: p.ref, kind: 'record', available: i?.available,
        inspection: i, source: null, basis: [], association: 'referenced', actionable: false, reason: null })
    }
    let after: string | null = null
    const seen = new Set<string>()
    // Bounded work: exhaustion is uncheckable, never evidence of absence.
    for (let n = 0; n < 100; n++) {
      const detail = await get(freshGroupPath(p, deps.viewer, after))
      const checked = verdict(p, { ok: true, detail }, deps.now())
      if (!detail || detail.expectation !== p.expectation || !validPage(detail.result_groups)) return checked
      const group = groupIn(detail.result_groups, p.group)
      if (!group || itemIn(detail.result_groups, p.group, p.ref) || !group.next_items_after) return checked
      if (checked.how === 'dropped' || checked.how === 'gone' && checked.why === MOVED_WORDS) return checked
      after = group.next_items_after
      if (seen.has(after)) return { how: 'gone', why: COULD_NOT_CHECK }
      seen.add(after)
    }
    return { how: 'gone', why: COULD_NOT_CHECK }
  } catch (e) {
    const answer: Answer = e instanceof ResultsRefreshRequired
      ? { ok: false, why: e.message, refresh: true }
      : { ok: false, why: e instanceof Error ? e.message : null }
    return verdict(p, answer, deps.now())
  }
}
