/* ONE HOST OPERATION OPENS EVERY RESULT -- `openResultTarget` (navigation
 * review adm-d9152e0643d7, B4).
 *
 * THE DEFECT THIS ANSWERS: "open the authorized target" was a phrase, not an
 * operation. The result chooser, the dock and Needs you each resolved and
 * opened their own way, so the same thing behaved differently depending on
 * where it was pressed, a reference that could not be opened was discovered by
 * pressing it, and a failed open still closed the dock and lost the reader's
 * place.
 *
 * WHAT IT DOES, AND WHAT IT REFUSES TO DO. The target's own discriminant picks
 * the route (`targets.ts` `actionOf`); the host supplies the existing readers
 * and navigation and nothing new. It returns what actually happened, and the
 * CALLER KEEPS ITS STATE until something was actually opened:
 *
 *    opened       a viewer, a post, a record or a conversation is shown
 *    leaving      asked for, and not arrived: a guard is open, a thread is
 *                 being read. Nothing has been left; `settled` says what
 *                 became of it (independent review adm-f3244dbc4bae, B3)
 *    placing      the reader is choosing which column: nothing left yet
 *    cancelled    the reader stayed, or a guard refused: nothing moved
 *    external     a recorded external link, in a new tab -- the page, the dock
 *                 and the draft stay exactly as they were
 *    identity     a commit with no record to inspect: its exact identity, said
 *    unavailable  the server's own reason, and nothing is opened
 *    refused      a stale read or another Brain: nothing is opened
 *
 * `leaves` is the one question the dock and the decision form ask of the
 * result: only a real open is a departure. A failure is never dressed up as
 * one, so a draft is never discarded for an open that did not happen.
 *
 * Pure apart from the host it is given, so every row is checkable against a
 * fake host without a browser (`tests/quiet2_result_opener_unit.ts`). */
import type { HeldBytes, ViewerItem } from '../../quiet/media/view'
import type { ViewerSource } from '../viewer/types'
import { BRAIN_MOVED, acceptsLate, brainVerdict, latestOpening, type BrainKey, type LaunchContext } from './launch'
import type { Shown } from './history'
import { actionOf, commitOpens, externalHref, goneWords, openable, sourceOf, targetKey, type ResultDestination, type ResultTarget } from './targets'

/** WHAT A HOST SAYS OF A MOVE IT WAS ASKED FOR (independent review
 *  adm-f3244dbc4bae, B3). The page's own navigation is not synchronous: a
 *  conversation press runs the unsaved-work guard, which the reader can
 *  answer with Stay; a post read fetches its thread and can fail. A boolean
 *  cannot say which of those happened, and reading one as success is what
 *  reported departures that never occurred.
 *
 *    completed  the guard passed AND the route or the read actually succeeded
 *    requested  it has begun: the answer comes to `settled`, not from here
 *    cancelled  the reader stayed, or a guard refused: nothing moved
 *    failed     the route or the read failed: nothing moved
 *
 *  Only `completed` is a departure. Anything else keeps the caller's page,
 *  its open form and its unsent draft exactly as they are. */
export type Navigated = 'completed' | 'requested' | 'cancelled' | 'failed'

export type Navigation = Navigated | { how: Navigated; why?: string | null }

const NAVIGATED = new Set<string>(['completed', 'requested', 'cancelled', 'failed'])

/** The host's answer, read safely. A HOST WRITTEN TO THE OLDER BOOLEAN SHAPE
 *  IS NOT TREATED AS HAVING ARRIVED: `true` meant "I have begun", which is
 *  `requested`, and anything unrecognised is read the same way -- never as a
 *  completion. `false` and nothing at all are a failure, as they were. */
export function navigationOf(answer: unknown): { how: Navigated; why: string | null } {
  if (typeof answer === 'string') return { how: NAVIGATED.has(answer) ? (answer as Navigated) : 'requested', why: null }
  if (answer && typeof answer === 'object') {
    const how = (answer as { how?: unknown }).how
    const why = (answer as { why?: unknown }).why
    return { how: typeof how === 'string' && NAVIGATED.has(how) ? (how as Navigated) : 'requested', why: typeof why === 'string' ? why : null }
  }
  if (answer === false || answer === null || answer === undefined) return { how: 'failed', why: null }
  return { how: 'requested', why: null }
}

