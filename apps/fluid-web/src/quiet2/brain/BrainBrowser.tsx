/* THE BRAIN BROWSER (Manage Brain, round 2): the rail's Brain icon opens
 * this card — the conversation list's own form (DESIGN-r2.md, "Navigation"
 * §2), turned to the Brain's records instead of conversations.
 *
 *   Brain                                  ×
 *   [ Find in the Brain                   ]
 *   Knowledge  Governing  Needs you 2  All
 *   Kind · Ladder status · plain words        one line, compact
 *
 * Narrower than 760px (quiet2.css's own phone breakpoint) it is a bottom
 * sheet over the conversation instead (§6): the same markup, repositioned
 * by brain.css alone.
 *
 * "Needs you" is a read-only view of the same owner asks the global dock
 * already lists (§5): its count is read the one way this card can, through
 * `fetchBrainList('needs-you', '')`, never a second decision path.
 *
 * A row's click calls `onOpenRecord`. Where the record opens next, and what
 * Back does, is Workstream B's (the record view) and integration's own
 * wiring — this card only asks for it; until then the click does nothing
 * visible, which is expected on this branch. */
import { useEffect, useRef, useState } from 'react'
import { fetchBrainList, type BrainFilter, type BrainRecordSummary } from './data'
import './brain.css'

const TABS: { id: BrainFilter; label: string }[] = [
  { id: 'knowledge', label: 'Knowledge' },
  { id: 'governing', label: 'Governing' },
  { id: 'needs-you', label: 'Needs you' },
  { id: 'all', label: 'All' },
]

/** The Ladder word and the short plain words a compact row shows beside the
 *  Kind (DESIGN-r2.md, "The record, at rest"): read from what
 *  `fetchBrainList` already gives a record, not a second status enum of
 *  its own. A hypothesis still recorded reads "not settled", as the table
 *  has it, rather than the general "recorded" wording. */
export function compactStanding(r: BrainRecordSummary): { status: string; words: string; off: boolean } {
  const status = r.standingLabel.split('·')[0]?.trim() || 'Recorded'
  const words = /^hypothesis$/i.test(r.kind) ? 'not settled'
    : status === 'Adopted' ? 'in effect'
    : status === 'Adoption requested' ? 'not in effect'
    : status === 'Superseded' ? 'replaced'
    : status === 'Adoption declined' ? 'declined'
    : status === 'Ended' || status === 'Retired' ? 'ended'
    : 'not in effect'
  const off = status === 'Superseded' || status === 'Ended' || status === 'Retired' || status === 'Adoption declined'
  return { status, words, off }
}

const kindWords = (k: string) => (k ? k.charAt(0).toUpperCase() + k.slice(1) : 'Record')

