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
 *    placing      the reader is choosing which column: nothing left yet
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
import { actionOf, commitOpens, externalHref, goneWords, openable, sourceOf, type ResultDestination } from './targets'

/** What a file open is given: the bytes as the viewer reads them where the
 *  caller has them, else what the record said of them, and the SOURCE -- the
 *  post the content came from, or the Brain. Never a hardcoded Brain source
 *  where a post is known (B4). */
export interface FileOpen {
  ref: string
  item?: ViewerItem | null
  file?: HeldBytes | null
  source: ViewerSource | null
}

/** THE EXISTING HOST OPERATIONS, and only those. Nothing here adds a reader,
 *  a route, a renderer or a permission: each is what the page already does.
 *  A host that cannot do one of them says so by not having it. */
export interface OpenerHost {
  /** the Brain this page is bound to now */
  brainKey: BrainKey | null
  /** this page's own origin, for the external-URL policy */
  origin: string | null
  /** held bytes in the page's viewer: where it went, `choosing` while the
   *  reader picks a column, or null where it could not be opened */
  file?: (o: FileOpen) => Shown | 'choosing' | null
  /** a post, loading its thread and conversation even if folded or unread */
  post?: (conversation: string, post: string) => boolean
  /** a Brain record on its own page */
  record?: (ref: string) => boolean
  /** a conversation */
  conversation?: (ref: string) => boolean
  /** a new tab, on this press, with no referrer (`EXTERNAL_LINK`) */
  external?: (href: string) => boolean
  /** said to the reader, once */
  say?: (words: string) => void
}

export type Opened =
  | { what: 'opened'; how: 'file' | 'post' | 'record' | 'conversation'; where: Shown }
  | { what: 'placing' }
  | { what: 'external'; href: string }
  | { what: 'identity'; words: string }
  | { what: 'unavailable'; why: string }
  | { what: 'refused'; why: string }

/** WHETHER THE READER HAS ACTUALLY LEFT. Only a real open: a new tab leaves
 *  this page (and so the dock, the open form and its unsent draft) exactly as
 *  it was, and a failure is not a departure at all. */
export const leaves = (o: Opened) => o.what === 'opened'

/** Whether this open took the centre, and so owes the history one entry. */
export const displaces = (o: Opened) => o.what === 'opened' && o.where === 'max'

const NO_ROUTE = 'This page cannot open that from here.'

/** OPENS WHAT THE RECORD POINTS AT, through the host's existing readers.
 *
 *  `now` is for a resolve that finished LATE: an open may only act while it is
 *  still the newest opening, and in the Brain it was begun against. Omit it
 *  and the current opening counter is used, which is what an immediate press
 *  wants. */
export function openResultTarget(d: ResultDestination, launch: LaunchContext, host: OpenerHost, now?: { latest: number }): Opened {
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
    if (go.how === 'record' && host.record) return host.record(go.ref) ? { what: 'opened', how: 'record', where: 'max' } : { what: 'unavailable', why: NO_ROUTE }
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
    const went = host.file({ ref, item: d.item ?? null, file: d.file ?? null, source: sourceOf(d, host.brainKey) })
    if (went === 'choosing') return { what: 'placing' }
    if (!went || went === 'none') {
      const why = d.reason ?? 'Those contents could not be opened.'
      host.say?.(why)
      return { what: 'unavailable', why }
    }
    return { what: 'opened', how: 'file', where: went }
  }

  if (action === 'post') {
    if (!host.post || t.kind !== 'post') { host.say?.(NO_ROUTE); return { what: 'unavailable', why: NO_ROUTE } }
    /* THE EXACT THREAD AND CONVERSATION, loaded if they are not drawn: a post
       folded away, off-screen, or in a conversation this page has not read is
       still the post the record named (B3, item 4). */
    return host.post(t.conversation, t.post) ? { what: 'opened', how: 'post', where: 'none' } : { what: 'unavailable', why: 'That post could not be read.' }
  }

  if (action === 'conversation') {
    const ref = t.kind === 'record' ? t.ref : ''
    if (!host.conversation || !ref) { host.say?.(NO_ROUTE); return { what: 'unavailable', why: NO_ROUTE } }
    return host.conversation(ref) ? { what: 'opened', how: 'conversation', where: 'none' } : { what: 'unavailable', why: NO_ROUTE }
  }

  /* a record, or a request: the existing record page, never a synthetic post */
  const ref = t.kind === 'record' ? t.ref : ''
  if (!host.record || !ref) { host.say?.(NO_ROUTE); return { what: 'unavailable', why: NO_ROUTE } }
  return host.record(ref) ? { what: 'opened', how: 'record', where: 'max' } : { what: 'unavailable', why: NO_ROUTE }
}
