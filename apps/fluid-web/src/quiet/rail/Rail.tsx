/* Track 2: bounded topic navigation; public rail props stay unchanged.
 *
 * ROUND 4 (Track C) adds a FOURTH READING: what the posts carry. The margin
 * already held the conversation's topics, its brief, and the runs with the
 * decisions accordion under them; beside those it now presents each post's
 * rendered blocks, its media and its annotations as small windows
 * (`margin/Margin.tsx`), which is what the concept's margins are for.
 *
 * HOW THAT READING IS CHOSEN. By its own control, like the other three -- and
 * by anything that asks to be read there. An annotation's icon in a post's
 * gutter collects the annotation into the margin (`margin/carried.ts`
 * `present`), which means switching the reading; `useRail` is the one place
 * that can, so it watches the store's ask rather than the margin reaching
 * for the shell's state.
 *
 * ROUND 5 (package M) adds WHAT SURVIVES. Which of the four was open
 * (including closed), the topic-query box's visibility and text, and how far
 * each reading was scrolled, all live in S's bookmark envelope under this
 * Page's `ReadingBookmark.margin` -- read through S's `useWorkspaceBookmark`
 * from the provider R mounts above `useRail`/`Rail` (F4): no new prop, and a
 * `useRail()` called where no provider is mounted stays memory-only rather
 * than resuming anything. M writes the WHOLE reading back, carrying R's half
 * of it (`flow`/`thread`) through untouched -- the mirror of how
 * `reader/ConversationReader.tsx` carries this module's margin through ITS
 * own writes. An annotation's `present` still deliberately switches the
 * reading to Carried and that choice is kept; RESTORING a saved `carried`
 * reading calls neither `present` nor anything in `margin/carried.ts`, so
 * putting a bookmark back never raises a fresh "look at this" request of its
 * own. */
import { useEffect, useRef, useState } from 'react'
import type { Conversation, Id } from '../../api'
import type { RailName } from '../contract'
import ActivityPanel from '../activity/ActivityPanel'
import Decisions from '../activity/Decisions'
import Margin from '../margin/Margin'
import { useAsked } from '../margin/carried'
import { useQuietHref } from '../reader/navigation'
import { useWorkspaceBookmark } from '../workspace/bookmarks'
import type { ReadingBookmark, ReadingFlow, ReadingMargin } from '../workspace/types'
import { markMetrics } from './marks'
import './rail.css'

const READINGS = ['topics', 'brief', 'activity', 'carried'] as const
const titled = (rail: RailName) => rail[0].toUpperCase() + rail.slice(1)

/** A flow nobody has read yet. M writes the whole reading, so a bookmark with
 *  no flow of its own yet (nothing from R to carry through) stays empty
 *  rather than inventing one. */
const NO_FLOW: ReadingFlow = { topic: null, batch: {}, anchor: null }

export const emptyMargin = (): ReadingMargin =>
  ({ reading: null, searchOpen: false, query: '', scrollByReading: {} })

/** M writes the whole reading back, carrying R's half of it (`flow`/
 *  `thread`) through exactly as it finds them -- the mirror of
 *  `ConversationReader.tsx`'s `NO_MARGIN`, which does the same for this
 *  module's half when R writes. Exported for the unit suite, which checks
 *  this carry-through without a browser. */
export function withMargin(stored: ReadingBookmark | null | undefined, margin: ReadingMargin): ReadingBookmark {
  return { flow: stored?.flow ?? NO_FLOW, thread: stored?.thread ?? null, margin }
}

/** Which reading the margin shows. Starts on Topics, as it always has; moves
 *  to Carried when something in a post asks to be read there; otherwise
 *  resumes what this browser remembers for this Page once the question of
 *  whether anything is being restored at all has been answered (`restoring`)
 *  -- the same gate R's own capture waits on, so this never records the
 *  default over a place somebody left before the Brain was known. */
