/* COMPOSE PREVIEW IN FLUID ("What would compose now"): Contract §4, §6 & mockup adm-061fe5d11867.
 *
 * Adds "The work" field (sent as `work` to GET /api/context) and renders
 * components grouped into GOVERNING / ADOPTED KNOWLEDGE / RELEVANT EXPERIENCE
 * with their epistemic trailers (`recorded_by`, `basis`, `limits`, `outcomes`,
 * open `challenges`, `status`, `why_holds`), plus `withheld` with reasons. */

import { useState } from 'react'
import { qs, useApi, when } from '../../api'
import {
  allRows,
  indexBy,
  nameOf,
  type GovernedAnswer,
  type GovernedRow,
} from '../../surfaces/governance/InUseContext'
import '../../surfaces/governance/preview.css'
import {
  atAlias,
  buildLadderContextPath,
  whoOf,
  type LadderContextComponent,
  type LadderTrailer,
  type LadderWithheldComponent,
} from './ladderTypes'

export interface FluidPreviewSheetProps {
  conversation: string | null
  conversationName?: string | null
  participant?: string | null
  persona?: string | null
  initialWork?: string
  onClose: () => void
  onInspect?: (entry: string) => void
}

interface PersonaRow {
  persona: string
  name: string
  stands: boolean
}

/* The server's shape (Contract §4), with the optional words a summary-style
 * answer may also carry; nothing here requires them. */
type AnyComponent = Partial<LadderContextComponent> & {
  entry?: string | null
  kind?: string | null
  knowing?: 'how' | 'that' | null
  reason?: string
  summary?: string
  stands?: boolean
  why_holds?: string | null
}

type AnyWithheld = Partial<LadderWithheldComponent> & {
  entry?: string | null
  kind?: string | null
  summary?: string
  reason?: string
}

interface AnyContextAnswer {
  components?: AnyComponent[]
  withheld?: AnyWithheld[]
  conflicts?: { about: string; components: string[] }[]
  payload_chars?: number
}

function classifyTier(c: AnyComponent): 'governing' | 'adopted' | 'experience' | 'other' {
  if (c.tier === 'governing' || c.tier === 'adopted' || c.tier === 'experience') return c.tier
  // THE SERVER SAID: on no tier (orientation, the request). Only an answer
  // that carries no `tier` at all is classified from its Kind.
  if (c.tier === null) return 'other'
  if (c.knowing === 'how') return 'governing'
  const k = (c.kind ?? c.source_kind ?? '').toLowerCase()
  if (['rule', 'decision', 'discipline', 'workflow', 'instruction', 'persona'].includes(k)) {
    return 'governing'
  }
  if (['lesson', 'hypothesis'].includes(k) && (c.stands || c.trailer?.status === 'adopted')) {
    return 'adopted'
  }
  if (['finding', 'problem', 'solution', 'outcome', 'lesson', 'hypothesis'].includes(k)) {
    return 'experience'
  }
  if (c.source_id) return 'governing'
  return 'other'
}

