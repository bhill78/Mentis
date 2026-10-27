import type { Id } from './api'

/* ------------------------------------------------------------------------ *
 * WHERE YOU ARE, WRITTEN DOWN.
 *
 * NAVIGATION IS STILL UI STATE and still not a durable fact -- nothing here
 * is recorded, and the corpus never learns that anybody looked at anything.
 * But WHICH SCOPE you are in has to survive a reload, and it did not: the
 * shell opened on `HOME`, overwrote `history.state` with it before anything
 * could read it back, and then replaced that with whichever Conversation
 * happened to be first. Refreshing anywhere sent you somewhere else.
 *
 * So the identifying part of a Place -- the scope, not the furniture -- goes
 * in the address bar. Only four things: whether this is Brain, which
 * Conversation, which Topic, which Turn. Everything else a Place carries
 * (which panes are open, how wide the canvas is, what the depth stack holds)
 * stays in `history.state`, because it is arrangement rather than location
 * and nobody wants it in a link they send somebody.
 *
 * IN THE HASH, deliberately. A path would have to be served, and this is a
 * static bundle behind one route; the hash is addressable, survives reload,
 * participates in Back and Forward, and needs nothing from the server.
 *
 * AN ADDRESS IS A CLAIM, NOT A GUARANTEE. What it names may have been
 * superseded or may never have existed, so reading one is separate from
 * trusting it -- see `App` for what happens when the record does not hold it.
 * ------------------------------------------------------------------------ */

export interface Address {
  /** Brain scope: everything here, rather than one Conversation. */
  brain: boolean
  conversation: Id | null
  topic: Id | null
  turn: Id | null
  /** GOVERNANCE, WHICH IS A LENS ON THIS SCOPE AND NOT A PLACE OF ITS OWN.
   *  null is the work itself: the Turns at a Conversation, Brain home at
   *  Brain. See the note at the foot of this file. */
  gov: GovState | null
  /** THE SCRATCH OPEN ON MAIN, at Brain scope only (`#/brain/scratch/<id>`).
   *  A Scratch is temporary working state the Brain keeps until it expires
   *  or is dismissed, so it is addressable: a refresh, Back, or the same
   *  Brain on another machine reopens it. null is the briefing itself. */
  scratch: Id | null
  /** MANAGE SOURCES, at Brain scope only (`#/brain/sources/...`). The part
   *  after `sources/`, exactly as written in the address -- each segment
   *  still percent-encoded, so an object key holding `/` stays one segment.
   *  '' is the overview; null is not in Manage Sources at all. Reached only
   *  from the Brain menu (U2), so it is a place of its own and never a lens
   *  over a Conversation. See `surfaces/sources/route.ts` for what each
   *  path names. */
  sources: string | null
  /** THE 3D BRAIN (`#/brain/space`), at Brain scope only, reached from the
   *  Brain menu. A place with no lens, like Manage Sources. */
  space: boolean
}

export const NOWHERE: Address = {
  brain: false,
  conversation: null,
  topic: null,
  turn: null,
  gov: null,
  scratch: null,
  sources: null,
  space: false,
}

/** True when the browser is not pointing anywhere yet: a first arrival. */
export const isBlank = (a: Address) => !a.brain && !a.conversation && !a.gov

/** WHERE THE SCOPE ENDS AND THE LENS BEGINS. The governance suffix only ever
 *  follows the scope, so it is looked for after it and never inside it: a
 *  Topic or a Turn whose id happens to be spelled `gov` is an id, not a door,
 *  and searching the whole segment list for the word opened the workspace on
 *  one. */
function scopeEnd(bits: string[]): number {
  /* Manage Sources is a place with no lens: everything after it is its own. */
  if (bits[0] === 'brain' && bits[1] === 'sources') return bits.length
  if (bits[0] === 'brain' && bits[1] === 'space') return bits.length
  if (bits[0] === 'brain') return bits[1] === 'scratch' && bits[2] ? 3 : 1
  if (bits[0] !== 'c' || !bits[1]) return 0
  let i = 2
  while (bits[i] === 't' || bits[i] === 'turn') i += 2
  return i
}

