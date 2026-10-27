/* ADOPTED TAB (?gov=1&s=adopted): Contract §6.
 *
 * Displays adopted working positions (`knowing: that`, e.g. lessons and
 * hypotheses) and governing material in force (`knowing: how`, e.g. rules,
 * decisions, disciplines, workflows, instructions, personas), with their
 * adoption history and open challenges, and links into the authoring tabs. */

import { useMemo, useState } from 'react'
import { useApi, when } from '../../api'
import { useGovNav } from './context'
import {
  formatScopeLabel,
  hintOfLadderItem,
  type LadderAdoptedItem,
  type LadderAdoptedResponse,
  resolutionOf,
  whoOf,
  atAlias,
} from './ladderTypes'

export default function AdoptedTab({
  onSelectTab,
}: {
  onSelectTab: (tab: string) => void
}) {
  const g = useGovNav()
  const [q, setQ] = useState('')
  const [kind, setKind] = useState('')
  const [challengedOnly, setChallengedOnly] = useState(false)

  const url = useMemo(() => {
    const params: string[] = []
    if (kind) params.push(`kind=${encodeURIComponent(kind)}`)
    if (q.trim()) params.push(`q=${encodeURIComponent(q.trim())}`)
    if (challengedOnly) params.push('challenged=1')
    return `/api/ladder/adopted${params.length ? '?' + params.join('&') : ''}`
  }, [kind, q, challengedOnly])

  const read = useApi<LadderAdoptedResponse>(url)

  const items = useMemo(() => {
    const raw = read.data?.items ?? []
    const needle = q.trim().toLowerCase()
    return raw.filter((it) => {
      if (kind && it.kind !== kind) return false
      if (challengedOnly && !(it.challenged > 0 || (it.challenges && it.challenges.length > 0))) return false
      if (needle) {
        const hay = `${it.id} ${it.kind} ${it.text} ${it.because ?? ''} ${it.limits ?? ''}`.toLowerCase()
        if (!hay.includes(needle)) return false
      }
      return true
    })
  }, [read.data, kind, q, challengedOnly])

  const workingPositions = useMemo(
    () => items.filter((it) => !it.governs && (it.kind === 'lesson' || it.kind === 'hypothesis')),
    [items],
  )
  const governingItems = useMemo(
    () => items.filter((it) => it.governs || (it.kind !== 'lesson' && it.kind !== 'hypothesis')),
    [items],
  )

  const renderCard = (item: LadderAdoptedItem) => {
    const hint = hintOfLadderItem(item)
    const openChallenges = (item.challenges ?? []).filter((c) => resolutionOf(c) === 'open')
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
            <em>{item.governs ? 'knowing: how · governs work' : 'knowing: that · working position'}</em>
          </div>
          <div className="fg-l-txt">{item.text}</div>
          {item.limits && (
            <div className="fg-l-limits">
              <b>Limits:</b> {item.limits}
            </div>
          )}
          <div className="fg-l-meta">
            <b>Adopted by {item.adopted_by_alias ?? item.adopted_by ?? 'Owner'}</b>
            {item.adopted_at != null && <> · {when(item.adopted_at)}</>}
            {' · '}
            <span>{formatScopeLabel(item.scope, item.governs)}</span>
            {item.because && <> · why: “{item.because}”</>}
            {item.delivered_to > 0 && <> · delivered to {item.delivered_to} runs</>}
            {item.cited_by > 0 && <> · cited by {item.cited_by}</>}
          </div>
          {openChallenges.length > 0 && (
            <div className="fg-adopted-challenges">
              {openChallenges.map((c) => (
                <div key={c.link} className="fg-warn">
                  Open challenge by {whoOf(c, 'Participant')}: “{c.because}”
                </div>
              ))}
            </div>
          )}
          {item.history && item.history.length > 0 && (
            <div className="fg-adopted-history">
              {item.history.slice(0, 3).map((h, idx) => (
                <span key={idx} className="fg-adopted-hist-step">
                  <b>{h.act}</b>
                  {h.by ? ` by ${atAlias((h as { by_alias?: string | null }).by_alias ?? h.by)}` : ''}
                  {h.at ? ` (${when(h.at)})` : ''}
                </span>
              ))}
            </div>
          )}
          <div className="fg-l-pills">
            <span className="fg-l-pill p-ado">Adopted</span>
            {item.governs && <span className="fg-l-pill p-gov">Governs work</span>}
            {(item.challenged > 0 || openChallenges.length > 0) && (
              <span className="fg-l-pill p-chal">
                Challenged · {Math.max(item.challenged, openChallenges.length)}
              </span>
            )}
          </div>
        </div>
      </li>
    )
  }

  return (
    <div className="fg-adopted-tab" data-testid="adopted-tab">
      <div className="fg-filters" role="group" aria-label="Adopted material filters">
        <input
          className="fg-f-grow"
          aria-label="Search adopted material"
          placeholder="Search adopted positions and governing rules…"
          value={q}
          onChange={(e) => setQ(e.target.value)}
        />
        <select aria-label="Adopted kind filter" value={kind} onChange={(e) => setKind(e.target.value)}>
          <option value="">Kind: any</option>
          <option value="lesson">lesson</option>
          <option value="hypothesis">hypothesis</option>
          <option value="rule">rule</option>
          <option value="decision">decision</option>
          <option value="discipline">discipline</option>
          <option value="workflow">workflow</option>
          <option value="instruction">instruction</option>
          <option value="persona">persona</option>
        </select>
        <button
          type="button"
          className={'fg-filter-toggle' + (challengedOnly ? ' on' : '')}
          aria-pressed={challengedOnly}
          onClick={() => setChallengedOnly(!challengedOnly)}
        >
          Challenged
        </button>
      </div>

      <div className="fg-chips" aria-label="Authoring section shortcuts">
        <span className="fg-faint">Authoring tabs:</span>
        <button type="button" className="fg-chip" onClick={() => onSelectTab('instructions')}>Instructions →</button>
        <button type="button" className="fg-chip" onClick={() => onSelectTab('personas')}>Personas →</button>
        <button type="button" className="fg-chip" onClick={() => onSelectTab('rules')}>Rules &amp; decisions →</button>
        <button type="button" className="fg-chip" onClick={() => onSelectTab('disciplines')}>Disciplines →</button>
        <button type="button" className="fg-chip" onClick={() => onSelectTab('workflows')}>Workflows →</button>
      </div>

      {read.loading && !read.data && <p className="fg-faint">Reading adopted material…</p>}
      {read.error && (
        <p className="fg-field-error" role="alert">
          Couldn’t read adopted material: {read.error}{' '}
          <button type="button" className="fg-link" onClick={read.reload}>Retry</button>
        </p>
      )}

      <section className="fg-adopted-group" aria-label="Working positions (knowing: that)">
        <h2 className="fg-h">
          Working positions <span className="fg-faint">(knowing: that — lessons &amp; hypotheses)</span>
        </h2>
        {workingPositions.length === 0 ? (
          <p className="fg-faint">No adopted working positions match these filters.</p>
        ) : (
          <ul className="fg-l-rows">{workingPositions.map(renderCard)}</ul>
        )}
      </section>

      <section className="fg-adopted-group" aria-label="Governing material (knowing: how)">
        <h2 className="fg-h">
          Governing material <span className="fg-faint">(knowing: how — rules, decisions, disciplines &amp; workflows)</span>
        </h2>
        {governingItems.length === 0 ? (
          <p className="fg-faint">No adopted governing material matches these filters.</p>
        ) : (
          <ul className="fg-l-rows">{governingItems.map(renderCard)}</ul>
        )}
      </section>
    </div>
  )
}