export function useRail() {
  const bookmark = useWorkspaceBookmark()
  const page = bookmark?.page ?? null
  const restoring = bookmark?.restoring ?? false
  const stored = page ? bookmark?.envelope.readings[page] ?? null : null
  const asked = useAsked()

  const [rail, setRail] = useState<RailName | null>('topics')
  const restoredRef = useRef(false)
  const justRestored = useRef(false)
  const storedRef = useRef(stored)
  storedRef.current = stored

  /* ADOPTED ONCE, and only once restoration has been decided one way or the
   *  other -- never before, which is what keeps a Brain that is still
   *  resolving from being recorded over by the default. */
  useEffect(() => {
    if (restoredRef.current || restoring) return
    restoredRef.current = true
    if (stored) {
      justRestored.current = true
      setRail(stored.margin.reading)
    }
  }, [restoring, stored])

  useEffect(() => { if (asked) setRail('carried') }, [asked])

  const patch = bookmark?.patch
  useEffect(() => {
    /* The render that just adopted a restored value writes nothing: it is
     *  already what storage holds, and writing it again here would race the
     *  still-stale closure this same effect flush was scheduled with. */
    if (justRestored.current) { justRestored.current = false; return }
    if (!patch || !page || restoring || !restoredRef.current) return
    const now = storedRef.current
    patch({ readings: { [page]: withMargin(now, { ...(now?.margin ?? emptyMargin()), reading: rail }) } })
  }, [rail, patch, page, restoring])

  return { rail, setRail }
}

export function RailTools({ rail, choose }: {
  rail: RailName | null; choose: (rail: RailName | null) => void
}) {
  return <nav className="qc-rail-tools" aria-label="Conversation tools">{READINGS.map((item) =>
    <button key={item} aria-expanded={rail === item} aria-controls="qc-margin"
      onClick={() => choose(rail === item ? null : item)}>{titled(item)}</button>)}</nav>
}

