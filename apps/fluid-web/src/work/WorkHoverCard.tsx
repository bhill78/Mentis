import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import type { Id } from '../api'
import { useMe } from '../identity'
import { useWorkDetail } from './api'
import type { WorkItem } from './contract'
import StatusWords from './StatusWords'
import './work.css'

export interface WorkHoverCardProps {
  item: WorkItem
  anchor: HTMLElement
  onOpen: () => void
  /** Who is looking. Defaults to the signed-in participant; null is nobody,
   *  and then no decision is said to be "for you". */
  viewer?: Id | null
  /** Escape dismisses the card when given. */
  onDismiss?: () => void
  id?: string
  onMouseEnter?: () => void
  onMouseLeave?: () => void
}

export default function WorkHoverCard({ item, anchor, onOpen, viewer, onDismiss, id, onMouseEnter, onMouseLeave }: WorkHoverCardProps) {
  const { me: signedIn } = useMe()
  const me = (viewer === undefined ? signedIn : viewer) || null
  /* A PREVIEW, NOT A LIVE-RUNS READER: it rereads when the record moves. */
  const read = useWorkDetail(item.expectation, me, { runs: false })
  const detail = read.data?.expectation === item.expectation ? read.data : null
  const questions = me ? detail?.decisions.filter((d) => !d.answered && d.owed_by === me).map((d) => d.question).filter(Boolean).join('; ') : ''
  const card = useRef<HTMLDivElement>(null)
  const [position, setPosition] = useState({ top: 0, left: 0 })
  useLayoutEffect(() => {
    const place = () => {
      const a = anchor.getBoundingClientRect()
      const h = card.current?.offsetHeight ?? 180
      const w = card.current?.offsetWidth ?? 300
      setPosition({
        left: Math.max(8, Math.min(a.left + a.width / 3, window.innerWidth - w - 8)),
        top: a.bottom + h + 12 < window.innerHeight ? a.bottom + 7 : Math.max(8, a.top - h - 7),
      })
    }
    place()
    window.addEventListener('resize', place)
    window.addEventListener('scroll', place, true)
    const size = new ResizeObserver(place)
    if (card.current) size.observe(card.current)
    return () => {
      size.disconnect()
      window.removeEventListener('resize', place)
      window.removeEventListener('scroll', place, true)
    }
  }, [anchor])
  /* ESCAPE TAKES THE CARD AWAY FIRST, and only the card: heard while
     capturing, so an open drawer's own Escape does not also fire. */
  const dismiss = useRef(onDismiss)
  dismiss.current = onDismiss
  const dismissible = onDismiss !== undefined
  useEffect(() => {
    if (!dismissible) return
    const key = (e: KeyboardEvent) => {
      if (e.key !== 'Escape' || !dismiss.current) return
      e.preventDefault()
      e.stopPropagation()
      dismiss.current()
    }
    document.addEventListener('keydown', key, true)
    return () => document.removeEventListener('keydown', key, true)
  }, [dismissible])
  const owed = item.decisions_open > 0
    ? `${item.decisions_open} ${item.decisions_open === 1 ? 'decision' : 'decisions'}${me ? ' for you' : ' open'}`
    : null
  return createPortal(
    <div className="work-hover" ref={card} style={position} id={id} role="region" aria-label="Work preview"
      onMouseEnter={onMouseEnter} onMouseLeave={onMouseLeave}>
      <strong>{item.title ?? 'Work title unknown'}</strong>
      {item.stage_words && <div className="work-hover-stage" data-stage={item.stage}>{item.stage_words}</div>}
      <div><StatusWords item={item} />
        {' · '}{item.objective_met === true ? 'Objective met' : 'Not complete'}</div>
      {detail && <div>{detail.executions_words}</div>}
      {owed && <div className="work-attention">
        {owed}
        {questions ? `: ${questions}` : ''}
      </div>}
      {item.why_unknown && <div>{item.why_unknown}</div>}
      {read.error && <div>Details unavailable: {read.error}</div>}
      <button className="work-link work-hover-go" onClick={onOpen}>Click for details ›</button>
    </div>, document.body,
  )
}

export { WorkHoverCard }
