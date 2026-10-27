import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { Id } from './api'
import { isBlank, readAddress, showAddress, type Address, type GovState } from './address'
import { holds, type Breadth, type Layer, type Primary, type Resolution } from './layouts/composition'

/* ------------------------------------------------------------------------ *
 * NAVIGATION IS UI STATE.
 *
 * Everything below describes WHERE THE OWNER IS LOOKING — which conversation,
 * which topic focus, which turn, which thread, which media item, and which
 * surfaces are composed around them. None of it is a durable fact and none of
 * it is ever sent anywhere: it lives in React state and in `history.state`,
 * and nowhere else. No POST, no record, no corpus.
 *
 * One Place is one meaningful state. Moving between Places pushes a browser
 * history entry, so Back — the app's own and the device's — walks the same
 * list of places the owner actually visited, rather than closing whichever
 * pane happens to be nearest. The URL never changes: a Place is a view of the
 * record, not an address for it.
 * ------------------------------------------------------------------------ */

export type SurfaceName = 'rail' | 'topics' | 'history' | 'graph' | 'media' | 'thread' | 'details'

/** Which surface initiated the current selection. Read only by the
 *  synchronisation effects, so that the surface a person is scrolling is
 *  never scrolled back by its own change. Never a durable fact. */
export type Origin = SurfaceName | 'conversation' | 'shell' | null

export interface Place {
  conversation: Id | null
  topic: Id | null
  /** the Turn in view across every projection */
  turn: Id | null
  /** the operational act in view, when one was selected */
  act: Id | null
  thread: Id | null
  /** the MediaItem key the viewer is on, null when the viewer is closed */
  media: string | null
  /** the media viewer, over everything */
  overlay: boolean
  surfaces: Record<SurfaceName, boolean>
  /** phone and tablet: which single surface is occupying the screen */
  aux: SurfaceName | null
  compare: boolean
  /** GOVERNANCE IS A LENS ON THIS SCOPE, held as one field so that a scope
   *  change carries it unchanged (I-8). null is the work itself. */
  gov: GovState | null
  /** GOVERNANCE WAS ENTERED FROM MAIN. Set by the move itself -- any move
   *  that opens Governance while standing on Main (Brain scope, no lens) --
   *  and cleared by any move out of Governance or into a Conversation. It
   *  decides only what Brain-scope Governance's prominent exit says and
   *  where it lands: back to Brain home when that is where it was entered
   *  from (#136: "a clear and easy way to exit"; D-5, G-9). */
  govFromHome?: boolean
  /** THE SCRATCH OPEN ON MAIN (Brain scope only), or null for the briefing.
   *  Kept when a move leaves Main, so coming back to Main comes back to it. */
  scratch?: Id | null
  /** MANAGE SOURCES (Brain scope only): the path inside it, '' for the
   *  overview, null when not there. See `Address.sources`. */
  sources?: string | null
  /** THE 3D BRAIN (Brain scope only), true while standing in it. */
  space?: boolean

  /* ---- the canvas composition (see layouts/composition.ts) ------------- */

  /** how much canvas the current primary presentation is given */
  breadth: Breadth
  /** what is holding the centre of the canvas */
  primary: Primary
  /** which resolution of this scope's operational history is showing */
  resolution: Resolution
  /** contextual depth, as a stack. Only the top is drawn. */
  depth: Layer[]

  /** who moved last — the loop guard, not part of a Place's identity */
  from: Origin
}

export const SURFACES: SurfaceName[] = [
  'rail',
  'topics',
  'history',
  'graph',
  'media',
  'thread',
  'details',
]

const NONE: Record<SurfaceName, boolean> = {
  rail: false,
  topics: false,
  history: false,
  graph: false,
  media: false,
  thread: false,
  details: false,
}

export const HOME: Place = {
  conversation: null,
  topic: null,
  turn: null,
  act: null,
  thread: null,
  media: null,
  overlay: false,
  surfaces: { ...NONE, rail: true },
  aux: null,
  compare: false,
  gov: null,
  scratch: null,
  sources: null,
  space: false,
  breadth: 'normal',
  primary: 'conversation',
  resolution: 'glance',
  depth: [],
  from: null,
}

/** The part of a Place that belongs in the address bar. */
export const addressOf = (p: Place): Address => ({
  brain: p.conversation === null,
  conversation: p.conversation,
  topic: p.topic,
  turn: p.turn,
  gov: p.gov,
  scratch: p.conversation === null ? (p.scratch ?? null) : null,
  sources: p.conversation === null && !p.gov ? (p.sources ?? null) : null,
  space: p.conversation === null && !p.gov && !!p.space,
})

