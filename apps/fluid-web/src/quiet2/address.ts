/* WHERE THE READER IS, AS AN ADDRESS (owner, 2026-11-20, navigation A1-A3).
 *
 * THE DEFECTS THIS ANSWERS. A Brain record's link opened the record and then
 * took `record` off the address, so a refresh showed the conversation and the
 * address in the bar could not be copied or bookmarked. Choosing another
 * conversation changed neither the address nor the browser's history, so a
 * refresh (or the address, copied) named the conversation the page was first
 * opened on, and Back left Quiet Chat. Manage Sources and the 3D Brain had no
 * address at all.
 *
 * Now the address always names the place shown, in the query, the same way at
 * `/` and at `/quiet2` (the path is whatever the page is on):
 *
 *   ?c=<conversation>                  the conversation shown
 *   ?c=…&at=<n>                        read around one post, as before
 *   ?c=…&record=<entry>                a Brain record, over that conversation
 *   ?c=…&sources=all                   Manage Sources: the Sources browser
 *   ?c=…&sources=<source>              one source's page
 *   ?c=…&sources=<source>&file=<path>  a held file read in place over it
 *   ?c=…&sources=add[/<kind>]          Add a source
 *   ?c=…&space=1                       the 3D Brain
 *
 * `sources` and `file` are written in the grammar Manage Sources already has
 * for its places (`surfaces/sources/route.ts`), not a second one. None of the
 * names is one of Fluid's (`src/entry.ts` hands `t, gov, home, stream, view, s,
 * w, from, lab` and a `#/…` hash at the root to Fluid), and nothing here ever
 * writes a `#/` hash.
 *
 * NOTHING HERE NAMES A SERVER. An address is the page's own path and a query:
 * it can only ever be this page, on this origin (centreHistory.ts says why
 * that matters).
 *
 * Everything in this file is a function of its arguments, so each row above
 * is checkable without a browser (`tests/quiet_address_unit.ts`). */
import { readRoute, writeRoute, type SourcesRoute } from '../surfaces/sources/route'
import type { BrainMainState } from './brain/logic'
import type { SourceMainState } from './sources/SourceMain'
import type { SpaceIntent } from './space/history'

/** WHAT TAKES THE CENTRE COLUMN, as an entry of the browser's own history
 *  (centreHistory.ts): a Brain record or the pages reached from it, a source
 *  or Add a source, the Sources browser over the conversation, the 3D Brain
 *  and what is being read FROM it. Each is intent: ids and keys, never a
 *  record, a graph, a read or an address. `null` is the conversation itself. */
export type CentreAt = { brain?: BrainMainState; source?: SourceMainState; sources?: 'all'; space?: SpaceIntent } | null

/** ONE ENTRY OF THE HISTORY: the conversation shown, and what is over it. */
export interface Place { c: string | null; at: CentreAt }

/** The query names Quiet Chat writes for a place. Every other name in the
 *  address (a layout or content override given for this load) is left as it is. */
export const PLACE_NAMES = ['c', 'at', 'record', 'sources', 'file', 'space'] as const

/** What an address asks for, as far as the address alone can say. */
export type Asked =
  | { what: 'conversation' }
  | { what: 'record'; entry: string }
  | { what: 'sources' }
  | { what: 'source'; col: string; file: SourcesRoute | null }
  | { what: 'add-source'; connector: string | null }
  | { what: 'space' }
  /** it names something this page cannot open; `words` says what, plainly */
  | { what: 'nothing'; words: string }

/** `at` is null unless it is a post number. `note` says, plainly, what part
 *  of the address could not be taken as written: the page says it once, and
 *  the address is put right (`addressOf`), so it never goes on naming a place
 *  that is not the one shown. */
export interface Address { c: string | null; at: string | null; asked: Asked; note?: string }

/** A Mentis entry id, as a record's address carries it. */
export const isEntryId = (id: string) => /^ent-[a-z0-9]{6,40}$/i.test(id)

export const NO_SUCH_RECORD = 'The address names a Brain record that is not in this Brain. The conversation is shown instead.'
export const NO_SUCH_SOURCE = 'The address names a source that is not in this Brain. The conversation is shown instead.'
export const NO_SUCH_FILE = 'The address names a file in a way that cannot be read. The source is shown instead.'
export const NO_SOURCE_NAMED = 'The address names a held file without saying which source it is in. Manage Sources is shown instead.'
export const NO_SUCH_AT = 'The address names a post number that is not a number. The latest posts are shown instead.'

/** A post number, as `at` carries one: a whole number from 1. */
export const isPostNumber = (at: string) => /^[1-9]\d{0,8}$/.test(at)

/** A file read in place is one of these; a source's own page or a list is not. */
const isFile = (r: SourcesRoute) => r.at === 'object' || r.at === 'observation' || r.at === 'compare'

/** What `search` asks for. One thing only: a record before Sources before the
 *  3D Brain, so an address carrying two never opens half of each. */
export function readAddress(search: string): Address {
  const q = new URLSearchParams(search)
  const c = q.get('c') || null
  const given = q.get('at')
  const at = given !== null && isPostNumber(given) ? given : null
  const read = readPlace(q, c, at)
  /* a post number that is not one is said only where nothing else is */
  return given !== null && at === null && !read.note && read.asked.what !== 'nothing' ? { ...read, note: NO_SUCH_AT } : read
}

