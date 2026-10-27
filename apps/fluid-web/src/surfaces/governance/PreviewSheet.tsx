import { useState } from 'react'
import { useApi, qs } from '../../api'
import {
  allRows,
  indexBy,
  isGovernedMaterial,
  nameOf,
  pathOf,
  type ContextAnswer,
  type GovernedAnswer,
  type GovernedRow,
} from './InUseContext'
import { contextPath } from './previewContext'
import './preview.css'

/* ---------------------------------------------------------------------- *
 * PREVIEW -- what would compose now.
 *
 * NOTHING HAS RUN AND NOTHING IS RECORDED. This sheet computes from what
 * stands at the moment it is asked; it starts no execution, writes no
 * entry and leaves no trace. The banner says so before the controls,
 * because a surface that looks like a launcher and is not one has to say
 * which it is in its own words rather than by what it omits.
 *
 * AND IT OFFERS NO RUNTIME CONTROL. Not because the field was forgotten:
 * a runtime is the carrier and not a reason anything applies, so a control
 * for it here would change nothing, and the sheet says that instead of
 * showing a disabled box.
 * ---------------------------------------------------------------------- */

export interface PreviewSheetProps {
  /** where the preview is taken. null is Brain scope, which has its own
   *  answer and is not "everywhere". */
  conversation: string | null
  conversationName?: string | null
  /** the Participant to open on, where the caller has one. */
  participant?: string | null
  /** the Persona to open on. From a Participant inspector this is the one
   *  on its most recent record; where that Persona has ended, the sheet
   *  advances to its successor without announcing it, because the question
   *  asked was what would compose NOW. */
  persona?: string | null
  onClose: () => void
  onInspect?: (entry: string) => void
}

interface PersonaRow {
  persona: string
  name: string
  stands: boolean
}

export default function PreviewSheet({
  conversation,
  conversationName,
  participant: openWith,
  persona: openAs,
  onClose,
  onInspect,
}: PreviewSheetProps) {
  const people = useApi<{ participants: { participant: string; alias: string }[] }>(
    '/api/participants' + qs({ limit: 200 }),
  )
  /* The door's own answer about what can be started as. A Persona that has
     ended is not offered here because it is not selectable at all -- the
     composer would withhold it, and offering it would be a control that
     cannot do what it looks like it does. */
  const personas = useApi<{ personas: PersonaRow[] }>('/api/personas')
  const governed = useApi<GovernedAnswer>('/api/governed' + qs({ limit: 200 }))

  const [participant, setParticipant] = useState<string>(openWith ?? '')
  const [persona, setPersona] = useState<string>(openAs ?? '')
  /* Named material is held here, listed, and passed to the composing door
     once per item -- the engine decides what of it reaches and what is
     withheld, not this sheet. */
  const [named, setNamed] = useState<string[]>([])

  const offered = personas.data?.personas ?? []
  const index = indexBy(allRows(governed.data))
  /* SILENTLY ADVANCE A PERSONA THAT HAS ENDED. The caller handed the one on
     the most recent record; what stands now is its successor, and the
     question this sheet answers is what would compose now. */
  const chosenPersona =
    persona && offered.some((p) => p.persona === persona)
      ? persona
      : successorOf(persona, index) ?? ''

  const ctx = useApi<ContextAnswer>(
    contextPath(qs({ conversation, participant, persona: chosenPersona }), named),
  )

  const standing = allRows(governed.data).filter((r) => r.state === 'stands')
  const nameable = standing.filter((r) => !named.includes(r.entry))
  const where = conversation
    ? conversationName ?? conversation
    : 'Brain scope (no Conversation)'

  return (
    <section className="preview" aria-label="What would compose now">
      <header className="pv-head">
        <div>
          <p className="pv-eyebrow">Preview</p>
          <h2>What would compose now</h2>
        </div>
        <button type="button" className="btn quiet" onClick={onClose}>
          Close
        </button>
      </header>

      {/* I-102. Said before the controls, not after the result. */}
      <p className="pv-banner">
        Computed from what stands now. <strong>Nothing has run and nothing is
        recorded.</strong> For what an execution actually received, open it from a turn
        or a delivery line.
      </p>

      <div className="pv-controls">
        <label className="pv-field">
          <span>Participant</span>
          <select value={participant} onChange={(e) => setParticipant(e.target.value)}>
            <option value="">Nobody in particular</option>
            {(people.data?.participants ?? []).map((p) => (
              <option key={p.participant} value={p.participant}>
                {p.alias}
              </option>
            ))}
          </select>
        </label>

        <label className="pv-field">
          <span>Started as (Persona)</span>
          <select value={chosenPersona} onChange={(e) => setPersona(e.target.value)}>
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
              {/* I-104 */}
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

      {/* I-105. The reason, not a disabled control. */}
      <p className="pv-refusal">
        Where: {where} · Runtime: no control, because it changes nothing here
      </p>

      {conversation === null && (
        /* I-107. There is no placement vocabulary meaning "the whole
           Brain", and none is invented here. */
        <p className="pv-scope-note">
          At Brain scope there is no placement meaning “the whole Brain”. Nothing placed
          in a Conversation is consulted. Only the Persona and named material can reach
          it.
        </p>
      )}

      {ctx.error ? (
        <p className="pv-error">{ctx.error}</p>
      ) : !ctx.data ? (
        <p className="pv-faint">Composing…</p>
      ) : (
        <Result ctx={ctx.data} index={index} onInspect={onInspect} />
      )}
    </section>
  )
}