export default function BrainBrowser({ open, filter, query, onFilterChange, onQueryChange, onClose, onOpenRecord }: {
  open: boolean
  filter: BrainFilter
  query: string
  onFilterChange: (f: BrainFilter) => void
  onQueryChange: (q: string) => void
  onClose: () => void
  /** a row was asked for: where it opens next is Workstream B's + integration's */
  onOpenRecord: (id: string, summary: BrainRecordSummary) => void
}) {
  const [rows, setRows] = useState<BrainRecordSummary[] | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [needsYou, setNeedsYou] = useState<number | null>(null)
  const box = useRef<HTMLDivElement>(null)
  const input = useRef<HTMLInputElement>(null)
  const asked = useRef('')

  /* the tab's rows: at once for a tab, a moment after typing stops — the
     conversation list's own filter does the same (ConversationList.tsx) */
  useEffect(() => {
    if (!open) return
    const words = query.trim()
    const key = `${filter}\u0000${words}`
    const t = window.setTimeout(() => {
      asked.current = key
      setBusy(true); setError(null)
      fetchBrainList(filter, words).then((got) => {
        if (asked.current !== key) return
        setRows(got)
      }, (e: unknown) => { if (asked.current === key) setError(e instanceof Error ? e.message : String(e)) })
        .finally(() => { if (asked.current === key) setBusy(false) })
    }, words ? 180 : 0)
    return () => clearTimeout(t)
  }, [open, filter, query])

  /* "Needs you" keeps its own count on every tab, not only while it is
     shown, the way the global dock's own badge does */
  useEffect(() => {
    if (!open) return
    let gone = false
    fetchBrainList('needs-you', '').then((got) => { if (!gone) setNeedsYou(got.length) }, () => { if (!gone) setNeedsYou(null) })
    return () => { gone = true }
  }, [open])

  useEffect(() => { if (open) requestAnimationFrame(() => input.current?.focus()) }, [open])

  if (!open) return null

  return (
    <div className="q2-brain-veil" onPointerDown={(e) => { if (e.target === e.currentTarget) onClose() }}>
      <div ref={box} className="q2-brain-card" role="dialog" aria-modal="true" aria-label="Brain"
        onKeyDown={(e) => { if (e.key === 'Escape') { e.preventDefault(); onClose() } }}>
        <div className="q2-cl">
          <header className="q2-cl-head">
            <h2>Brain</h2>
            <button type="button" className="q2-cl-close" aria-label="Close" title="Close" onClick={onClose}>×</button>
          </header>
          <input ref={input} type="search" className="q2-cl-filter" value={query} placeholder="Find in the Brain"
            autoComplete="off" spellCheck={false} aria-label="Find in the Brain"
            onChange={(e) => onQueryChange(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Escape' && query) { e.preventDefault(); e.stopPropagation(); onQueryChange('') } }} />
          <div className="q2-cl-tabs" role="tablist" aria-label="Which records"
            onKeyDown={(e) => {
              if (e.key !== 'ArrowRight' && e.key !== 'ArrowLeft') return
              e.preventDefault()
              const i = TABS.findIndex((t) => t.id === filter)
              const n = TABS[(i + (e.key === 'ArrowRight' ? 1 : TABS.length - 1)) % TABS.length].id
              onFilterChange(n)
              requestAnimationFrame(() => box.current?.querySelector<HTMLElement>(`[data-tab="${n}"]`)?.focus())
            }}>
            {TABS.map((t) => (
              <button key={t.id} type="button" role="tab" data-tab={t.id} aria-selected={filter === t.id} tabIndex={filter === t.id ? 0 : -1}
                onClick={() => onFilterChange(t.id)}>
                {t.label}{t.id === 'needs-you' && !!needsYou && <span className="q2-brain-tabcount">{needsYou}</span>}
              </button>
            ))}
          </div>
          <ul className="q2-brain-rows" role="list" aria-busy={busy || undefined}>
            {(rows ?? []).map((r) => {
              const { status, words, off } = compactStanding(r)
              return (
                <li key={r.id}>
                  <button type="button" className="q2-brain-row" onClick={() => onOpenRecord(r.id, r)}>
                    <span className="q2-brain-text">
                      <span className="q2-brain-name">{r.text}</span>
                      <span className={'q2-brain-meta' + (off ? ' q2-brain-off' : '')}>
                        {kindWords(r.kind)} · {status} · {words}
                        {r.challenged && <span className="q2-brain-ask"> · challenged</span>}
                      </span>
                    </span>
                  </button>
                </li>
              )
            })}
            {rows && !rows.length && !busy && !error && <li className="q2-cl-note">Nothing here yet.</li>}
            {rows && !rows.length && busy && !error && <li className="q2-cl-note">Reading…</li>}
            {!rows && !error && <li className="q2-cl-note">Reading the Brain…</li>}
            {error && <li className="q2-cl-note" role="alert">Could not read the Brain: {error}</li>}
          </ul>
          {!!rows?.length && <p className="q2-brain-foot">{rows.length} {rows.length === 1 ? 'record' : 'records'} · newest first</p>}
        </div>
      </div>
    </div>
  )
}