function readPlace(q: URLSearchParams, c: string | null, at: string | null): Address {
  const record = q.get('record')
  if (record !== null) return { c, at, asked: isEntryId(record) ? { what: 'record', entry: record } : { what: 'nothing', words: NO_SUCH_RECORD } }
  const sources = q.get('sources')
  if (sources !== null) {
    if (sources === '' || sources === 'all') return { c, at, asked: { what: 'sources' } }
    const r = readRoute(sources)
    if (r.at === 'add') return { c, at, asked: { what: 'add-source', connector: null } }
    if (r.at === 'flow') return { c, at, asked: { what: 'add-source', connector: r.connector } }
    if (r.at === 'collection') {
      const named = q.get('file')
      if (named === null) return { c, at, asked: { what: 'source', col: r.col, file: null } }
      const f = named ? readRoute(named) : null
      /* A FILE THAT IS NOT ONE (or one of another source) is not opened as
         something else in silence: the source is shown, and it is said */
      const ok = !!f && isFile(f) && (f.at !== 'object' || f.col === r.col)
      return ok ? { c, at, asked: { what: 'source', col: r.col, file: f } } : { c, at, asked: { what: 'source', col: r.col, file: null }, note: NO_SUCH_FILE }
    }
    if (r.at === 'object') return { c, at, asked: { what: 'source', col: r.col, file: r } }
    /* an observation on its own does not say which source it is of */
    return { c, at, asked: { what: 'sources' }, note: NO_SOURCE_NAMED }
  }
  if (q.has('space') && q.get('space') !== '0') return { c, at, asked: { what: 'space' } }
  return { c, at, asked: { what: 'conversation' } }
}

/** THE CENTRE AS A FRESH PAGE OPENS IT from what its address asks for. A
 *  record opens as a link opens one; the 3D Brain is not here, because a graph
 *  is a session and one is only ever opened once the Brain is known (the page
 *  does that, then puts its entry in this place). */
export function centreFor(asked: Asked): CentreAt {
  switch (asked.what) {
    case 'record': return { brain: { stack: [{ page: 'record', entry: asked.entry }], origin: { from: 'link' } } }
    case 'sources': return { sources: 'all' }
    case 'source': return { source: { view: { page: 'source', col: asked.col }, reading: asked.file } }
    case 'add-source': return { source: { view: { page: 'add', connector: asked.connector }, reading: null } }
    default: return null
  }
}

/** What an entry of the history asks for, in the address's own terms: the
 *  inverse of `centreFor`, for everything that has an address. What has none
 *  (Import, an entry inspector, a Turn read from the 3D Brain) is addressed
 *  as the conversation it is over, which is where a refresh then lands. */
export function askedOf(at: CentreAt): Asked {
  if (!at) return { what: 'conversation' }
  if (at.brain) {
    const top = at.brain.stack[at.brain.stack.length - 1]
    return top && top.page === 'record' ? { what: 'record', entry: top.entry } : { what: 'conversation' }
  }
  if (at.source) {
    const v = at.source.view
    return v.page === 'add' ? { what: 'add-source', connector: v.connector } : { what: 'source', col: v.col, file: at.source.reading }
  }
  if (at.sources) return { what: 'sources' }
  if (at.space) {
    if (at.space.phase === 'graph') return { what: 'space' }
    /* read FROM the graph: the thing read is what a refresh can show again */
    return at.space.target.kind === 'record' ? { what: 'record', entry: at.space.target.entry } : { what: 'conversation' }
  }
  return { what: 'conversation' }
}

/** THE ADDRESS OF A PLACE: this page's own path, the place's names first,
 *  then whatever else the address already carried. `loaded` is what the page
 *  was opened with: `at` belongs to that conversation and is kept for it,
 *  because the conversation is still read around that post whenever it is the
 *  one shown. A hash (a post's anchor) stays only while the conversation does.
 *  `spaceOwed` is the one place an address names before the page can show
 *  it: the 3D Brain asked for by address, waiting for the Brain to be known. */
export function addressOf(now: { pathname: string; search: string; hash: string }, to: Place, loaded: { c: string | null; at: string | null }, spaceOwed = false): string {
  const was = new URLSearchParams(now.search)
  const q = new URLSearchParams()
  if (to.c) q.set('c', to.c)
  if (to.c && loaded.at && loaded.c === to.c) q.set('at', loaded.at)
  const a = askedOf(to.at)
  if (a.what === 'record') q.set('record', a.entry)
  else if (a.what === 'sources') q.set('sources', 'all')
  else if (a.what === 'add-source') q.set('sources', writeRoute(a.connector ? { at: 'flow', connector: a.connector } : { at: 'add' }))
  else if (a.what === 'source') {
    q.set('sources', writeRoute({ at: 'collection', col: a.col, tab: 'overview' }))
    if (a.file) q.set('file', writeRoute(a.file))
  } else if (a.what === 'space' || (spaceOwed && !to.at)) q.set('space', '1')
  for (const [k, v] of was) if (!(PLACE_NAMES as readonly string[]).includes(k)) q.append(k, v)
  const sameConversation = !was.get('c') || was.get('c') === to.c
  const hash = sameConversation && !now.hash.startsWith('#/') ? now.hash : ''
  const s = q.toString()
  return now.pathname + (s ? '?' + s : '') + hash
}

/** An entry made before places carried their conversation (a tab left open
 *  across the change) is read as the centre it was, over the conversation
 *  shown now; anything else that is not a place is the conversation. */
export function placeOf(held: unknown, c: string | null): Place {
  if (held && typeof held === 'object') {
    const h = held as Record<string, unknown>
    if ('c' in h && 'at' in h) return { c: typeof h.c === 'string' ? h.c : null, at: (h.at ?? null) as CentreAt }
    if ('brain' in h || 'source' in h || 'space' in h) return { c, at: held as CentreAt }
  }
  return { c, at: null }
}