function Result({
  ctx,
  index,
  onInspect,
}: {
  ctx: ContextAnswer
  index: Record<string, GovernedRow>
  onInspect?: (entry: string) => void
}) {
  const material = ctx.components.filter(isGovernedMaterial)
  const other = ctx.components.filter((c) => !isGovernedMaterial(c))
  const withheld = ctx.withheld

  return (
    <div className="pv-result">
      <div className="pv-result-head">
        <h3>Would receive</h3>
        {/* The stamp is the claim about what this IS, carried next to the
            thing it is about rather than only in the banner. */}
        <span className="pv-stamp">COMPUTED · NOT A RECORD</span>
      </div>

      {material.length === 0 ? (
        <p className="pv-empty">
          No governed material would reach it. That is an empty answer, computed from
          what stands — not a record that an execution received none.
        </p>
      ) : (
        <ul className="pv-list">
          {material.map((c) => (
            <li key={c.source_id ?? c.scope}>
              <button
                type="button"
                className="pv-link"
                onClick={onInspect && c.source_id ? () => onInspect(c.source_id!) : undefined}
              >
                {c.source_id ? nameOf(c.source_id, index) : c.source_kind}
              </button>
              <span className="pv-how"> · {c.why}</span>
              <span className="pv-path"> · {pathOf(c.scope)}</span>
            </li>
          ))}
        </ul>
      )}

      {other.length > 0 && (
        <p className="pv-faint">
          Also in the payload, and not governed material:{' '}
          {other.map((c) => c.source_kind).join(', ')}.
        </p>
      )}

      <h3>Would be withheld, with the reason</h3>
      {withheld.length === 0 ? (
        <p className="pv-empty">
          Composition would withhold nothing. An empty answer, read from the
          composition.
        </p>
      ) : (
        <ul className="pv-list">
          {withheld.map((w) => (
            <li key={(w.source_id ?? '') + w.source_kind + w.why}>
              <span>{w.source_id ? nameOf(w.source_id, index) : w.source_kind}</span>
              {/* the engine's own word, never re-worded */}
              <span className="pv-machine"> · withheld: {w.why}</span>
            </li>
          ))}
        </ul>
      )}

      <h3>Conflicts</h3>
      <p className="pv-sub">Surfaced, not resolved.</p>
      {ctx.conflicts.length === 0 ? (
        /* Honest about WHY it is empty: composition groups on the subject
           an item declares, and nothing declares one yet. Not a finding
           that nothing conflicts. */
        <p className="pv-empty">
          Nothing here is grouped by subject. Composition groups on the subject an item
          declares, and nothing here declares one — so this answer is empty, not a
          finding that nothing conflicts.
        </p>
      ) : (
        <ul className="pv-list">
          {ctx.conflicts.map((k) => (
            <li key={k.about}>
              {k.components.length} items here speak to “{k.about}”. Both are delivered;
              Mentis does not choose.
            </li>
          ))}
        </ul>
      )}

      <p className="pv-faint">{ctx.payload_chars} characters, as composed now.</p>
    </div>
  )
}

/** The successor of a Persona that has ended, where the record names one.
 *
 *  `superseded_by` is a list because a thing can be replaced more than once
 *  over its life; the last is the one that stands now. Where there is no
 *  successor this returns null and the sheet opens on No Persona, which is
 *  a real selection and not a failure. */
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
