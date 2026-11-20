/* THE BRAIN BROWSER (Manage Brain in Quiet Chat): the rail's Brain icon opens
 * this card -- the conversation list's own form (DESIGN-r2.md, "Navigation"
 * §2), turned to the Brain's records instead of conversations. The rail's
 * dashes stay conversations; this is a card of its own, never a mode of the
 * rail and never a second rail.
 *
 *   Brain                              ⋯  ×
 *   [ Find in the Brain                   ]
 *   Knowledge  Governing  Needs you 2  All
 *   Any kind ▾   Any standing ▾
 *   Kind · Ladder status · plain words        one line, compact
 *   50 of 213 records · newest first   Show more
 *
 * Narrower than 760px (quiet2.css's own phone breakpoint) it is a bottom
 * sheet over the conversation instead (§6): the same markup, repositioned
 * by brain.css alone.
 *
 * IT STAYS AS IT WAS LEFT. The card is kept while it is closed, so coming
 * Back from a record finds the filter, the words searched for, the rows read
 * and the place scrolled to. Only what the record says is re-read.
 *
 * "Needs you" lists the records the owner is asked about by the same rule
 * the global dock's bell uses (§5), resolved on the server; nothing is
 * decided here that is not decided there. */
import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { useApi } from '../../api'
import type { KindAuthoring } from '../../surfaces/governance/r2Model'
import { BRAIN_PAGE, countAdoptionRequested, fetchBrainPage, type BrainFilter, type BrainKind, type BrainRecordSummary } from './data'
import { appendPage, compactStanding, footWords, kindWords } from './logic'
import { useBeat } from './beat'
import { kindChoices } from './author/model'
import BrainOverview from './BrainOverview'
import './brain.css'

const TABS: { id: BrainFilter; label: string }[] = [
  { id: 'knowledge', label: 'Knowledge' },
  { id: 'governing', label: 'Governing' },
  { id: 'needs-you', label: 'Needs you' },
  { id: 'all', label: 'All' },
]

/** The Ladder's standings a list can be narrowed to, in its own words. */
const STANDINGS: { id: string; label: string }[] = [
  { id: 'adopted', label: 'Adopted' },
  { id: 'adoption_requested', label: 'Adoption requested' },
  { id: 'recorded', label: 'Recorded' },
  { id: 'declined', label: 'Adoption declined' },
  { id: 'superseded', label: 'Replaced' },
  { id: 'deleted', label: 'Ended' },
]

