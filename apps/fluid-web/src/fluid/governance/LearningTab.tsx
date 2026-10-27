/* LEARNING TAB (?gov=1&s=learning): Contract §6 & mockup adm-5a58e4464f60.
 *
 * Shows what agents recorded while working (findings, problems, solutions,
 * outcomes, hypotheses, lessons, and candidate governing material). Calls
 * GET /api/ladder/items with the filter row parameters, renders summary chips
 * from `counts`, and opens any selected item in the Stage beside its
 * originating conversation with that Turn highlighted. */

import { useMemo, useRef, useState } from 'react'
import { useApi, when, type Id } from '../../api'
import { useGovNav } from './context'
import {
  agentOptionsOf,
  artifactUrl,
  attemptedLabel,
  buildLadderItemsUrl,
  citeView,
  DEFAULT_LEARNING_FILTERS,
  filterLadderItems,
  formatStatusLabel,
  hintOfLadderItem,
  summarizeBasis,
  type LadderItem,
  type LadderItemsResponse,
  type LearningFilters,
  atAlias,
} from './ladderTypes'

const LEARNING_KINDS = [
  'finding',
  'problem',
  'solution',
  'outcome',
  'hypothesis',
  'lesson',
  'rule',
  'decision',
  'discipline',
  'workflow',
]

const UNFILTERED_URL = buildLadderItemsUrl(DEFAULT_LEARNING_FILTERS, 200, 0)