function renderTrailer(
  c: AnyComponent,
  tier: 'governing' | 'adopted' | 'experience',
  index: Record<string, GovernedRow>,
) {
  const tr: LadderTrailer | null | undefined = c.trailer
  const parts: string[] = []
  if (tier === 'governing') {
    if (c.reason || c.why) parts.push(c.reason || c.why || '')
    // The server says it whole ("why this holds: 1 decision, ..."); older
    // fixtures said only the reason.
    const whyHolds = tr?.why ?? c.why_holds ?? tr?.why_holds
    if (whyHolds) parts.push(/^why this holds/i.test(whyHolds) ? whyHolds : `why this holds: ${whyHolds}`)
    if (tr?.outcomes && tr.outcomes.length > 0) {
      parts.push(
        `${tr.outcomes.length} recent ${tr.outcomes.length === 1 ? 'outcome' : 'outcomes'}: ${tr.outcomes.map((o) => o.result).join(', ')}`,
      )
    }
  } else {
    const rb = tr?.recorded_by
    if (rb?.alias) {
      let who = atAlias(rb.alias)
      if (rb.runtime) who += ` · ${rb.runtime}`
      if (rb.conversation_name || rb.conversation) {
        who += ` · ${rb.conversation_name ?? rb.conversation}${rb.number != null ? ` #${rb.number}` : ''}`
      } else if (rb.number != null) {
        who += ` · #${rb.number}`
      }
      if (rb.at != null) who += ` · ${when(rb.at)}`
      parts.push(who)
    }
    if (tr?.basis && tr.basis.length > 0) {
      parts.push(`from ${tr.basis.map((b) => b.label || b.ref).join(', ')}`)
    } else if (tr && (!tr.basis || tr.basis.length === 0)) {
      parts.push('no basis recorded')
    }
    if (tr?.limits) {
      parts.push(`limits: ${tr.limits}`)
    }
    if (tr?.outcomes && tr.outcomes.length > 0) {
      parts.push(
        `outcomes: ${tr.outcomes.slice(0, 3).map((o) => `${o.result}${o.text ? ` (${o.text})` : ''}`).join('; ')}`,
      )
    }
    if (tr?.status && tier === 'experience') {
      parts.push(tr.status === 'recorded' ? 'recorded, not adopted' : `${tr.status.replace(/_/g, ' ')}, not adopted`)
    }
    if (c.reason || c.why) {
      parts.push(c.reason || c.why || '')
    }
  }

  const challenges = tr?.challenges ?? []
  const rowId = c.entry ?? c.source_id
  const fallbackRow = rowId ? (index[rowId] as (GovernedRow & { disputed_by?: unknown[] }) | undefined) : undefined

  return (
    <div className="fg-pv-trail">
      {parts.filter(Boolean).join(' · ')}
      {challenges.length > 0 && (
        <>
          {parts.length > 0 ? ' · ' : ''}
          <span className="fg-warn">
            {tier === 'governing'
              ? `${challenges.length} open ${challenges.length === 1 ? 'challenge' : 'challenges'} (${challenges.map((ch) => `${whoOf(ch)}: “${ch.because}”`).join('; ')}) — still in force`
              : `challenged: ${challenges.map((ch) => `“${ch.because}” (${whoOf(ch)})`).join('; ')}`}
          </span>
        </>
      )}
      {challenges.length === 0 && fallbackRow && (fallbackRow.disputed_by?.length ?? 0) > 0 && (
        <>
          {parts.length > 0 ? ' · ' : ''}
          <span className="fg-warn">
            {fallbackRow.disputed_by!.length} open challenge — still in force
          </span>
        </>
      )}
    </div>
  )
}

