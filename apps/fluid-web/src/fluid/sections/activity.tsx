/* -- Section: Activity ----------------------------------------------------- */

import { useEffect, useState } from 'react'
import { ago } from '../../api'
import { Who } from '../identity/Who'
import { store, type Id } from '../store'
import { registerSection, type SectionBodyProps } from './registry'
import { READING, useKey } from './shared'
import RunPanel, { StopButton } from '../runs/RunPanel'
import { runLine } from '../runs/gravity'

/** A run's states that are work going on now (the server's words; fluid.css
 *  also inks runtime-ended and not-launched as live, which are not work). */
const RUN_LIVE = new Set(['running', 'active', 'performing'])

function RunCard({ id, onOpenPost }: { id: Id; onOpenPost: (c: Id, p: Id) => void }) {
  const run = useKey('run:' + id, () => store.runs.get(id))
  const [watching, setWatching] = useState(false)
  if (!run) {
    return <div className="fw-run-card fw-home-item fw-pending" data-run={id} aria-busy="true">Loading run…</div>
  }

  const isClickable = !!(run.conversation && run.post)
  /* A RUN THIS SERVER HOLDS can be watched and stopped from its card.
     Stopping ends the agent's session; the work stays open. */
  const live = !!run.held_here && run.state === 'running'

  return (
    <article
      className={'fw-run-card fw-home-item' + (isClickable ? ' fw-clickable' : '')}
      data-run={run.id}
      data-state={run.state}
      onClick={() => {
        if (isClickable) onOpenPost(run.conversation, run.post)
      }}
    >
      <header className="fw-run-card-head">
        {/* The ring is this run's, not its participant's: a finished run of
            somebody now working elsewhere does not glow. */}
        <Who id={run.participant} name={run.participant_name || run.participant} show="line" size={18}
          working={RUN_LIVE.has(run.state)} runtime={run.runtime ?? undefined} className="fw-participant" />
        <span className={'fw-badge fw-state-badge fw-run-' + run.state}>{run.state}</span>
        {/* A run that names no model (the runtime's own default) says only its runtime. */}
        {(run.runtime || run.model) && (
          <span className="fw-runtime-meta">{[run.runtime, run.model ? `(${run.model})` : ''].filter(Boolean).join(' ')}</span>
        )}
        <time className="fw-time">{ago(run.started_at)}</time>
        {isClickable && <span className="fw-run-link-hint fw-go" aria-hidden="true">{'→'}</span>}
      </header>
      {/* Participant · Persona · runtime · Task Gravity, in the order every
          run is described (runs/gravity.ts). */}
      <p className="fw-run-asked fw-meta">{runLine(run)}</p>
      {live && (
        <div className="fr-card-live" onClick={(e) => e.stopPropagation()}>
          <button type="button" className="fx-linkish fr-card-doing" aria-expanded={watching}
            onClick={() => setWatching(!watching)} title="See what the agent is doing">
            {run.stopping ? 'Stopping…' : run.activity ?? 'Working'}
          </button>
          {!run.stopping && <StopButton run={run.id} compact />}
        </div>
      )}
      {watching && run.held_here && (
        <div onClick={(e) => e.stopPropagation()}>
          <RunPanel run={run.id} who={run.participant_name || run.participant} onClose={() => setWatching(false)}
            onOpenPost={onOpenPost} />
        </div>
      )}
    </article>
  )
}

function ActivityZone({ onOpenPost, chrome }: SectionBodyProps) {
  const data = useKey('coll:home:activity', () => store.homeActivity)

  useEffect(() => {
    void store.loadHomeActivity()
  }, [])

  const items = data?.items ?? []

  return chrome({
    count: items.length,
    children: !data ? READING : items.length === 0 ? (
      <p className="fw-empty">No recent activity.</p>
    ) : (
      <div className="fw-activity-list fw-home-items">
        {items.map((id) => (
          <RunCard key={id} id={id} onOpenPost={onOpenPost} />
        ))}
      </div>
    ),
  })
}

registerSection({ show: 'activity', name: 'Activity', body: ActivityZone })