export type Patch = Partial<Omit<Place, 'surfaces'>> & {
  surfaces?: Partial<Record<SurfaceName, boolean>>
}

/** Two Places are the same place when everything a person could perceive is
 *  the same. `from` is deliberately excluded: it is a guard, not a location. */
const same = (a: Place, b: Place): boolean =>
  a.conversation === b.conversation &&
  a.topic === b.topic &&
  a.turn === b.turn &&
  a.act === b.act &&
  a.thread === b.thread &&
  a.media === b.media &&
  a.overlay === b.overlay &&
  a.compare === b.compare &&
  /* Every governance state is its own Place, so Back walks out of an
     investigation, an inspector and a lens in the order they were entered
     -- which is what I-9 and I-10 are asking of the history stack. */
  sameGov(a.gov, b.gov) &&
  (a.scratch ?? null) === (b.scratch ?? null) &&
  (a.sources ?? null) === (b.sources ?? null) &&
  !!a.space === !!b.space &&
  !!a.govFromHome === !!b.govFromHome &&
  a.aux === b.aux &&
  a.breadth === b.breadth &&
  a.primary === b.primary &&
  a.resolution === b.resolution &&
  sameDepth(a.depth, b.depth) &&
  SURFACES.every((s) => a.surfaces[s] === b.surfaces[s])

/** Two governance states are the same when everything either of them puts on
 *  screen is the same. Compared by their written form, because that form is
 *  exactly what a person could send somebody else. */
const sameGov = (a: GovState | null, b: GovState | null): boolean =>
  a === b || (!!a && !!b && govKey(a) === govKey(b))

const govKey = (g: GovState): string =>
  JSON.stringify([g.lens, g.section, g.whole, g.conversationFilter, g.centre, g.item, g.participant, g.filters, [...g.open].sort()])

/** Two contextual stacks are the same when they hold the same layers, in the
 *  same order, on the same things. */
const sameDepth = (a: Layer[], b: Layer[]): boolean =>
  a.length === b.length &&
  a.every((l, i) => {
    const o = b[i]
    if (l.kind !== o.kind) return false
    if (l.kind === 'thread') return l.id === (o as typeof l).id
    if (l.kind === 'media') return l.key === (o as typeof l).key
    if (l.kind === 'entry') return l.id === (o as typeof l).id
    return l.turn === (o as typeof l).turn
  })

/** How a movement treats the stack of places behind it. */
export interface GoOptions {
  /** START AGAIN FROM HERE. The place is still pushed, so the browser's own
   *  Back is untouched — nothing may take that away from anybody — but the
   *  app's own depth returns to zero and its Back control goes quiet. Only a
   *  movement that is a change of ALTITUDE rather than a step uses it: the
   *  whole Brain is not somewhere you went next, it is one above wherever you
   *  were, and I-1 asks for the stack behind it to be reset. */
  fresh?: boolean
}

export interface Nav {
  at: Place
  /** a new place: pushes history, so Back returns to the one before it */
  go: (patch: Patch, opts?: GoOptions) => void
  /** the same place, said differently: no history entry */
  replace: (patch: Patch) => void
  back: () => void
  canBack: boolean
  /** is this surface composed into the workspace right now */
  shows: (s: SurfaceName) => boolean
}

/** COMPARE IS TWO CONVERSATIONS, SO STANDING AT BRAIN IS OUT OF IT.
 *
 *  Compare never lets a half sit at Brain: given a Place in Compare with no
 *  Conversation it put the first one on the rail back into its left half. So
 *  every way to Brain that did not itself say "leave Compare" -- an address
 *  typed or pasted, the app bar's Brain, Back or Forward to an entry made that
 *  way, a reload -- landed in a Conversation, still in Compare, and Back could
 *  not get out (review 4, non-blocking 4). Compare's own way out has always
 *  cleared `compare` with the Conversation; every Place now does. */
const whole = (p: Place): Place => {
  const q = p.compare && p.conversation === null ? { ...p, compare: false } : p
  /* MANAGE SOURCES IS A BRAIN PLACE WITH NO LENS. Any move into a
     Conversation or into Governance leaves it, so coming back to Brain home
     later is Brain home and not Sources reappearing from under it. */
  const r = (q.sources ?? null) !== null && (q.conversation !== null || q.gov)
    ? { ...q, sources: null }
    : q
  /* THE 3D BRAIN IS LEFT THE SAME WAY, and by any move into Manage Sources:
     a move that names Sources does not know the 3D Brain exists. */
  return r.space && (r.conversation !== null || r.gov || (r.sources ?? null) !== null)
    ? { ...r, space: false }
    : r
}