export default function Rail({ rail, close, conversation, topic, facts }: {
  rail: RailName; close: () => void; conversation: Id; topic: Id | null; facts: Conversation | null
}) {
  const topics = facts?.topics ?? []
  const quietHref = useQuietHref()
  const bookmark = useWorkspaceBookmark()
  const page = bookmark?.page ?? null
  const restoring = bookmark?.restoring ?? false
  const stored = page ? bookmark?.envelope.readings[page] ?? null : null
  const storedRef = useRef(stored)
  storedRef.current = stored

  const [searching, setSearching] = useState(false)
  const [query, setQuery] = useState('')
  /* Opening the find box by the reader's own hand is the only thing that
   *  steals focus into it; a box that opened because this is what was
   *  remembered does not (no auto-focus of a restored query). */
  const [autoFocusSearch, setAutoFocusSearch] = useState(false)
  const searchButton = useRef<HTMLButtonElement>(null)
  const viewport = useRef<HTMLElement>(null)
  const filtered = topics.filter((t) => (t.name + ' ' + t.about).toLowerCase().includes(query.trim().toLowerCase()))
  const busiest = Math.max(0, ...topics.map((t) => t.turns))

  /* ADOPTED ONCE restoration has been decided one way or the other -- NOT a
   *  lazy initial state, because Rail can already be mounted (showing the
   *  default Topics reading) before the bookmark's identity has resolved at
   *  all; seeding from whatever `stored` happened to be at that premature
   *  mount would freeze on the wrong default and, once restoration settles,
   *  the write below would carry that frozen default back over what this
   *  browser actually remembered. */
  const restoredSearchRef = useRef(false)
  const justRestoredSearch = useRef(false)
  useEffect(() => {
    if (restoredSearchRef.current || restoring) return
    restoredSearchRef.current = true
    const m = storedRef.current?.margin
    if (m) {
      justRestoredSearch.current = true
      setSearching(m.searchOpen)
      setQuery(m.query)
    }
  }, [restoring])

  /* WRITE THE SEARCH BOX'S STATE, carrying everything else -- the reading
   *  itself and every reading's scroll position -- through untouched. */
  const patch = bookmark?.patch
  useEffect(() => {
    if (justRestoredSearch.current) { justRestoredSearch.current = false; return }
    if (!patch || !page || restoring || !restoredSearchRef.current) return
    const now = storedRef.current
    patch({ readings: { [page]: withMargin(now, {
      ...(now?.margin ?? emptyMargin()), reading: rail, searchOpen: searching, query,
    }) } }, { coalesce: true })
  }, [searching, query, patch, page, restoring, rail])

  /* PUT THIS READING'S SCROLL BACK, each time the reading shown changes --
   *  on the first open and on switching back to one already visited in this
   *  session -- rather than leaving whatever the previous reading's content
   *  happened to leave the box scrolled to.
   *
   *  A READING THAT FETCHES (Activity's runs and decisions) MAY STILL BE TOO
   *  SHORT TO HOLD THE TARGET the moment this runs -- an assignment past the
   *  current scroll range clamps to whatever is scrollable NOW, which is not
   *  "the reader took over" -- so the target is reapplied as the box keeps
   *  growing, for a bounded window, rather than trusted on the first try. */
  useEffect(() => {
    const el = viewport.current
    if (!el) return
    const target = storedRef.current?.margin.scrollByReading[rail] ?? 0
    el.scrollTop = target
    if (!target || typeof ResizeObserver === 'undefined') return
    const watch = new ResizeObserver(() => { el.scrollTop = target })
    watch.observe(el)
    const stop = setTimeout(() => watch.disconnect(), 1500)
    return () => { watch.disconnect(); clearTimeout(stop) }
  }, [rail])

  /* REMEMBER THIS READING'S SCROLL, coalesced like every other scroll write
   *  in this round; the map keeps every OTHER reading's entry as it was. */
  useEffect(() => {
    const el = viewport.current
    if (!el || !patch || !page) return
    const scrolled = () => {
      const now = storedRef.current
      patch({ readings: { [page]: withMargin(now, {
        ...(now?.margin ?? emptyMargin()), reading: rail,
        scrollByReading: { ...(now?.margin.scrollByReading ?? {}), [rail]: el.scrollTop },
      }) } }, { coalesce: true })
    }
    el.addEventListener('scroll', scrolled, { passive: true })
    return () => el.removeEventListener('scroll', scrolled)
  }, [patch, page, rail])

  return <aside id="qc-margin" className="qc-margin" aria-label={rail} ref={viewport}>
    <div className="qc-rail-heading"><h2>{titled(rail)}</h2>
      <button aria-label="Close margin" onClick={close}>×</button></div>
    {rail === 'topics' && <nav className="qc-topics" aria-label="Topics">
      <div className="qc-topic-tools">
        <a className="qc-topic-all" href={quietHref(conversation)} aria-current={!topic ? 'page' : undefined}><span>All posts</span></a>
        <button ref={searchButton} aria-label="Find a topic" aria-expanded={searching} aria-controls="qc-topic-query"
          onClick={() => {
            const next = !searching
            setSearching(next)
            setQuery('')
            setAutoFocusSearch(next)
          }}>⌕</button>
      </div>
      {searching && <input id="qc-topic-query" type="search" autoFocus={autoFocusSearch} aria-label="Find a topic" placeholder="Filter topics…"
        value={query} onChange={(e) => setQuery(e.target.value)} onKeyDown={(e) => {
          if (e.key === 'Escape') { setSearching(false); setQuery(''); setAutoFocusSearch(false); searchButton.current?.focus() }
        }} />}
      {/* TEXT-FREE, so recency and busyness read as shape before anyone reads
          a name: each mark's thickness and length come from its own turn
          count against the busiest topic shown beside it, and the selected
          topic's mark carries a further, computed emphasis on top of that --
          not only the colour `[aria-current='page']` already paints. The name
          stays the mark's accessible name and its hover-revealed label, so a
          reader who wants it still gets it. */}
      {!!topics.length && <ul className="qc-topic-marks">
        {filtered.map((t) => {
          const metrics = markMetrics(t.turns, busiest, t.id === topic)
          return <li key={t.id}>
            <a className="qc-topic-mark" href={quietHref(conversation, t.id)}
              aria-current={t.id === topic ? 'page' : undefined}
              aria-label={t.about ? `${t.name} — ${t.about}` : t.name}
              title={`${t.name} · ${t.turns} posts${t.about ? ` — ${t.about}` : ''}`}
              style={{ '--qc-mark-thickness': `${metrics.thickness}px`, '--qc-mark-length': `${metrics.length}px` } as React.CSSProperties}>
              <span className="qc-topic-bar" aria-hidden="true" />
              <span className="qc-topic-label">{t.name}</span>
            </a>
          </li>
        })}
      </ul>}
      {facts && !topics.length && <p>No topics in this conversation yet.</p>}
      {!!topics.length && !filtered.length && <p>No matching topics.</p>}
    </nav>}
    {rail === 'brief' && <><p>{facts?.about || 'This conversation has no description.'}</p>
      <h3>People here</h3><p>{facts?.participants.map((p) => p.alias).join(', ')}</p></>}
    {rail === 'activity' && <>
      <ActivityPanel conversation={conversation} topic={topic} />
      <Decisions conversation={conversation} topic={topic} />
    </>}
    {/* ALONGSIDE THE DECISION ACCORDIONS, as the request asks: what the posts
        carry is presented BESIDE the margin's existing controls, not instead
        of them. An outstanding decision is the one thing in the margin that
        is owed rather than offered, so it stays reachable in this reading
        too -- under the boxes, where Activity also puts it. */}
    {rail === 'carried' && <>
      <Margin />
      <Decisions conversation={conversation} topic={topic} />
    </>}
  </aside>
}
