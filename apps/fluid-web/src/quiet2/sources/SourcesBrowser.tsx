/* THE SOURCES BROWSER (Manage Sources in Quiet Chat): the rail's data-store
 * icon opens this card. It is the Brain browser's own card (brain.css:
 * `.q2-brain-veil`, `.q2-brain-card`, `.q2-cl`), turned to the Brain's
 * sources: the same search line, tabs, narrowing selects and compact rows,
 * the same bottom sheet on a phone, the same room taken beside the reading
 * column.
 *
 *   Sources                              +  ×
 *   [ Find a source                        ]
 *   All  Connected here  Not connected  Needs attention 1
 *   Any kind ▾   Refreshed most recently ▾
 *   Name                               KIND
 *   ● Connected here · 866 files · refreshed Nov 14
 *   + Add a source…
 *   7 sources · 4 connected on this machine · 569 MB held
 *
 * IT READS WHAT THE SOURCE SYSTEM ANSWERS (`/api/sources`) and decides
 * nothing itself (words.ts). The list is small and read whole, so search,
 * tabs, kind and order narrow it here; there is nothing to page.
 *
 * IT STAYS AS IT WAS LEFT: kept while closed, so Back from a source finds
 * the words searched for, the tab, the order and the place scrolled to. */
import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import type { Id } from '../../api'
import type { SourcesAnswer } from '../../surfaces/sources/route'
import { TABS, attentionCount, footWords, listed, standing, type SourceOrder, type SourceTab } from './words'
import '../brain/brain.css'
import './sources.css'