/** The Place this browser is already pointing at, before anything renders.
 *
 *  ORDER MATTERS. `history.state` carries the whole Place, including the
 *  arrangement; the address carries only the scope. On a reload both are
 *  present and agree. On a link opened cold there is only an address, and the
 *  arrangement starts from HOME. Reading state first and letting the address
 *  correct the scope covers both without either having to know about the
 *  other. */
function arriving(): Place {
  let base = HOME
  try {
    const s = (window.history.state ?? {}) as { mentis?: Place }
    if (s.mentis) base = { ...s.mentis, from: null }
  } catch {
    /* a browser that will not give us history state simply has none */
  }
  const a = readAddress()
  if (isBlank(a)) return whole(base)
  return whole({
    ...base,
    conversation: a.brain ? null : a.conversation,
    topic: a.topic,
    turn: a.turn,
    gov: a.gov,
    scratch: a.brain ? a.scratch : (base.scratch ?? null),
    sources: a.sources,
    space: a.space,
    // Arriving at a scope is arriving at the scope, not at whatever was
    // stacked over it when somebody last left.
    depth: a.turn ? base.depth : [],
    from: null,
  })
}

/** WHERE GOVERNANCE WAS ENTERED FROM, decided by the move and not by
 *  whoever asked for it, so every door off Main -- its rows, its Governance
 *  door, the app bar's Asks, the brand menu -- says the same thing. */
export function entered(was: Place, next: Place): Place {
  const fromHome =
    next.gov === null || next.conversation !== null
      ? false
      : was.gov === null && was.conversation === null
        ? true
        : !!was.govFromHome
  return fromHome === !!next.govFromHome ? next : { ...next, govFromHome: fromHome }
}

export function useNavigation(): Nav {
  /* NOT `HOME`. Initialising to HOME and then overwriting `history.state`
     with it -- which is what happened here -- threw away the restored Place
     before anything could read it, and every refresh landed somewhere else. */
  const [at, setAt] = useState<Place>(arriving)
  const [depth, setDepth] = useState(0)
  const here = useRef(at)
  here.current = at
  const level = useRef(0)
  level.current = depth

  useEffect(() => {
    // The session's own first entry, so that popping back to it is a place
    // rather than an empty state.
    window.history.replaceState({ mentis: here.current, depth: 0, ...carried() }, '')
    const onPop = (e: PopStateEvent) => {
      const s = (e.state ?? {}) as { mentis?: Place; depth?: number }
      if (!s.mentis) return
      setAt(whole({ ...s.mentis, from: 'shell' }))
      setDepth(s.depth ?? 0)
      showAddress(addressOf(s.mentis))
    }
    /* AN ADDRESS TYPED OR PASTED IN IS A NAVIGATION. Without this the bar
       could be edited and nothing would move: the address would be
       readable-on-load but not actually addressable, which is most of the
       point of putting it there. `showAddress` uses replaceState and so
       never fires this; only a real change to the bar does. */
    const onHash = () => {
      const a = readAddress()
      const now = here.current
      if (a.conversation === now.conversation && a.topic === now.topic &&
          a.turn === now.turn && sameGov(a.gov, now.gov) &&
          a.sources === (now.sources ?? null) &&
          a.space === !!now.space &&
          (!a.brain || a.scratch === (now.scratch ?? null))) return
      setAt(entered(now, whole({
        ...now,
        conversation: a.brain ? null : a.conversation,
        topic: a.topic,
        turn: a.turn,
        gov: a.gov,
        scratch: a.brain ? a.scratch : (now.scratch ?? null),
        sources: a.sources,
        space: a.space,
        depth: a.turn ? now.depth : [],
        from: 'shell',
      })))
    }
    window.addEventListener('popstate', onPop)
    window.addEventListener('hashchange', onHash)
    return () => {
      window.removeEventListener('popstate', onPop)
      window.removeEventListener('hashchange', onHash)
    }
  }, [])

  const merge = (patch: Patch): Place =>
    entered(
      here.current,
      whole({
        ...here.current,
        ...patch,
        surfaces: patch.surfaces
          ? { ...here.current.surfaces, ...patch.surfaces }
          : here.current.surfaces,
      }),
    )

  /* TWO MOVES IN ONE GESTURE COMPOSE. `here` is refreshed by the render,
     so without this a second `go` in the same tick merged into the place as
     it was BEFORE the first and quietly undid it. Choosing a Topic in the
     navigator's sheet is exactly that -- focus the Topic, then close the
     sheet -- and the second move put the Conversation back on All while
     the navigator had shown the Topic chosen. Compare's picker (select,
     clear the Turn, clear the thread) lost its selection the same way. The
     place a move produced is where the next move starts. */
  const go = useCallback((patch: Patch, opts?: GoOptions) => {
    const next = merge(patch)
    if (same(next, here.current)) {
      // Nothing moved — only who asked. No history entry for that.
      if (next.from !== here.current.from) {
        here.current = next
        setAt(next)
      }
      return
    }
    here.current = next
    const d = opts?.fresh ? 0 : level.current + 1
    window.history.pushState({ mentis: next, depth: d, ...(opts?.fresh ? {} : carried()) }, '')
    showAddress(addressOf(next))
    setAt(next)
    setDepth(d)
  }, [])

  const replace = useCallback((patch: Patch) => {
    const next = merge(patch)
    here.current = next
    window.history.replaceState({ mentis: next, depth: level.current, ...carried() }, '')
    showAddress(addressOf(next))
    setAt(next)
  }, [])

  const back = useCallback(() => {
    if (level.current > 0) window.history.back()
  }, [])

  return useMemo<Nav>(
    () => ({
      at,
      go,
      replace,
      back,
      canBack: depth > 0,
      /* ONE DERIVATION, SO TWO CONTROLS CANNOT DISAGREE ABOUT WHAT IS ON
         SCREEN. Thread, Media and Details are on screen when they are on the
         contextual stack; Graph and History are the two expanded resolutions
         of the operational history. Only the rail and the topic rail are
         still independent switches, because they genuinely are. */
      shows: (s) =>
        s === 'thread' || s === 'details'
          ? holds(at.depth, s)
          : s === 'media'
            ? at.primary === 'media' || holds(at.depth, 'media')
            : s === 'graph'
              ? at.resolution === 'structure' || at.primary === 'graph'
              : s === 'history'
                ? at.resolution === 'explanation'
                : at.surfaces[s],
    }),
    [at, depth, go, replace, back],
  )
}