export function readAddress(hash = window.location.hash): Address {
  const bits = hash.replace(/^#\/?/, '').split('/').filter(Boolean)
  const gov = readGov(bits, scopeEnd(bits))
  if (bits[0] === 'brain' && bits[1] === 'sources')
    return { ...NOWHERE, brain: true, sources: bits.slice(2).join('/') }
  if (bits[0] === 'brain' && bits[1] === 'space') return { ...NOWHERE, brain: true, space: true }
  if (bits[0] === 'brain')
    return { ...NOWHERE, brain: true, gov, scratch: bits[1] === 'scratch' && bits[2] ? bits[2] : null }
  if (bits[0] !== 'c' || !bits[1]) return { ...NOWHERE, gov }
  const out: Address = { ...NOWHERE, conversation: bits[1], gov }
  for (let i = 2; i < bits.length - 1; i += 2) {
    if (bits[i] === 't') out.topic = bits[i + 1]
    if (bits[i] === 'turn') out.turn = bits[i + 1]
  }
  return out
}

export function writeAddress(a: Address): string {
  /* THE SCOPE IS THE PREFIX AND GOVERNANCE IS THE SUFFIX, in that order, so
     that one movement between scopes carries the whole lens across. */
  const tail = a.gov ? '/' + govSegments(a.gov).join('/') : ''
  if (a.brain && a.space) return '#/brain/space'
  if (a.brain && a.sources !== null && a.sources !== undefined)
    return '#/brain/sources' + (a.sources ? `/${a.sources}` : '')
  if (a.brain) return '#/brain' + (a.scratch ? `/scratch/${a.scratch}` : '') + tail
  if (!a.conversation) return tail ? '#/' + tail.slice(1) : ''
  let s = `#/c/${a.conversation}`
  if (a.topic) s += `/t/${a.topic}`
  if (a.turn) s += `/turn/${a.turn}`
  return s + tail
}

/** Put the address in the bar without adding a history entry of its own.
 *
 *  The Place machinery already pushes an entry when somebody moves, so the
 *  address only ever needs to CATCH UP with the entry that exists. Pushing
 *  here as well would make one movement take two Backs to undo. */
export function showAddress(a: Address): void {
  const want = writeAddress(a)
  if (want === window.location.hash) return
  const url = want || window.location.pathname + window.location.search
  window.history.replaceState(window.history.state, '', url)
}

/* ------------------------------------------------------------------------ *
 * THE GOVERNANCE ADDRESS.
 *
 * Governance is not a second application, so it is not a second address
 * space: it is a suffix on the scope that is already in the bar. `#/c/x`
 * is that Conversation's work; `#/c/x/gov/standing` is the same corpus
 * through that Conversation's lens. THE SCOPE IS THE PREFIX, which is what
 * makes I-8 true by construction -- changing scope rewrites the prefix and
 * leaves the lens, the filters and the open folds exactly where they were.
 *
 * EVERY STATE THE APPROVED UI COULD BE IN IS NAMEABLE (I-11): which lens,
 * which item in the inspector, which Participant, which execution, which
 * comparison, which trace, which historical question, whether the asks
 * popover is open, the filters, and which folds are open. A LINK IS THE
 * ANSWER somebody sends somebody else, and an interaction that cannot be
 * sent is an interaction the next person has to be told how to reach.
 *
 * AND NO HASH IS A REAL STATE (I-12), not a missing one: the bare file lands
 * on Conversation Governance -> Standing with nothing opened, which is what
 * `entry_check.py` verified about the approved artifact.
 * ------------------------------------------------------------------------ */

export type Lens = 'standing' | 'use'

export type TraceSubject = { kind: 'material' | 'participant' | 'execution'; id: Id }

/** WHICH ONE THING HOLDS THE CENTRE. An investigation is a place you went
 *  to, not a mode the page is in -- so it is one of these and never a flag
 *  beside the lens. `lens` means the corpus itself is on the centre. */
export type GovView =
  | { view: 'lens' }
  | { view: 'history'; question: string }
  | { view: 'trace'; subject: TraceSubject | null }
  | { view: 'execution'; execution: Id }
  | { view: 'compare'; left: Id; right: Id }
  | { view: 'preview' }

export interface GovFilters {
  q: string
  /** the Standing facet: '' | proposed | standing | history | disputed */
  state: string
  kind: string
  /** the In use facet: '' | placed | by_persona | when_named | truth_apt */
  applies: string
}

/** A section slug as a Kind may declare one (`governance_ui._SECTION`). */
export const GOV_SECTION = /^[a-z][a-z0-9-]{0,39}$/

export interface GovState {
  /** 'start', one of the three sections the surface has always had, or a
   *  section a Kind DECLARES (`authoring.section`): a short lower-case slug.
   *  Which ones exist is the Brain's vocabulary, so it is not a closed union. */
  section?: string
  whole?: boolean
  conversationFilter?: Id
  lens: Lens
  centre: GovView
  /** the one shared item inspector (I-43) */
  item: Id | null
  /** the Participant inspector (A12) */
  participant: Id | null
  /* THE ASKS POPOVER IS NOT HERE, AND WAS ONLY EVER HALF HERE. `asks` was
     written into the address, read back out of it and counted as a distinct
     Place for Back -- while the popover kept its own `useState` and never
     looked at it. So `#/…/gov/standing/asks/1` was linkable, opened nothing
     on arrival, and put a step in the history stack that Back had to walk
     through for no visible reason. A segment that only pretends to be a
     Place is worse than no segment: it is removed rather than left as a
     claim. Making the popover genuinely addressable is a change to the
     popover, and this comes back with it when somebody makes it. */
  filters: GovFilters
  /** folds opened by their own name, so a link can open one */
  open: string[]
}

export const NO_FILTERS: GovFilters = { q: '', state: '', kind: '', applies: '' }

/** Governance, opened on nothing in particular. The landing state. */
export const GOV_HOME: GovState = {
  lens: 'standing',
  centre: { view: 'lens' },
  item: null,
  participant: null,
  filters: NO_FILTERS,
  open: [],
}

const SEP = '~'
const enc = (s: string) => encodeURIComponent(s)
const dec = (s: string) => {
  try {
    return decodeURIComponent(s)
  } catch {
    /* A hand-edited address can hold a half-written escape. It names
       something odd rather than nothing, so it is taken literally. */
    return s
  }
}

/** The governance part of an address, as hash segments after the scope. */
function govSegments(g: GovState): string[] {
  const out = ['gov', g.lens]
  if (g.section) out.push('section', g.section)
  if (g.whole) out.push('whole', '1')
  if (g.conversationFilter) out.push('conversation', enc(g.conversationFilter))
  const c = g.centre
  if (c.view === 'history') out.push('ask', enc(c.question))
  if (c.view === 'execution') out.push('exe', enc(c.execution))
  if (c.view === 'compare') out.push('pair', enc(c.left) + SEP + enc(c.right))
  if (c.view === 'preview') out.push('preview', '1')
  if (c.view === 'trace')
    out.push('trace', c.subject ? c.subject.kind + SEP + enc(c.subject.id) : 'choose')
  if (g.item) out.push('item', enc(g.item))
  if (g.participant) out.push('who', enc(g.participant))
  const f = g.filters
  if (f.q || f.state || f.kind || f.applies)
    out.push('f', [f.state, f.kind, f.applies, f.q].map(enc).join(SEP))
  if (g.open.length) out.push('open', g.open.map(enc).join(SEP))
  return out
}

/** Read the governance part out of already-split hash segments.
 *
 *  A SEGMENT NOBODY WROTE IS NOT AN ERROR AND NOT A DEFAULT EITHER: an
 *  unrecognised pair is skipped, and whatever was recognised still holds.
 *  Half an address is still an address. */
function readGov(bits: string[], from = 0): GovState | null {
  const i = bits.indexOf('gov', from)
  if (i < 0) return null
  const g: GovState = { ...GOV_HOME, filters: { ...NO_FILTERS }, open: [] }
  if (bits[i + 1] === 'use') g.lens = 'use'
  for (let j = i + 2; j < bits.length - 1; j += 2) {
    const k = bits[j]
    const v = bits[j + 1]
    if (k === 'section' && GOV_SECTION.test(v)) g.section = v
    else if (k === 'whole') g.whole = v === '1'
    else if (k === 'conversation') g.conversationFilter = dec(v)
    else if (k === 'ask') g.centre = { view: 'history', question: dec(v) }
    else if (k === 'exe') g.centre = { view: 'execution', execution: dec(v) }
    else if (k === 'preview') g.centre = { view: 'preview' }
    else if (k === 'pair') {
      const [l, r] = v.split(SEP)
      if (l && r) g.centre = { view: 'compare', left: dec(l), right: dec(r) }
    } else if (k === 'trace') {
      if (v === 'choose') g.centre = { view: 'trace', subject: null }
      else {
        const [kind, id] = v.split(SEP)
        g.centre =
          kind === 'material' || kind === 'participant' || kind === 'execution'
            ? { view: 'trace', subject: { kind, id: dec(id ?? '') } }
            : { view: 'trace', subject: null }
      }
    } else if (k === 'item') g.item = dec(v)
    else if (k === 'who') g.participant = dec(v)
    else if (k === 'f') {
      const [st = '', kind = '', applies = '', ...q] = v.split(SEP)
      g.filters = { state: dec(st), kind: dec(kind), applies: dec(applies), q: dec(q.join(SEP)) }
    } else if (k === 'open') g.open = v.split(SEP).filter(Boolean).map(dec)
  }
  return g
}