/** WHERE A FILE OPEN ACTUALLY WENT, once it has gone anywhere: the column or
 *  the maximised place, the reader's cancellation of the chooser, or a failed
 *  read. The host says this through `FileOpen.settled` where the press did
 *  not finish on the press (a column chosen afterwards). */
export type Placed =
  | { how: 'completed'; where: Shown }
  | { how: 'cancelled' }
  | { how: 'failed'; why?: string | null }

/** What a file open is given: the bytes as the viewer reads them where the
 *  caller has them, else what the record said of them, the SOURCE -- the post
 *  the content came from, or the Brain (never a hardcoded Brain source where a
 *  post is known) -- and WHERE THE READER WAS.
 *
 *  `launch` is the caller's own launch, carried through so the viewer this
 *  opens returns to the control that was pressed and to the Place it was
 *  pressed in (B2): a launch the host makes for itself after the read is a
 *  different opening, with a different focus and a different Place. */
export interface FileOpen {
  ref: string
  item?: ViewerItem | null
  file?: HeldBytes | null
  source: ViewerSource | null
  /** THE RESULT'S OWN IDENTITY, which is not its source (re-review
   *  adm-263df1ccb512, F12). The host writes one history entry for a maximised
   *  result, and the entry must name the DELIVERABLE: deriving it from the
   *  `ViewerSource` instead records the post the bytes came from, so landing on
   *  that entry again re-resolves to the source rather than to the result, and
   *  a Brain-sourced artifact gets no target at all. */
  target: ResultTarget
  launch: LaunchContext
  /** told once where the placement finishes after the press */
  settled: (p: Placed) => void
}

/** A FRESH READ OF WHAT IS BEING OPENED, on the explicit open (contract
 *  A4/P4). A row the dock drew minutes ago says what was true then; an
 *  Admission can have been deleted, purged or found corrupt since. The host's
 *  existing reader answers, and nothing here reaches bytes: a fresh
 *  destination is the server's own availability and `opens` words again.
 *
 *    fresh      the server answered: THIS destination is what is opened
 *    reading    it has been asked: the answer comes to `settled`
 *    gone       it is not available to this reader now, in the server's own
 *               words -- INCLUDING a refusal, a failure and an answer about
 *               something else, none of which authorises reusing the
 *               descriptor in hand (re-review adm-d84456fd4c3c, B4.1)
 *    unchecked  this host has no reader for this route at all: the descriptor
 *               in hand stands. It is NOT what a failed or refused read says,
 *               and no artifact route answers it any more. */
export type Read =
  | { how: 'fresh'; destination: ResultDestination }
  | { how: 'reading' }
  | { how: 'gone'; why: string }
  | { how: 'unchecked' }

/** THE EXISTING HOST OPERATIONS, and only those. Nothing here adds a reader,
 *  a route, a renderer or a permission: each is what the page already does.
 *  A host that cannot do one of them says so by not having it.
 *
 *  Each navigation is given a `settled` to call when it knows -- after the
 *  guard, after the thread read -- and says meanwhile whether it has begun.
 *  A host whose move really is finished on the press answers `'completed'`. */