export default function FluidPreviewSheet({
  conversation,
  conversationName,
  participant: openWith,
  persona: openAs,
  initialWork = '',
  onClose,
  onInspect,
}: FluidPreviewSheetProps) {
  const people = useApi<{ participants: { participant: string; alias: string }[] }>(
    '/api/participants' + qs({ limit: 200 }),
  )
  const personas = useApi<{ personas: PersonaRow[] }>('/api/personas')
  const governed = useApi<GovernedAnswer>('/api/governed' + qs({ limit: 200 }))

  const [participant, setParticipant] = useState<string>(openWith ?? '')
  const [persona, setPersona] = useState<string>(openAs ?? '')
  const [named, setNamed] = useState<string[]>([])
  const [work, setWork] = useState<string>(initialWork)

  const offered = personas.data?.personas ?? []
  const index = indexBy(allRows(governed.data))
  const chosenPersona =
    persona && offered.some((p) => p.persona === persona)
      ? persona
      : successorOf(persona, index) ?? ''

  const path = buildLadderContextPath(
    {
      conversation,
      participant: participant || null,
      persona: chosenPersona || null,
    },
    named,
    work,
  )
  const ctx = useApi<AnyContextAnswer>(path)

  const standing = allRows(governed.data).filter((r) => r.state === 'stands')
  const nameable = standing.filter((r) => !named.includes(r.entry))
  const where = conversation
    ? conversationName ?? conversation
    : 'Brain scope (no Conversation)'

  const components = ctx.data?.components ?? []
  const governing = components.filter((c) => classifyTier(c) === 'governing')
  const adopted = components.filter((c) => classifyTier(c) === 'adopted')
  const experience = components.filter((c) => classifyTier(c) === 'experience')
  const withheld = ctx.data?.withheld ?? []

  const renderComponentRow = (c: AnyComponent, tier: 'governing' | 'adopted' | 'experience', idx: number) => {
    const id = c.entry ?? c.source_id ?? `comp-${idx}`
    const kind = (c.kind ?? c.source_kind ?? 'item').toUpperCase()
    const summary = c.summary || c.text || (id && index[id]?.summary) || id
    return (
      <div key={id} className="fg-pv-item" data-entry={id}>
        <div className="fg-pv-item-main">
          <span className="fg-pv-k">{kind}</span>
          {onInspect && (c.entry || c.source_id) ? (
            <button
              type="button"
              className="fg-pv-link"
              onClick={() => onInspect((c.entry ?? c.source_id)!)}
            >
              {summary}
            </button>
          ) : (
            <span>{summary}</span>
          )}
        </div>
        {renderTrailer(c, tier, index)}
      </div>
    )
  }

  return (
    <section className="preview fg-pv-sheet" aria-label="What would compose now" data-testid="compose-preview">
      <header className="pv-head">
        <div>
          <p className="pv-eyebrow">Preview</p>
          <h2>What would compose now</h2>
        </div>
        <button type="button" className="btn quiet" onClick={onClose}>
          Close
        </button>
      </header>

      <p className="pv-banner">
        Computed from the record now. <strong>Nothing has run and nothing is
        recorded.</strong> For what an execution actually received, open it from a turn
        or a delivery line.
      </p>

      <div className="pv-controls">
        <label className="pv-field">
          <span>Participant</span>
          <select
            aria-label="Participant"
            value={participant}
            onChange={(e) => setParticipant(e.target.value)}
          >
            <option value="">Nobody in particular</option>
            {(people.data?.participants ?? []).map((p) => (
              <option key={p.participant} value={p.participant}>
                {p.alias.startsWith('@') ? p.alias : '@' + p.alias}
              </option>
            ))}
          </select>
        </label>

        <label className="pv-field">
          <span>Started as (Persona)</span>
          <select
            aria-label="Started as (Persona)"
            value={chosenPersona}
            onChange={(e) => setPersona(e.target.value)}
          >
            <option value="">No Persona</option>
            {offered.map((p) => (
              <option key={p.persona} value={p.persona}>
                {p.name}
              </option>
            ))}
          </select>
        </label>

        <label className="pv-field">
          <span>Name material for it</span>
          <select
            aria-label="Name material for it"
            value=""
            onChange={(e) => {
              const v = e.target.value
              if (v) setNamed((n) => (n.includes(v) ? n : [...n, v]))
            }}
          >
            <option value="">Add…</option>
            {nameable.map((r) => (
              <option key={r.entry} value={r.entry}>
                {r.summary || r.entry}
              </option>
            ))}
          </select>
        </label>
      </div>

      {named.length > 0 && (
        <ul className="pv-chips">
          {named.map((id) => (
            <li key={id}>
              <span>{nameOf(id, index)}</span>
              <button
                type="button"
                aria-label={`Stop naming ${nameOf(id, index)}`}
                onClick={() => setNamed((n) => n.filter((x) => x !== id))}
              >
                ×
              </button>
            </li>
          ))}
        </ul>
      )}

      <div className="fg-pv-work-field">
        <label htmlFor="fg-pv-work-input" className="fg-lbl">
          The work <span className="fg-new-tag">NEW</span>
        </label>
        <input
          id="fg-pv-work-input"
          aria-label="The work"
          className="fg-pv-work-input"
          placeholder="Describe the task or question to match adopted knowledge and relevant experience…"
          value={work}
          onChange={(e) => setWork(e.target.value)}
        />
      </div>

      <p className="pv-refusal">
        Where: {where} · Runtime: no control, because it changes nothing here
      </p>

      {ctx.error ? (
        <p className="pv-error" role="alert">{ctx.error}</p>
      ) : !path ? (
        <p className="pv-faint">Select a participant, persona, or enter the work to preview what would compose.</p>
      ) : !ctx.data ? (
        <p className="pv-faint">Composing…</p>
      ) : (
        <div className="pv-result fg-pv-tiers">
          <div className="pv-result-head">
            <h3>Would receive</h3>
            <span className="pv-stamp">COMPUTED · NOT A RECORD</span>
          </div>

          <section className="fg-pv-tier t-gov" aria-label="GOVERNING">
            <div className="fg-pv-th">
              <span className="fg-pv-nm gov">GOVERNING</span>
              <span className="fg-pv-why">Follow, within where it applies. Adopted by the owner; directs the work.</span>
            </div>
            {governing.length === 0 ? (
              <div className="fg-pv-empty">No governing material reaches this selection.</div>
            ) : (
              governing.map((c, i) => renderComponentRow(c, 'governing', i))
            )}
          </section>

          <section className="fg-pv-tier t-ado" aria-label="ADOPTED KNOWLEDGE">
            <div className="fg-pv-th">
              <span className="fg-pv-nm ado">ADOPTED KNOWLEDGE</span>
              <span className="fg-pv-why">The Brain’s working position. Use it, within its limits.</span>
            </div>
            {adopted.length === 0 ? (
              <div className="fg-pv-empty">Nothing adopted overlaps this work.</div>
            ) : (
              adopted.map((c, i) => renderComponentRow(c, 'adopted', i))
            )}
          </section>

          <section className="fg-pv-tier t-exp" aria-label="RELEVANT EXPERIENCE">
            <div className="fg-pv-th">
              <span className="fg-pv-nm exp">RELEVANT EXPERIENCE</span>
              <span className="fg-pv-why">
                Recorded by agents, not adopted. Weigh it as evidence and check its basis before relying on it.
              </span>
            </div>
            {experience.length === 0 ? (
              <div className="fg-pv-empty">
                {work.trim()
                  ? 'No recorded experience matched this work.'
                  : 'Enter "The work" above to recall relevant recorded experience.'}
              </div>
            ) : (
              experience.map((c, i) => renderComponentRow(c, 'experience', i))
            )}
          </section>

          <div className="fg-pv-withheld" aria-label="Withheld material">
            <div className="fg-lbl">Withheld, with the reason</div>
            {withheld.length === 0 ? (
              <p className="fg-faint fg-mt-xs">
                Withheld: nothing beyond the bound of 5 · superseded and deleted material is never offered
              </p>
            ) : (
              <ul className="pv-list fg-mt-xs">
                {withheld.map((w, i) => {
                  const id = w.entry ?? w.source_id ?? `withheld-${i}`
                  const label = w.summary || (id && index[id]?.summary) || w.kind || w.source_kind || id
                  const reason = w.reason || w.why || 'withheld'
                  return (
                    <li key={id + reason}>
                      <span className="fg-pv-k">{(w.kind ?? w.source_kind ?? 'item').toUpperCase()}</span>
                      <span>{label}</span>
                      <span className="pv-machine"> · withheld: {reason}</span>
                    </li>
                  )
                })}
              </ul>
            )}
          </div>
        </div>
      )}
    </section>
  )
}

function successorOf(
  persona: string | null | undefined,
  index: Record<string, GovernedRow>,
): string | null {
  let at = persona || null
  const seen = new Set<string>()
  while (at && !seen.has(at)) {
    seen.add(at)
    const row = index[at]
    const next = row?.superseded_by?.[row.superseded_by.length - 1]
    if (!next) return row?.state === 'stands' ? at : null
    at = next
  }
  return null
}
