/* -- Section: Work --------------------------------------------------------- */

import { useEffect } from 'react'
import { ago } from '../../api'
import { Who } from '../identity/Who'
import { store, type Id } from '../store'
import { registerSection, type SectionBodyProps } from './registry'
import { Filters, READING, useKey } from './shared'

export type WorkState = 'all' | 'needs-you' | 'in-flight' | 'completed' | 'ended'

const WORK_STATES: { key: WorkState; label: string }[] = [
  { key: 'all', label: 'All' },
  { key: 'needs-you', label: 'Needs you' },
  { key: 'in-flight', label: 'In flight' },
  { key: 'completed', label: 'Completed' },
  { key: 'ended', label: 'Ended' },
]

function WorkCard({ id, onOpenPost }: { id: Id; onOpenPost: (c: Id, p: Id) => void }) {
  const work = useKey('work:' + id, () => store.work.get(id))
  if (!work) {
    return <div className="fw-work-card fw-home-item fw-pending" data-work={id} aria-busy="true">Loading work…</div>
  }

  return (
    <article
      className="fw-work-card fw-home-item"
      data-work={work.id}
      data-state={work.state}
      onClick={() => onOpenPost(work.conversation, work.post)}
    >
      <div className="fw-work-what">{work.what}</div>
      <header className="fw-work-card-head fw-item-meta">
        <span className={'fw-badge fw-state-badge fw-state-' + work.state}>{work.state}</span>
        {work.carrier_name && <Who id={work.carrier} name={work.carrier_name} show="line" size={16} live className="fw-carrier" />}
        <span className="fw-where">
          {work.conversation_name}
          {work.post_number != null ? ` · #${work.post_number}` : ''}
        </span>
        <time className="fw-time">{ago(work.updated_at)}</time>
      </header>
    </article>
  )
}

function WorkZone({ options, setOption, onOpenPost, chrome }: SectionBodyProps) {
  const state = (options.state as WorkState | undefined) ?? 'all'
  const onStateChange = (s: WorkState) => setOption('tab', s)
  const data = useKey('coll:home:work:' + state, () => store.homeWork.get(state))
  const counts = data?.counts ?? {}

  useEffect(() => {
    void store.loadHomeWork(state)
  }, [state])

  const items = data?.items ?? []
  const tabs = WORK_STATES.map((s) => ({
    ...s, count: counts[s.key] != null ? counts[s.key] : s.key === 'all' && data ? items.length : undefined,
  }))

  return chrome({
    filters: <Filters label="work states" className="fw-work-tabs" value={state} items={tabs} onPick={onStateChange} />,
    children: !data ? READING : items.length === 0 ? (
      <p className="fw-empty">No work in this state.</p>
    ) : (
      <div className="fw-work-list fw-home-items">
        {items.map((id) => (
          <WorkCard key={id} id={id} onOpenPost={onOpenPost} />
        ))}
      </div>
    ),
  })
}

registerSection({
  show: 'work', name: 'Work', body: WorkZone,
  defaults: { tab: 'all' },
  readOptions: (o) => ({ state: (o.tab as WorkState | undefined) ?? 'all' }),
})