/* ------------------------------------------------------------------------ *
 * "TAKE ME THERE", SAID OUT LOUD. A person choosing to go to a Turn is a
 * different event from the page rereading the record, and a surface that
 * folded something away (a findings group the person closed) must tell them
 * apart: a reread respects the fold, a "go to it" undoes it. Selecting the
 * same Turn twice changes no address, so the choice is announced.
 * ------------------------------------------------------------------------ */
export const GOTO_EVENT = 'mentis:goto'

export function announceGoTo(turn: string): void {
  window.dispatchEvent(new CustomEvent<string>(GOTO_EVENT, { detail: turn }))
}

/* ------------------------------------------------------------------------ *
 * MAIN'S RETURN CONTEXT, KEPT WHERE BACK CAN FIND IT.
 *
 * Leaving Main for the place behind an item and coming back has to land on
 * Main where it was, with the item that was opened indicated (D-5). That is
 * where the owner was LOOKING, so it is UI state like every Place: it lives in
 * `history.state` beside the Place, and nowhere else -- no storage, no
 * request, no record. A reload may lose it, and that is allowed.
 *
 * It is written onto Main's own entry while Main is on screen, so the
 * browser's Back pops straight to it. It is also CARRIED FORWARD onto every
 * entry pushed after it, because some ways back to Main are a step forward
 * rather than a pop -- Governance's "Back to Brain home" pushes Main again --
 * and those must land in the same place too. A `fresh` move (the app bar's
 * Brain, a change of altitude) starts again, so it carries nothing.
 * ------------------------------------------------------------------------ */

export interface HomeReturn {
  /** `.brain-inner`'s scrollTop when it was left */
  scroll: number
  /** the `data-home-item` of what was opened from Main, or null */
  item: string | null
  /** where that item sat in the viewport, so it can be put back there even if
   *  rows above it arrive at a different height */
  offset: number | null
}

const KEPT = 'home'

function carried(): { home?: HomeReturn } {
  try {
    const h = (window.history.state ?? {})[KEPT] as HomeReturn | undefined
    return h ? { [KEPT]: h } : {}
  } catch {
    return {}
  }
}

/** The return context the current history entry carries, if any. */
export function homeReturn(): HomeReturn | null {
  return carried().home ?? null
}

/** Write Main's return context onto the current entry. Only while the entry
 *  IS Main: a late write must never land on the place that was opened. The
 *  address says so, and is always current -- `go` writes it in the same
 *  breath as it pushes -- where the entry's state may not be: an address
 *  typed into the bar makes an entry with none. */
export function keepHome(h: HomeReturn): void {
  try {
    const a = readAddress()
    if (a.conversation !== null || a.gov || a.sources !== null || a.space) return
    window.history.replaceState({ ...(window.history.state ?? {}), [KEPT]: h }, '')
  } catch {
    /* a browser that will not keep history state keeps no return context */
  }
}