export interface OpenerHost {
  /** the Brain this page is bound to now */
  brainKey: BrainKey | null
  /** this page's own origin, for the external-URL policy */
  origin: string | null
  /** held bytes in the page's viewer: where it went, `choosing` while the
   *  reader picks a column, or null where it could not be opened */
  file?: (o: FileOpen) => Shown | 'choosing' | null
  /** a post, loading its thread and conversation even if folded or unread */
  post?: (conversation: string, post: string, settled: (n: Navigation) => void) => Navigation
  /** a Brain record on its own page */
  record?: (ref: string, settled: (n: Navigation) => void) => Navigation
  /** a conversation */
  conversation?: (ref: string, settled: (n: Navigation) => void) => Navigation
  /** a new tab, on this press, with no referrer (`EXTERNAL_LINK`) */
  external?: (href: string) => boolean
  /** READ AGAIN ON THIS PRESS, FAIL-CLOSED (A4/P4; re-review adm-d84456fd4c3c,
   *  B4.1). THE WHOLE DESTINATION is handed over, not only the reference,
   *  because the fresh read answers about AVAILABILITY and the destination
   *  carries facts the read does not: where the bytes came from (the artifact
   *  description deliberately strips `source`), the label, and the record's
   *  own basis. The reader returns those unchanged in its fresh destination
   *  and replaces only what it actually read.
   *
   *  It is asked on EVERY explicit artifact open, whatever surface the press
   *  came from: a request behind the press is not a condition of checking. A
   *  host that has no reader for a route simply has none, and only then is a
   *  press `unchecked`. The launch is still passed, for a reader that wants
   *  the press's own identity. */
  read?: (d: ResultDestination, settled: (r: Read) => void, launch?: LaunchContext) => Read
  /** said to the reader, once */
  say?: (words: string) => void
}

export type Route = 'file' | 'post' | 'record' | 'conversation'

export type Opened =
  | { what: 'opened'; how: Route; where: Shown }
  /** ASKED FOR, AND NOT ARRIVED: a guard is open, a thread is being read, or
   *  a bound read is in flight. Nothing has been left and nothing is owed to
   *  the history yet; the answer reaches `settled`. */
  | { what: 'leaving'; how: Route }
  | { what: 'placing' }
  /** the reader stayed, or a guard refused: everything is as it was */
  | { what: 'cancelled'; why: string }
  | { what: 'external'; href: string }
  | { what: 'identity'; words: string }
  | { what: 'unavailable'; why: string }
  | { what: 'refused'; why: string }

/** WHETHER THE READER HAS ACTUALLY LEFT. Only a real, completed open: a new
 *  tab leaves this page (and so the dock, the open form and its unsent draft)
 *  exactly as it was; a navigation still being guarded or read has not left;
 *  and a cancellation or a failure is not a departure at all. */
export const leaves = (o: Opened) => o.what === 'opened'

/** Whether this open took the centre, and so owes the history one entry. */
export const displaces = (o: Opened) => o.what === 'opened' && o.where === 'max'

/** Whether something is still happening for this press: the caller keeps
 *  everything it has, and what became of it arrives at `settled`. */
export const pending = (o: Opened) => o.what === 'leaving' || o.what === 'placing'

/** WHAT THE CALLER IS TOLD WHEN AN OPEN FINISHES AFTER THE PRESS, and how the
 *  press itself is judged: both are an `Opened`, so the dock arms its way back
 *  in one place, on one rule (`leaves`), whenever the answer comes. */
export interface OpenNow {
  /** the newest opening, where it is not the module's own counter */
  latest?: number
  /** told once, when an open this press REQUESTED completed, was cancelled
   *  or failed. Never called for an answer the press already carried. */
  settled?: (o: Opened) => void
  /** internal: a fresh read has been taken for this press already */
  read?: 'done'
}

const NO_ROUTE = 'This page cannot open that from here.'
const STAYED = 'Nothing was opened: this page is as it was.'
const NOT_THE_SAME = 'That read answered about something else, so nothing was opened.'
const WENT_WRONG: Record<Route, string> = {
  file: 'Those contents could not be opened.',
  post: 'That post could not be read.',
  record: NO_ROUTE,
  conversation: NO_ROUTE,
}

/** One navigation answer as an `Opened`. `say` is for the reader, and is said
 *  only where something actually went wrong: a reader who chose Stay knows
 *  what they chose. */
