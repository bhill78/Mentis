/* -- Section: Needs you ---------------------------------------------------- */

import { useEffect } from 'react'
import { ago } from '../../api'
import { store, type Id } from '../store'
import { registerSection, type SectionBodyProps } from './registry'
import { READING, useKey } from './shared'

function NeedsYouCard({ id, onOpenPost }: { id: Id; onOpenPost: (c: Id, p: Id) => void }) {
  const work = useKey('work:' + id, () => store.work.get(id))
  if (!work) {
    return <div className="fw-needs-you-card fw-home-item fw-pending" data-needs-you={id} aria-busy="true">Loading…</div>
  }

  return (
    <article
      className="fw-needs-you-card fw-home-item"
      data-needs-you={work.id}
      data-work={work.id}
      onClick={() => onOpenPost(work.conversation, work.post)}
    >
      <div className="fw-work-what">{work.what}</div>
      <header className="fw-work-card-head fw-item-meta">
        <span className="fw-where">
          {work.conversation_name}
          {work.post_number != null ? ` · #${work.post_number}` : ''}
        </span>
        <time className="fw-time">{ago(work.updated_at)}</time>
      </header>
    </article>
  )
}

function NeedsYouZone({ onOpenPost, onOpenGovernance, chrome }: SectionBodyProps) {
  const data = useKey('coll:home:needs-you', () => store.homeNeedsYou)

  useEffect(() => {
    void store.loadHomeNeedsYou()
  }, [])

  const items = data?.items ?? []

  return chrome({
    count: items.length,
    tools: onOpenGovernance && (
      <button className="fw-gov-door" onClick={onOpenGovernance} title="Asks and challenges about governed material, and the material itself">
        Governance →
      </button>
    ),
    children: !data ? READING : items.length === 0 ? (
      <p className="fw-empty">Nothing needs you right now.</p>
    ) : (
      <div className="fw-needs-you-list fw-home-items">
        {items.map((id) => (
          <NeedsYouCard key={id} id={id} onOpenPost={onOpenPost} />
        ))}
      </div>
    ),
  })
}

registerSection({ show: 'needs-you', name: 'Needs you', body: NeedsYouZone })