export default function BrainBrowser({ open, filter, query, onFilterChange, onQueryChange, onClose, onOpenRecord, onNew, onImport, onPreview, canWrite }: {
  open: boolean
  filter: BrainFilter
  query: string
  onFilterChange: (f: BrainFilter) => void
  onQueryChange: (q: string) => void
  onClose: () => void
  onOpenRecord: (id: string, summary: BrainRecordSummary) => void
  /** authoring: make a record of this Kind's section */
  onNew: (kind: string) => void
  onImport: () => void
  onPreview: () => void
  /** nothing that writes is offered where the page may not write */
  canWrite: boolean
}) {
  /* THE ROWS READ, AND WHAT THEY WERE READ FOR. They are drawn only while
     that is what is asked for now: the render that carries a new filter
     shows no row of the old one, not even for the frame before its effect
     runs (review round 2). */
  const [read, setRead] = useState<{ params: string; rows: BrainRecordSummary[] } | null>(null)
  const [total, setTotal] = useState(0)
  const [past, setPast] = useState(0)
  const [kinds, setKinds] = useState<BrainKind[]>([])
  const [unknown, setUnknown] = useState(false)
  const [busy, setBusy] = useState(false)
  const [more, setMore] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [needsYou, setNeedsYou] = useState<number | null>(null)
  const [requested, setRequested] = useState<number | null>(null)
  const [kind, setKind] = useState('')
  const [status, setStatus] = useState('')
  const [withPast, setWithPast] = useState(false)
  const [menu, setMenu] = useState(false)
  /* the card's second face: what this Brain holds and takes (BrainOverview) */
  const [about, setAbout] = useState(false)
  const aboutBtn = useRef<HTMLButtonElement>(null)
  const leaveAbout = () => { setAbout(false); requestAnimationFrame(() => aboutBtn.current?.focus({ preventScroll: true })) }
  const box = useRef<HTMLDivElement>(null)
  const list = useRef<HTMLUListElement>(null)
  const input = useRef<HTMLInputElement>(null)
  const asked = useRef('')
  const scrolled = useRef(0)
  const opener = useRef<HTMLElement | null>(null)
  /* the record moved (something was adopted, challenged, written): re-read */
  const beat = useBeat()
  const authoring = useApi<{ kinds: KindAuthoring[] }>(open && menu ? '/api/governance/authoring' : null)

  /* a Kind or standing chosen under one tab does not follow to another */
  const view = filter
  const params = `${view}\u0000${query.trim()}\u0000${kind}\u0000${status}\u0000${withPast ? 1 : 0}`

  /* WHAT IS ASKED FOR NOW, known at once (not when its read lands): an answer
     to anything else -- a first page or a "Show more" still on its way when
     the filter changed -- is dropped, never drawn under the new filter */
  const wanted = useRef(params)
  wanted.current = params
  const rows = read && read.params === params ? read.rows : null
  const paging = useRef<AbortController | null>(null)
  /* a "Show more" on its way is given up when the filter changes or the card closes */
  useEffect(() => () => { paging.current?.abort(); paging.current = null; setMore(false) }, [params, open])

  /* the tab's rows: at once for a tab, a moment after typing stops. What was
     read for other filters is cleared first: a row of the last tab is never
     left clickable under the new one (audit finding 9). */
  const shownFor = useRef('')
  useEffect(() => {
    if (!open) return
    const words = query.trim()
    const fresh = shownFor.current !== params
    if (fresh) setError(null)
    const ctl = new AbortController()
    const t = window.setTimeout(() => {
      asked.current = params
      setBusy(true)
      fetchBrainPage({ view, q: words, kind: kind || undefined, status: status || undefined, past: withPast, limit: Math.max(BRAIN_PAGE, fresh ? 0 : rowsRef.current) }, ctl.signal).then((got) => {
        if (asked.current !== params || wanted.current !== params) return
        shownFor.current = params
        setRead({ params, rows: got.items }); setTotal(got.total); setPast(got.past); setKinds(got.kinds); setUnknown(!!got.unknown); setError(null)
      }, (e: unknown) => { if (asked.current === params && wanted.current === params && !ctl.signal.aborted) setError(e instanceof Error ? e.message : String(e)) })
        .finally(() => { if (asked.current === params && wanted.current === params) setBusy(false) })
    }, fresh && words ? 180 : 0)
    return () => { clearTimeout(t); ctl.abort() }
  }, [open, params, beat]) // eslint-disable-line react-hooks/exhaustive-deps
  const rowsRef = useRef(0)
  rowsRef.current = rows?.length ?? 0

  const showMore = () => {
    if (more || !rows || shownFor.current !== params) return
    const at = params
    const ctl = new AbortController()
    paging.current?.abort()
    paging.current = ctl
    const current = () => wanted.current === at && shownFor.current === at && !ctl.signal.aborted
    setMore(true)
    fetchBrainPage({ view, q: query.trim(), kind: kind || undefined, status: status || undefined, past: withPast, offset: rows.length }, ctl.signal).then((got) => {
      if (!current()) return
      setRead((r) => (r && r.params === at ? { params: at, rows: appendPage(r.rows, got.items) } : r)); setTotal(got.total)
    }, (e: unknown) => { if (current()) setError(e instanceof Error ? e.message : String(e)) })
      .finally(() => { if (paging.current === ctl) { paging.current = null; setMore(false) } })
  }

  /* "Needs you" keeps its own count on every tab; and how many adoption
     requests are open at all, so one that never reached the bell is said */
  useEffect(() => {
    if (!open) return
    const ctl = new AbortController()
    fetchBrainPage({ view: 'needs-you', limit: 1 }, ctl.signal).then((got) => setNeedsYou(got.total), () => setNeedsYou(null))
    countAdoptionRequested(ctl.signal).then(setRequested, () => setRequested(null))
    return () => ctl.abort()
  }, [open, beat])

  /* opened: the search line, remembering what opened it; the list where it
     was left. Closed: focus goes back to what opened it. */
  useLayoutEffect(() => {
    if (open) {
      opener.current = document.activeElement instanceof HTMLElement ? document.activeElement : null
      if (list.current) list.current.scrollTop = scrolled.current
      requestAnimationFrame(() => input.current?.focus({ preventScroll: true }))
    } else {
      setMenu(false); setAbout(false)
      const to = opener.current
      opener.current = null
      if (to && document.contains(to) && (!document.activeElement || document.activeElement === document.body || box.current?.contains(document.activeElement))) to.focus({ preventScroll: true })
    }
  }, [open])

  /* THE ROOM THE CARD HAS: from its own left edge to the reading column's,
     measured while it is open and again whenever the conversation's pane
     changes size (a divider dragged, a working column opened, the window
     resized). brain.css sizes the card from it; nothing here sets a width. */
  useLayoutEffect(() => {
    const card = box.current
    if (!open || !card) return
    const pane = document.querySelector<HTMLElement>('.q2-pane.q2-conv')
    const measure = () => {
      const column = pane?.querySelector<HTMLElement>(':scope > .q2-col:not(.q2-col-brain)')
      const left = card.getBoundingClientRect().left
      /* the column's sheet reaches 24px past its box (quiet2.css); the Brain's
         own column fills the pane, so beside it there is no room to take */
      const edge = column ? column.getBoundingClientRect().left - 24 : left
      card.style.setProperty('--q2-brain-room', Math.max(0, Math.floor(edge - left - 12)) + 'px')
    }
    measure()
    const watch = new ResizeObserver(measure)
    if (pane) watch.observe(pane)
    watch.observe(document.documentElement)
    window.addEventListener('resize', measure)
    return () => { watch.disconnect(); window.removeEventListener('resize', measure) }
  }, [open])

  /* where the list is, taken at the moment the card is left (a scroll event
     may not have been delivered yet), so coming back finds the same rows */
  const keepPlace = () => { if (list.current) scrolled.current = list.current.scrollTop }
  const leave = () => { keepPlace(); onClose() }
  const choose = (f: BrainFilter) => { setKind(''); setStatus(''); setWithPast(false); scrolled.current = 0; onFilterChange(f) }

  /* Tab stays inside the card while it is open: it is a dialog */
  const trap = (e: React.KeyboardEvent) => {
    if (e.key === 'Escape') {
      e.preventDefault()
      if (menu) { setMenu(false); return }
      if (about) { leaveAbout(); return }
      leave(); return
    }
    if (e.key !== 'Tab' || !box.current) return
    const stops = [...box.current.querySelectorAll<HTMLElement>('button:not([disabled]):not([tabindex="-1"]), input, select, [href]')].filter((el) => el.offsetParent !== null)
    if (!stops.length) return
    const first = stops[0], last = stops[stops.length - 1]
    if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus() }
    else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus() }
  }

  const choices = kindChoices(authoring.data?.kinds ?? [])
  const notAsked = requested !== null && needsYou !== null ? Math.max(0, requested - needsYou) : 0

  return (
    <div className="q2-brain-veil" hidden={!open} onPointerDown={(e) => { if (e.target === e.currentTarget) leave() }}>
      <div ref={box} className="q2-brain-card" role="dialog" aria-modal="true" aria-label="Brain" onKeyDown={trap}>
        <div className="q2-cl" hidden={about}>
          <header className="q2-cl-head">
            <h2>Brain</h2>
            <span className="q2-brain-tools">
              <button ref={aboutBtn} type="button" className="q2-brain-about" aria-label="About this Brain" title="What this Brain holds and how much room it takes"
                onClick={() => { setMenu(false); setAbout(true) }}>About</button>
              <button type="button" className="q2-brain-more" aria-haspopup="menu" aria-expanded={menu} aria-label="Make, import, preview" title="Make, import, preview"
                onClick={() => setMenu((m) => !m)}>⋯</button>
              {menu && (
                <span className="q2-menu q2-brain-toolmenu" role="menu" aria-label="Brain">
                  {canWrite && <span className="q2-menu-head">New</span>}
                  {canWrite && !authoring.data && !authoring.error && <span className="q2-brain-note">Reading what can be made…</span>}
                  {canWrite && authoring.error && <span className="q2-brain-note" role="alert">Could not read what can be made: {authoring.error}</span>}
                  {canWrite && choices.map((c) => (
                    <button key={c.kind} type="button" role="menuitem" onClick={() => { setMenu(false); onNew(c.kind) }}>{c.label}…</button>
                  ))}
                  {canWrite && <button type="button" role="menuitem" onClick={() => { setMenu(false); onImport() }}>Import an archive…</button>}
                  <button type="button" role="menuitem" onClick={() => { setMenu(false); onPreview() }}>See what an agent will receive…</button>
                </span>
              )}
              <button type="button" className="q2-cl-close" aria-label="Close" title="Close" onClick={leave}>×</button>
            </span>
          </header>
          <input ref={input} type="search" className="q2-cl-filter" value={query} placeholder="Find in the Brain"
            autoComplete="off" spellCheck={false} aria-label="Find in the Brain"
            onChange={(e) => { scrolled.current = 0; onQueryChange(e.target.value) }}
            onKeyDown={(e) => { if (e.key === 'Escape' && query) { e.preventDefault(); e.stopPropagation(); onQueryChange('') } }} />
          <div className="q2-cl-tabs" role="tablist" aria-label="Which records"
            onKeyDown={(e) => {
              if (e.key !== 'ArrowRight' && e.key !== 'ArrowLeft') return
              e.preventDefault()
              const i = TABS.findIndex((t) => t.id === filter)
              const n = TABS[(i + (e.key === 'ArrowRight' ? 1 : TABS.length - 1)) % TABS.length].id
              choose(n)
              requestAnimationFrame(() => box.current?.querySelector<HTMLElement>(`[data-tab="${n}"]`)?.focus())
            }}>
            {TABS.map((t) => (
              <button key={t.id} type="button" role="tab" data-tab={t.id} aria-selected={filter === t.id} tabIndex={filter === t.id ? 0 : -1}
                onClick={() => choose(t.id)}>
                {t.label}{t.id === 'needs-you' && !!needsYou && <span className="q2-brain-tabcount">{needsYou}</span>}
              </button>
            ))}
          </div>
          {filter !== 'needs-you' && (
            <div className="q2-brain-narrow">
              <select aria-label="Kind" value={kind} onChange={(e) => { scrolled.current = 0; setKind(e.target.value) }}>
                <option value="">Any kind</option>
                {kinds.map((k) => <option key={k.kind} value={k.kind}>{kindWords(k.kind)} · {k.count}</option>)}
                {kind && !kinds.some((k) => k.kind === kind) && <option value={kind}>{kindWords(kind)}</option>}
              </select>
              <select aria-label="Standing" value={status} onChange={(e) => { scrolled.current = 0; setStatus(e.target.value) }}>
                <option value="">Any standing</option>
                {STANDINGS.map((s) => <option key={s.id} value={s.id}>{s.label}</option>)}
              </select>
            </div>
          )}
          <ul ref={list} className="q2-brain-rows" role="list" aria-busy={busy || undefined}
            onScroll={(e) => { if (open) scrolled.current = e.currentTarget.scrollTop }}>
            {(rows ?? []).map((r) => {
              const { status: word, words, off } = compactStanding(r)
              return (
                <li key={r.id}>
                  <button type="button" className="q2-brain-row" data-record={r.id} onClick={() => { keepPlace(); onOpenRecord(r.id, r) }}>
                    <span className="q2-brain-text">
                      {/* ONE SENTENCE THAT SAYS WHAT IT IS (owner, 2026-11-16):
                          the record's summary, not its wording cut off. The
                          wording is in the record's own view. */}
                      <span className="q2-brain-name">{r.summary || <i>No words recorded</i>}</span>
                      <span className={'q2-brain-meta' + (off ? ' q2-brain-off' : '')}>
                        {kindWords(r.kind)} · {word} · {words}
                        {r.challenged > 0 && <span className="q2-brain-ask"> · challenged</span>}
                      </span>
                    </span>
                  </button>
                </li>
              )
            })}
            {rows && !rows.length && !busy && !error && (
              <li className="q2-cl-note">
                {unknown ? 'This Brain names no owner, so nothing can be said to ask them.'
                  : filter === 'needs-you' ? 'Nothing in the Brain is waiting on you.'
                    : query.trim() || kind || status ? 'Nothing matches.' : 'Nothing here yet.'}
              </li>
            )}
            {!rows && !error && <li className="q2-cl-note" role="status">Reading the Brain…</li>}
            {error && <li className="q2-cl-note" role="alert">Could not read the Brain: {error}</li>}
            {filter === 'needs-you' && rows && notAsked > 0 && (
              <li className="q2-cl-note q2-brain-aside">
                {notAsked} {notAsked === 1 ? 'record has' : 'records have'} an open adoption request that is not in Needs you now.{' '}
                <button type="button" className="q2-link" onClick={() => { onFilterChange('all'); setKind(''); setWithPast(false); setStatus('adoption_requested') }}>Show {notAsked === 1 ? 'it' : 'them'}</button>
              </li>
            )}
          </ul>
          {!!rows?.length && (
            <p className="q2-brain-foot">
              <span>{footWords(rows.length, total, filter)}</span>
              {rows.length < total && <button type="button" className="q2-link" disabled={more} onClick={showMore}>{more ? 'Reading…' : 'Show more'}</button>}
            </p>
          )}
          {filter !== 'needs-you' && rows && (past > 0 || withPast) && !status && (
            <p className="q2-brain-foot q2-brain-past">
              <label><input type="checkbox" checked={withPast} onChange={(e) => { scrolled.current = 0; setWithPast(e.target.checked) }} /> Include replaced and ended{!withPast && past > 0 ? ` (${past})` : ''}</label>
            </p>
          )}
        </div>
        <BrainOverview open={open && about} onBack={leaveAbout} onClose={leave} />
      </div>
    </div>
  )
}