function arrived(how: Route, where: Shown, n: { how: Navigated; why: string | null }, host: OpenerHost): Opened {
  switch (n.how) {
    case 'completed': return { what: 'opened', how, where }
    case 'requested': return { what: 'leaving', how }
    case 'cancelled': return { what: 'cancelled', why: n.why ?? STAYED }
    case 'failed': {
      const why = n.why ?? WENT_WRONG[how]
      host.say?.(why)
      return { what: 'unavailable', why }
    }
  }
}

/** OPENS WHAT THE RECORD POINTS AT, through the host's existing readers.
 *
 *  `now` is for a resolve that finished LATE: an open may only act while it is
 *  still the newest opening, and in the Brain it was begun against. Omit it
 *  and the current opening counter is used, which is what an immediate press
 *  wants. Its `settled` is how an open that finishes after the press -- a
 *  guarded conversation move, a thread read, a column chosen afterwards --
 *  says what became of it. */
export function openResultTarget(d: ResultDestination, launch: LaunchContext, host: OpenerHost, now?: OpenNow): Opened {
  /* ANOTHER BRAIN, OR ANOTHER INSTANCE OF IT: nothing is opened and nothing is
     replayed. Checked before the target, so a stale read cannot even resolve. */
  if (launch.brainKey && brainVerdict(launch.brainKey, host.brainKey) !== 'same') {
    host.say?.(BRAIN_MOVED)
    return { what: 'refused', why: BRAIN_MOVED }
  }
  /* A LATE READ CANNOT REPLACE A NEWER OPENING (B3, item 7). */
  if (!acceptsLate(launch.opening, { latest: now?.latest ?? latestOpening(), brainKey: host.brainKey }, launch.brainKey))
    return { what: 'refused', why: 'Something else has been opened since.' }

  const t = d.target
  const action = actionOf(d)
  /** what a late answer for this press is reported as */
  const later = (how: Route, where: Shown) => (answer: Navigation) => {
    if (!now?.settled) return
    const n = navigationOf(answer)
    /* "still going" is not an answer: nothing is reported twice. */
    if (n.how === 'requested') return
    now.settled(arrived(how, where, n, host))
  }

  if (action === 'external') {
    const href = t.kind === 'url' ? externalHref(t.href, host.origin) : null
    if (!href || !host.external) {
      const why = href ? NO_ROUTE : 'That link is not one this page opens.'
      host.say?.(why)
      return { what: 'unavailable', why }
    }
    return host.external(href) ? { what: 'external', href } : { what: 'unavailable', why: NO_ROUTE }
  }

  if (action === 'commit') {
    /* THROUGH THE RECORD THAT STATES IT, where there is one; otherwise its
       exact identity, said plainly. No Git is fetched and no repository URL is
       invented (B4). */
    const go = t.kind === 'commit' ? commitOpens(t) : { how: 'identity' as const, words: NO_ROUTE }
    if (go.how === 'record' && host.record)
      return arrived('record', 'max', navigationOf(host.record(go.ref, later('record', 'max'))), host)
    const words = go.how === 'identity' ? go.words : NO_ROUTE
    host.say?.(words)
    return { what: 'identity', words }
  }

  if (action === 'unavailable') {
    const why = openable(d).why ?? goneWords(d.availability)
    host.say?.(why)
    return { what: 'unavailable', why }
  }

  if (action === 'file') {
    if (!host.file) { host.say?.(NO_ROUTE); return { what: 'unavailable', why: NO_ROUTE } }
    const ref = t.kind === 'artifact' ? t.ref : ''
    /* READ AGAIN BEFORE OPENING IT (A4/P4). The row in hand says what was
       true when it was drawn; the press is when it matters. The host's own
       bound reader answers, or says it has none. */
    if (host.read && now?.read !== 'done' && ref) {
      /* THE SAME THING, OR NOTHING -- on BOTH answers (re-review
         adm-263df1ccb512, F04). A second read that answers about another
         identity is not this press's answer, and whether it answered on the
         press or a moment later makes no difference to that: the host's own
         documented reader is asynchronous, so the delayed branch is the one
         that actually runs. Refused the same way, in the same words. */
      const sameThing = (fresh: ResultDestination): Opened | null => {
        if (targetKey(fresh.target) === targetKey(t)) return null
        host.say?.(NOT_THE_SAME)
        return { what: 'refused', why: NOT_THE_SAME }
      }
      /* THE OPEN HAPPENS WHEN THE ANSWER COMES, AND THE REPORT IS SEPARATE
         (re-review adm-d84456fd4c3c, B4.1). This callback used to return at
         once unless a `settled` observer had been registered -- so a caller
         that did not want to be told the outcome never got the viewer either,
         and `openResult(d, launch)` with the documented asynchronous reader
         simply did nothing. Completing the action is this module's business;
         `settled` is only how it is reported, and is optional. */
      const tell = (o: Opened) => { now?.settled?.(o) }
      const fresh = host.read(d, (r) => {
        if (r.how === 'reading') return
        if (r.how === 'gone') { host.say?.(r.why); tell({ what: 'unavailable', why: r.why }); return }
        if (r.how === 'fresh') {
          const other = sameThing(r.destination)
          if (other) { tell(other); return }
        }
        const again = r.how === 'fresh' ? r.destination : d
        const went = openResultTarget(again, launch, host, { ...now, read: 'done' })
        /* "still going" is not an answer, here as anywhere: a reader now
           choosing a column is told about by the chooser's own answer, once. */
        if (!pending(went)) tell(went)
      }, launch)
      if (fresh.how === 'gone') { host.say?.(fresh.why); return { what: 'unavailable', why: fresh.why } }
      if (fresh.how === 'reading') return { what: 'leaving', how: 'file' }
      if (fresh.how === 'fresh') {
        const other = sameThing(fresh.destination)
        if (other) return other
        return openResultTarget(fresh.destination, launch, host, { ...(now ?? {}), read: 'done' })
      }
    }
    const went = host.file({
      ref, item: d.item ?? null, file: d.file ?? null, source: sourceOf(d, host.brainKey), target: t, launch,
      settled: (p) => {
        if (!now?.settled) return
        if (p.how === 'completed') { now.settled({ what: 'opened', how: 'file', where: p.where }); return }
        if (p.how === 'cancelled') { now.settled({ what: 'cancelled', why: STAYED }); return }
        const why = p.why ?? d.reason ?? WENT_WRONG.file
        host.say?.(why)
        now.settled({ what: 'unavailable', why })
      },
    })
    if (went === 'choosing') return { what: 'placing' }
    if (!went || went === 'none') {
      const why = d.reason ?? WENT_WRONG.file
      host.say?.(why)
      return { what: 'unavailable', why }
    }
    return { what: 'opened', how: 'file', where: went }
  }

  if (action === 'post') {
    if (!host.post || t.kind !== 'post') { host.say?.(NO_ROUTE); return { what: 'unavailable', why: NO_ROUTE } }
    /* THE EXACT THREAD AND CONVERSATION, loaded if they are not drawn: a post
       folded away, off-screen, or in a conversation this page has not read is
       still the post the record named (B3, item 4). THE DEPARTURE IS THE
       HOST'S ANSWER, not the call returning: that read is asynchronous and
       its conversation move is guarded. */
    return arrived('post', 'none', navigationOf(host.post(t.conversation, t.post, later('post', 'none'))), host)
  }

  if (action === 'conversation') {
    const ref = t.kind === 'record' ? t.ref : ''
    if (!host.conversation || !ref) { host.say?.(NO_ROUTE); return { what: 'unavailable', why: NO_ROUTE } }
    return arrived('conversation', 'none', navigationOf(host.conversation(ref, later('conversation', 'none'))), host)
  }

  /* a record, or a request: the existing record page, never a synthetic post */
  const ref = t.kind === 'record' ? t.ref : ''
  if (!host.record || !ref) { host.say?.(NO_ROUTE); return { what: 'unavailable', why: NO_ROUTE } }
  return arrived('record', 'max', navigationOf(host.record(ref, later('record', 'max'))), host)
}