export default function LearningTab({
  conversations,
  expanded,
  onExpanded,
}: {
  conversations: Record<Id, string>
  expanded: boolean
  onExpanded: (v: boolean) => void
}) {
  const g = useGovNav()
  const [filters, setFilters] = useState<LearningFilters>(DEFAULT_LEARNING_FILTERS)
  const url = useMemo(() => buildLadderItemsUrl(filters, 200, 0), [filters])
  const read = useApi<LadderItemsResponse>(url)

  const rawItems = read.data?.items ?? []
  const items = useMemo(() => filterLadderItems(rawItems, filters), [rawItems, filters])
  const counts = read.data?.counts ?? {
    recorded: rawItems.length,
    adoption_requested: rawItems.filter((i) => i.status === 'adoption_requested').length,
    adopted: rawItems.filter((i) => i.status === 'adopted').length,
    declined: rawItems.filter((i) => i.status === 'declined').length,
    challenged: rawItems.filter((i) => i.challenged > 0).length,
    delivered: rawItems.filter((i) => i.delivered_to > 0).length,
    without_basis: rawItems.filter((i) => !i.basis || i.basis.length === 0).length,
  }
  const total = read.data?.total ?? counts.recorded
  /* "All" is every item the other filters match, whatever its status:
     `counts.all`, where the server says it. */
  const allCount = read.data?.counts?.all ?? total

  /* THE AGENT CHOICES COME FROM THE UNFILTERED SET, never from what a filter
     already narrowed (choosing one agent would leave only that one), and
     never from names the server cannot match. With no filter set, the read
     shown is that set; otherwise it is read once more without filters, and
     the last unfiltered answer stands in while that read is out. */
  const unfilteredNow = url === UNFILTERED_URL
  const unfilteredRead = useApi<LadderItemsResponse>(unfilteredNow ? null : UNFILTERED_URL)
  const lastUnfiltered = useRef<LadderItem[] | null>(null)
  const unfilteredItems = unfilteredNow ? read.data?.items ?? null : unfilteredRead.data?.items ?? null
  if (unfilteredItems) lastUnfiltered.current = unfilteredItems
  const agentOptions = useMemo(
    () => agentOptionsOf(unfilteredItems ?? lastUnfiltered.current, filters.agent),
    [unfilteredItems, filters.agent],
  )

  const convOptions = useMemo(() => {
    const map = new Map<string, string>()
    for (const [id, name] of Object.entries(conversations)) {
      map.set(id, name)
    }
    for (const it of rawItems) {
      if (it.recorded_by?.conversation) {
        map.set(
          it.recorded_by.conversation,
          it.recorded_by.conversation_name ?? conversations[it.recorded_by.conversation] ?? it.recorded_by.conversation,
        )
      }
    }
    return Array.from(map.entries())
  }, [conversations, rawItems])

  const pillClass = (status: string) => {
    switch (status) {
      case 'adopted': return 'fg-l-pill p-ado'
      case 'adoption_requested': return 'fg-l-pill p-req'
      case 'declined':
      case 'superseded':
      case 'ended':
      case 'retired':
        return 'fg-l-pill p-dec'
      default:
        return 'fg-l-pill p-rec'
    }
  }

  return (
    <div className="fg-learning" data-testid="learning-tab">
      <div className="fg-filters fg-learning-filters" role="group" aria-label="Learning filters">
        <input
          className="fg-f-grow"
          aria-label="Search learning material"
          placeholder="Search text…"
          value={filters.q}
          onChange={(e) => setFilters({ ...filters, q: e.target.value })}
        />
        <select
          aria-label="Kind filter"
          value={filters.kind}
          onChange={(e) => setFilters({ ...filters, kind: e.target.value })}
        >
          <option value="">Kind: any</option>
          {LEARNING_KINDS.map((k) => (
            <option key={k} value={k}>{k}</option>
          ))}
        </select>
        <select
          aria-label="Conversation filter"
          value={filters.conversation}
          onChange={(e) => setFilters({ ...filters, conversation: e.target.value })}
        >
          <option value="">Conversation: any</option>
          {convOptions.map(([id, name]) => (
            <option key={id} value={id}>{name}</option>
          ))}
        </select>
        <select
          aria-label="Agent filter"
          value={filters.agent}
          onChange={(e) => setFilters({ ...filters, agent: e.target.value })}
        >
          <option value="">Agent: any</option>
          {agentOptions.map((a) => (
            <option key={a} value={a}>{a}</option>
          ))}
        </select>
        <select
          aria-label="Recorded recency"
          value={filters.since}
          onChange={(e) => setFilters({ ...filters, since: e.target.value })}
        >
          <option value="">Recorded: any time</option>
          <option value="24h">Recorded: last 24 hours</option>
          <option value="7d">Recorded: last 7 days</option>
          <option value="30d">Recorded: last 30 days</option>
        </select>
        <select
          aria-label="Adoption status"
          value={filters.status}
          onChange={(e) => setFilters({ ...filters, status: e.target.value })}
        >
          <option value="">Adoption: any</option>
          <option value="recorded">Recorded</option>
          <option value="adoption_requested">Adoption requested</option>
          <option value="adopted">Adopted</option>
          <option value="declined">Adoption declined</option>
          <option value="without_basis">Without a basis</option>
        </select>
        <button
          type="button"
          className={'fg-filter-toggle' + (filters.challenged ? ' on' : '')}
          aria-pressed={filters.challenged}
          onClick={() => setFilters({ ...filters, challenged: !filters.challenged })}
        >
          Challenged
        </button>
        <span className="fg-segment" role="group" aria-label="row size">
          <button type="button" aria-pressed={!expanded} onClick={() => onExpanded(false)}>Compact</button>
          <button type="button" aria-pressed={expanded} onClick={() => onExpanded(true)}>Expanded</button>
        </span>
      </div>

      <div className="fg-chips" aria-label="Learning summary counts">
        <button
          type="button"
          className={'fg-chip' + (filters.status === '' && !filters.challenged ? ' on' : '')}
          onClick={() => setFilters({ ...filters, status: '', challenged: false })}
        >
          All · {allCount}
        </button>
        <button
          type="button"
          className={'fg-chip' + (filters.status === 'adoption_requested' ? ' on' : '')}
          onClick={() => setFilters({ ...filters, status: filters.status === 'adoption_requested' ? '' : 'adoption_requested' })}
        >
          {counts.adoption_requested} adoption requested
        </button>
        <button
          type="button"
          className={'fg-chip' + (filters.challenged ? ' on' : '')}
          onClick={() => setFilters({ ...filters, challenged: !filters.challenged })}
        >
          {counts.challenged} challenged
        </button>
        <span className="fg-chip">{counts.delivered} delivered to later work</span>
        <button
          type="button"
          className={'fg-chip' + (filters.status === 'without_basis' ? ' on' : '')}
          onClick={() => setFilters({ ...filters, status: filters.status === 'without_basis' ? '' : 'without_basis' })}
        >
          {counts.without_basis} without a basis
        </button>
      </div>

      <p className="fg-faint fg-results">Newest first · {items.length} of {total} shown</p>

      {read.loading && !read.data && <p className="fg-faint">Reading recorded material…</p>}
      {read.error && (
        <p className="fg-field-error" role="alert">
          Couldn’t read learning items: {read.error}{' '}
          <button type="button" className="fg-link" onClick={read.reload}>Retry</button>
        </p>
      )}

      {read.data && items.length === 0 && (
        <p className="fg-empty">
          No recorded material matches these filters.{' '}
          <button type="button" className="fg-link" onClick={() => setFilters(DEFAULT_LEARNING_FILTERS)}>
            Clear filters
          </button>
        </p>
      )}

      {items.length > 0 && (
        <ul className={'fg-l-rows' + (expanded ? ' expanded' : '')}>
          {items.map((item) => {
            const hint = hintOfLadderItem(item)
            const st = formatStatusLabel(item.status)
            const outcomeRes = item.kind === 'outcome'
              ? String(item.fields?.result ?? item.outcomes?.latest?.[0]?.result ?? 'observed')
              : null
            const convName = item.recorded_by?.conversation_name
              ?? (item.recorded_by?.conversation ? conversations[item.recorded_by.conversation] : null)
              ?? item.recorded_by?.conversation
            const turnRef = convName
              ? `${convName}${item.recorded_by?.number != null ? ` #${item.recorded_by.number}` : ''}`
              : null
            const basisText = summarizeBasis(item.basis)
            /* an outcome's own `attempted`: said only where it is recorded */
            const attempted = typeof item.fields?.attempted === 'boolean' ? item.fields.attempted : null

            return (
              <li key={item.id} className="fg-l-rec" data-entry={item.id}>
                <div
                  role="button"
                  tabIndex={0}
                  className="fg-l-rec-btn"
                  onClick={() => g.openItem(item.id, hint)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                      e.preventDefault()
                      g.openItem(item.id, hint)
                    }
                  }}
                >
                  <div className="fg-l-kind">
                    {item.kind}
                    {outcomeRes && <em>{outcomeRes}{attemptedLabel(attempted)}</em>}
                  </div>
                  <div className="fg-l-txt">{item.text}</div>
                  {expanded && item.limits && (
                    <div className="fg-l-limits">
                      <b>Limits:</b> {item.limits}
                    </div>
                  )}
                  {expanded && item.basis.length > 0 && (
                    <div className="fg-l-basis-list">
                      {item.basis.map((b) => {
                        const cv = citeView(b)
                        return (
                          <div key={b.ref + b.relation} className="fg-l-basis-row">
                            {cv.artifact ? (
                              <a className="fg-mono fg-l-link" href={artifactUrl(b.ref)} target="_blank" rel="noopener"
                                onClick={(e) => e.stopPropagation()}>{cv.link}</a>
                            ) : (
                              <span className="fg-mono">{cv.link}</span>
                            )}
                            {cv.quote && <span className="fg-faint"> — “{cv.quote}”</span>}
                            {cv.note && <span className="fg-faint"> · {cv.note}</span>}
                          </div>
                        )
                      })}
                    </div>
                  )}
                  <div className="fg-l-meta">
                    <b>{atAlias(item.recorded_by?.alias, 'unattributed')}</b>
                    {item.recorded_by?.runtime && <> · {item.recorded_by.runtime}</>}
                    {turnRef && (
                      <>
                        {' · '}
                        {item.recorded_by?.conversation && item.recorded_by?.turn ? (
                          <span
                            className="fg-l-link"
                            onClick={(e) => {
                              e.stopPropagation()
                              g.openItem(item.id, hint)
                            }}
                          >
                            {turnRef}
                          </span>
                        ) : (
                          <span>{turnRef}</span>
                        )}
                      </>
                    )}
                    {item.recorded_at != null && <> · {when(item.recorded_at)}</>}
                    {' · '}
                    <span className={item.basis.length === 0 ? 'fg-l-nobasis' : 'fg-l-link'}>
                      {basisText}
                    </span>
                    {!expanded && item.limits && <> · limits stated</>}
                    {item.outcomes?.count > 0 && (
                      <>
                        {' · '}
                        <span className="fg-l-link">
                          {item.outcomes.count} {item.outcomes.count === 1 ? 'outcome' : 'outcomes'}
                          {item.outcomes.latest?.[0]?.result ? ` (${item.outcomes.latest[0].result})` : ''}
                        </span>
                      </>
                    )}
                    {item.delivered_to > 0 && <> · delivered to {item.delivered_to} {item.delivered_to === 1 ? 'run' : 'runs'}</>}
                    {item.cited_by > 0 && <> · cited by {item.cited_by}</>}
                  </div>
                  <div className="fg-l-pills">
                    <span className={pillClass(item.status)}>{st.label}</span>
                    {item.governs && item.status === 'adopted' && (
                      <span className="fg-l-pill p-gov">Governs work</span>
                    )}
                    {item.challenged > 0 && (
                      <span className="fg-l-pill p-chal">Challenged · {item.challenged}</span>
                    )}
                  </div>
                </div>
              </li>
            )
          })}
        </ul>
      )}
    </div>
  )
}