export default function SourcesBrowser({ open, data, error, current, canWrite, onClose, onOpenSource, onAdd, said }: {
  open: boolean
  /** something the page has to say while this card is what is shown (an
   *  address that could not be taken as written): drawn INSIDE the card, so
   *  its Dismiss is within the card's own Tab order */
  said?: React.ReactNode
  /** every source, read by whoever keeps this card (Quiet2), so the card and
   *  the page beside it never disagree */
  data: SourcesAnswer | null
  error: string | null
  /** the source last opened from here: marked, so Back shows where you were */
  current: Id | null
  canWrite: boolean
  onClose: () => void
  onOpenSource: (col: Id) => void
  onAdd: () => void
}) {
  const [q, setQ] = useState('')
  const [tab, setTab] = useState<SourceTab>('all')
  const [kind, setKind] = useState('')
  const [order, setOrder] = useState<SourceOrder>('recent')
  const box = useRef<HTMLDivElement>(null)
  const list = useRef<HTMLUListElement>(null)
  const input = useRef<HTMLInputElement>(null)
  const scrolled = useRef(0)
  const opener = useRef<HTMLElement | null>(null)

  const all = data?.collections ?? []
  const label = (connector: string) => data?.descriptors.find((d) => d.id === connector)?.label ?? connector
  const rows = listed(all, { q, tab, kind, order }, label)
  const kinds = [...new Set(all.map((c) => c.connector))].sort((a, b) => label(a).localeCompare(label(b)))
  const attention = attentionCount(all)

  /* opened: the search line, the list where it was left. Closed: focus goes
     back to what opened it. (BrainBrowser.tsx, the same rule.) */
  useLayoutEffect(() => {
    if (open) {
      opener.current = document.activeElement instanceof HTMLElement ? document.activeElement : null
      if (list.current) list.current.scrollTop = scrolled.current
      requestAnimationFrame(() => input.current?.focus({ preventScroll: true }))
    } else {
      const to = opener.current
      opener.current = null
      if (to && document.contains(to) && (!document.activeElement || document.activeElement === document.body || box.current?.contains(document.activeElement))) to.focus({ preventScroll: true })
    }
  }, [open])
  /* rows read after the card opened: the place it was left at is put back once */
  const placed = useRef(false)
  useEffect(() => { if (!open) placed.current = false }, [open])
  useLayoutEffect(() => {
    if (open && data && !placed.current && list.current) { placed.current = true; list.current.scrollTop = scrolled.current }
  }, [open, data])

  /* THE ROOM THE CARD HAS, measured as the Brain browser measures it: from
     its own left edge to the reading column's. brain.css sizes it. */
  useLayoutEffect(() => {
    const card = box.current
    if (!open || !card) return
    const pane = document.querySelector<HTMLElement>('.q2-pane.q2-conv')
    const measure = () => {
      const column = pane?.querySelector<HTMLElement>(':scope > .q2-col:not(.q2-col-brain)')
      const left = card.getBoundingClientRect().left
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

  const keepPlace = () => { if (list.current) scrolled.current = list.current.scrollTop }
  const leave = () => { keepPlace(); onClose() }
  const choose = (t: SourceTab) => { scrolled.current = 0; setTab(t) }

  /* Tab stays inside the card while it is open: it is a dialog */
  const trap = (e: React.KeyboardEvent) => {
    if (e.key === 'Escape') { e.preventDefault(); leave(); return }
    if (e.key !== 'Tab' || !box.current) return
    const stops = [...box.current.querySelectorAll<HTMLElement>('button:not([disabled]):not([tabindex="-1"]), input, select, [href]')].filter((el) => el.offsetParent !== null)
    if (!stops.length) return
    const first = stops[0], last = stops[stops.length - 1]
    if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus() }
    else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus() }
  }

  return (
    <div className="q2-brain-veil q2-src-veil" hidden={!open} onPointerDown={(e) => { if (e.target === e.currentTarget) leave() }}>
      <div ref={box} className="q2-brain-card q2-src-card" role="dialog" aria-modal="true" aria-label="Sources" onKeyDown={trap}>
        <div className="q2-cl">
          <header className="q2-cl-head">
            <h2>Sources</h2>
            <span className="q2-brain-tools">
              {canWrite && <button type="button" className="q2-brain-more" aria-label="Add a source" title="Add a source" onClick={() => { keepPlace(); onAdd() }}>+</button>}
              <button type="button" className="q2-cl-close" aria-label="Close" title="Close" onClick={leave}>×</button>
            </span>
          </header>
          {said}
          <input ref={input} type="search" className="q2-cl-filter" value={q} placeholder="Find a source"
            autoComplete="off" spellCheck={false} aria-label="Find a source"
            onChange={(e) => { scrolled.current = 0; setQ(e.target.value) }}
            onKeyDown={(e) => { if (e.key === 'Escape' && q) { e.preventDefault(); e.stopPropagation(); setQ('') } }} />
          <div className="q2-cl-tabs" role="tablist" aria-label="Which sources"
            onKeyDown={(e) => {
              if (e.key !== 'ArrowRight' && e.key !== 'ArrowLeft') return
              e.preventDefault()
              const i = TABS.findIndex((t) => t.id === tab)
              const n = TABS[(i + (e.key === 'ArrowRight' ? 1 : TABS.length - 1)) % TABS.length].id
              choose(n)
              requestAnimationFrame(() => box.current?.querySelector<HTMLElement>(`[data-tab="${n}"]`)?.focus())
            }}>
            {TABS.map((t) => (
              <button key={t.id} type="button" role="tab" data-tab={t.id} aria-selected={tab === t.id} tabIndex={tab === t.id ? 0 : -1}
                onClick={() => choose(t.id)}>
                {t.label}{t.id === 'attention' && attention > 0 && <span className="q2-brain-tabcount">{attention}</span>}
              </button>
            ))}
          </div>
          <div className="q2-brain-narrow">
            <select aria-label="Kind of source" value={kind} onChange={(e) => { scrolled.current = 0; setKind(e.target.value) }}>
              <option value="">Any kind</option>
              {kinds.map((k) => <option key={k} value={k}>{label(k)} · {all.filter((c) => c.connector === k).length}</option>)}
            </select>
            <select aria-label="Order" value={order} onChange={(e) => { scrolled.current = 0; setOrder(e.target.value as SourceOrder) }}>
              <option value="recent">Refreshed most recently</option>
              <option value="name">Name</option>
              <option value="size">Largest</option>
            </select>
          </div>
          <ul ref={list} className="q2-brain-rows" role="list" onScroll={(e) => { if (open) scrolled.current = e.currentTarget.scrollTop }}>
            {rows.map((c) => {
              const s = standing(c)
              return (
                <li key={c.collection}>
                  <button type="button" className="q2-brain-row" data-source={c.collection} aria-current={c.collection === current || undefined}
                    onClick={() => { keepPlace(); onOpenSource(c.collection) }}>
                    <span className="q2-brain-text">
                      <span className="q2-src-rowtop"><span className="q2-brain-name">{c.name}</span><span className="q2-src-kind">{label(c.connector).replace(/ (on this machine|file)$/i, '')}</span></span>
                      <span className={'q2-brain-meta q2-src-state q2-src-' + s.tone}>
                        <span className="q2-src-dot" aria-hidden="true" />{s.label} · {s.words}
                      </span>
                    </span>
                  </button>
                </li>
              )
            })}
            {data && !rows.length && (
              <li className="q2-cl-note">{all.length ? 'Nothing matches.' : 'No sources yet. A source is a folder, a Git repository or a database whose contents Mentis keeps a copy of, for every conversation to use.'}</li>
            )}
            {!data && !error && <li className="q2-cl-note" role="status">Reading the sources…</li>}
            {error && !data && <li className="q2-cl-note" role="alert">Could not read the sources: {error}</li>}
          </ul>
          {canWrite && <button type="button" className="q2-src-add" onClick={() => { keepPlace(); onAdd() }}>＋ Add a source…</button>}
          {data && <p className="q2-brain-foot"><span>{footWords(rows.length, all)}</span></p>}
        </div>
      </div>
    </div>
  )
}
