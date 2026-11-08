/* Track B: Topics as a Medium-style floating table of contents -- a small
 * toggle beside the heading, and a card that floats OVER the page when
 * opened. Unlike the working margin (rail/Rail.tsx: Brief/Activity/Carried,
 * unchanged and still a reserved grid column), Topics never reserves layout
 * space, open or closed: `position: fixed` in floatnav.css, no grid cell. */
import { useEffect, useRef, useState } from 'react'
import type { Conversation, Id } from '../../api'
import { href } from '../model'
import { markMetrics } from '../rail/marks'
import './floatnav.css'

export function useTopicsFloat() {
  const [open, setOpen] = useState(false)
  return { open, setOpen }
}

/** The discoverable entry point, kept beside the existing rail tools rather
 *  than inside them: Topics is not one of the working readings any more. */
export function TopicsToggle({ open, setOpen }: { open: boolean; setOpen: (open: boolean) => void }) {
  return <nav className="qc-topics-entry" aria-label="Topics">
    <button type="button" className="qc-topics-toggle" aria-haspopup="dialog"
      aria-expanded={open} aria-controls="qc-topics-float"
      onClick={() => setOpen(!open)}>Topics</button>
  </nav>
}

export default function TopicsFloat({ open, close, conversation, topic, facts }: {
  open: boolean; close: () => void; conversation: Id; topic: Id | null; facts: Conversation | null
}) {
  const topics = facts?.topics ?? []
  const [searching, setSearching] = useState(false)
  const [query, setQuery] = useState('')
  const panel = useRef<HTMLDivElement>(null)
  const searchButton = useRef<HTMLButtonElement>(null)
  const filtered = topics.filter((t) => (t.name + ' ' + t.about).toLowerCase().includes(query.trim().toLowerCase()))
  const busiest = Math.max(0, ...topics.map((t) => t.turns))
  useEffect(() => {
    if (!open) return
    const onPointer = (e: MouseEvent) => {
      if (panel.current && !panel.current.contains(e.target as Node)) close()
    }
    document.addEventListener('mousedown', onPointer)
    return () => document.removeEventListener('mousedown', onPointer)
  }, [open, close])
  if (!open) return null
  return <div id="qc-topics-float" ref={panel} className="qc-topics-float" role="dialog"
    aria-label="Topics" onKeyDown={(e) => {
      if (e.key !== 'Escape' || e.defaultPrevented) return
      e.preventDefault()
      if (searching) { setSearching(false); setQuery(''); searchButton.current?.focus() }
      else close()
    }}>
    <div className="qc-rail-heading"><h2>Topics</h2>
      <button type="button" aria-label="Close topics" onClick={close}>×</button></div>
    <nav className="qc-topics" aria-label="Topics">
      <div className="qc-topic-tools">
        <a className="qc-topic-all" href={href(conversation)} aria-current={!topic ? 'page' : undefined}
          onClick={close}><span>All posts</span></a>
        <button ref={searchButton} aria-label="Find a topic" aria-expanded={searching} aria-controls="qc-topic-query"
          onClick={() => { setSearching(!searching); setQuery('') }}>⌕</button>
      </div>
      {searching && <input id="qc-topic-query" type="search" autoFocus aria-label="Find a topic" placeholder="Filter topics…"
        value={query} onChange={(e) => setQuery(e.target.value)} />}
      {!!topics.length && <ul className="qc-topic-marks">
        {filtered.map((t) => {
          const metrics = markMetrics(t.turns, busiest, t.id === topic)
          return <li key={t.id}>
            <a className="qc-topic-mark" href={href(conversation, t.id)} onClick={close}
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
    </nav>
  </div>
}
