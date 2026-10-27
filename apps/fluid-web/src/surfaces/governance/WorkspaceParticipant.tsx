import { useMemo, useState } from 'react'
import { ago, useApi, when, type Id, type WhoRead } from '../../api'
import PictureChooser from '../PictureChooser'
import RuntimeDefaultChooser from '../RuntimeDefaultChooser'
import RenameParticipant from '../RenameParticipant'
import './Workspace.css'

/* ------------------------------------------------------------------------ *
 * THE PARTICIPANT INSPECTOR.
 *
 * A PARTICIPANT IS DURABLE. It is not a runtime and it is not a Persona, and
 * those three are kept apart here because the record keeps them apart:
 *
 *   Participant   who this is. It survives every execution it ever had.
 *   Persona       what an execution was STARTED AS. Chosen per execution, so
 *                 what is shown is history and never an assignment.
 *   Runtime       the carrier. A label on each execution that changes nothing
 *                 about what was composed.
 *
 * ABSENT, EMPTY AND UNKNOWN ARE THREE ANSWERS and each gets said. A
 * Participant no execution has been recorded for is ABSENT — nothing is known
 * about which Persona it would be started as or on which runtime — and that is
 * not "none". A record that lists no Persona says none was RECORDED, which is
 * not the same as none was worn. And whether this name belongs to a person is
 * a fact this record does not hold at all, so it is UNKNOWN and is not read
 * out of the prose in `about`.
 *
 * EVERYTHING HISTORICAL IS BEHIND ONE FOLD. What it has actually been run as
 * is a question somebody asks; it does not occupy the surface.
 * ------------------------------------------------------------------------ */

/** One row of the per-execution delivery question, mirrored. */
interface ReceivedRow {
  execution: Id
  answer: 'absent' | 'empty' | 'received'
  sources?: number
  participant?: Id | null
  runtime?: string | null
  conversation?: Id | null
  at?: number | null
  persona:
    | { answer: 'no_record'; why: string }
    | { answer: 'lists_none'; why: string }
    | { answer: 'from_the_record'; persona: Id }
  why?: string | null
}

interface Received {
  executions: ReceivedRow[]
  total: number
  error?: string
}

/** A Persona as the register reads it. `state` is the server's own word
 *  (`standing_state`), so an ended Persona is named and said to be ended
 *  rather than falling back to its id. */
interface PersonaRow {
  entry: Id
  summary: string
  state: 'candidate' | 'stands' | 'ended' | 'replaced' | null
}

/** One intake designation, as `/api/intake` reports it: a recorded link
 *  saying this Participant carries requests addressed to nobody as this
 *  Persona. Whether it stands is the record's answer. */
interface Designation {
  designation: Id
  participant: Id
  persona: Id
  persona_name: string | null
  stands: boolean
  superseded_by: Id[]
}

interface IntakeRead {
  carrier: { resolved: boolean; designation?: Id | null; participant?: Id | null }
  designations: Designation[]
  error?: string
}

const EXECUTIONS_SHOWN = 8

export interface WorkspaceParticipantProps {
  participant: Id
  /** the Conversation this is being read in, or null for the Brain. It
   *  narrows what is counted; it does not narrow who this is. */
  conversation: Id | null
  conversationName?: string | null
  onOpenExecution?: (execution: Id) => void
  /** trace what reaches this name here, and why */
  onTrace?: (participant: Id) => void
  onPreview?: () => void
  onInspect?: (entry: Id) => void
}

export default function WorkspaceParticipant({
  participant,
  conversation,
  conversationName,
  onOpenExecution,
  onTrace,
  onPreview,
  onInspect,
}: WorkspaceParticipantProps) {
  const [open, setOpen] = useState(false)
  const [all, setAll] = useState(false)

  const who = useApi<WhoRead>('/api/who/' + encodeURIComponent(participant))
  /* FROM DELIVERY RECORDS ONLY. Everything under the fold is what the records
     say; nothing here is computed from what stands, and nothing is inferred
     from what this name could have been run as. */
  const got = useApi<Received>(
    '/api/governance/questions?question=received&participant=' +
      encodeURIComponent(participant) +
      (conversation ? '&conversation=' + encodeURIComponent(conversation) : ''),
  )
  /* EVERY PERSONA THE RECORD HOLDS, ENDED ONES TOO. `/api/personas` answers
     what can be started as now, so a Persona that has ended was never in it:
     History named it by its id and could not say it had ended. The register
     carries every one, with its standing. */
  const personas = useApi<{ groups?: Record<string, PersonaRow[]> }>(
    '/api/governed?kind=persona&limit=500',
  )
  const personaRows = useMemo(
    () => Object.values(personas.data?.groups ?? {}).flat(),
    [personas.data],
  )
  const personaRow = (id: Id) => personaRows.find((p) => p.entry === id)
  const nameOfPersona = (id: Id) => personaRow(id)?.summary || id
  const endedPersona = (id: Id) => {
    const st = personaRow(id)?.state
    return st === 'ended' || st === 'replaced' ? st : null
  }

  /* WHICH PERSONA IT CARRIES INTAKE AS, from the designation record. A
     designation is a standing link a person established, held apart from the
     per-execution choices under History; one that has been superseded is
     history and is shown only there. */
  const intake = useApi<IntakeRead>('/api/intake')
  const mine = (intake.data?.designations ?? []).filter((d) => d.participant === participant)
  const designatedNow = mine.filter((d) => d.stands)
  const designatedBefore = mine.filter((d) => !d.stands)

  const rows = got.data?.executions ?? []
  const newest = useMemo(() => [...rows].sort((a, b) => (b.at ?? 0) - (a.at ?? 0)), [rows])

  /* PERSONAS IT HAS BEEN STARTED AS, counted from records. The two answers
     that are not a Persona are counted SEPARATELY and never folded into one
     another, because "the record listed none" and "there is no record" are
     different facts about different silences. */
  const started = useMemo(() => {
    const byPersona = new Map<string, { n: number; first: number; last: number }>()
    let listsNone = 0
    let noRecord = 0
    for (const r of rows) {
      if (r.persona.answer === 'from_the_record') {
        const id = r.persona.persona
        const at = r.at ?? 0
        const got = byPersona.get(id)
        if (got) {
          got.n += 1
          got.first = Math.min(got.first, at)
          got.last = Math.max(got.last, at)
        } else byPersona.set(id, { n: 1, first: at, last: at })
      } else if (r.persona.answer === 'lists_none') listsNone += 1
      else noRecord += 1
    }
    return {
      rows: [...byPersona.entries()].sort((a, b) => b[1].n - a[1].n),
      listsNone,
      noRecord,
    }
  }, [rows])

  /* CARRIED BY, which is a label on each execution and nothing more. */
  const runtimes = useMemo(() => {
    const out = new Map<string, number>()
    for (const r of rows) if (r.runtime) out.set(r.runtime, (out.get(r.runtime) ?? 0) + 1)
    return [...out.entries()].sort((a, b) => b[1] - a[1])
  }, [rows])

  const alias = (who.data?.alias ?? participant).replace(/^@/, '')
  const actedHere = rows.length > 0

  if (who.error)
    return <p className="wp-error">the record could not be read for that name: {who.error}</p>
  if (who.data && !who.data.known)
    return (
      <p className="wp-empty">
        {who.data.why_not ?? 'this record holds no entry under that reference'}
      </p>
    )

  return (
    <article className="wp">
      <header className="wp-head">
        <PictureChooser participant={participant} alias={who.data?.alias ?? null} onChanged={who.reload} />
        <h2>@{alias}</h2>
        <p className="wp-sub">
          {who.data?.about ? who.data.about + ' · ' : ''}A durable Participant. Not a runtime, not
          a Persona.
        </p>
        <RuntimeDefaultChooser participant={participant} who={who.data} onChanged={who.reload} />
        <RenameParticipant participant={participant} alias={who.data?.alias ?? null} onChanged={who.reload} />
      </header>

      <p className="wp-acts">
        {/* TRACE IS OFFERED ONLY WHERE THERE IS A PATH TO TRACE. Offering it
            where nothing was ever recorded would promise an answer the record
            cannot give. */}
        {actedHere && onTrace && (
          <>
            <button className="wp-link" onClick={() => onTrace(participant)}>
              Trace what reaches @{alias}
              {conversation ? ' here' : ''} →
            </button>
            {' · '}
          </>
        )}
        {onPreview && (
          <button className="wp-link" onClick={onPreview}>
            Preview what would compose{conversation ? ' here' : ''}
          </button>
        )}
      </p>

      {/* ---- the three answers, up front ---------------------------------- */}

      {/* WHETHER THIS IS A PERSON IS NOT A FACT THIS RECORD HOLDS. The resolve
          read says so itself: nothing is derived from the prose in `about`,
          because reading "agent" or "person" out of a description is inference
          dressed as a fact. So it is UNKNOWN, and the consequence the approved
          surface draws from it — that people are not composed and no delivery
          record is written for them — cannot be stated about this name. */}
      <p className="wp-unknown">
        Whether this name belongs to a person is <b>UNKNOWN</b>: the record carries no such fact,
        and it is not read out of the description.
      </p>

      {got.error ? (
        <p className="wp-error">the delivery records could not be read: {got.error}</p>
      ) : !got.data ? (
        <p className="wp-faint">reading the records…</p>
      ) : rows.length === 0 ? (
        <p className="wp-absent">
          No execution has been recorded for @{alias}
          {conversation ? ` in ${conversationName ?? 'this Conversation'}` : ''}. Nothing is known
          about which Persona it would be started as, or on which runtime. The answer is{' '}
          <b>absent</b>, not empty.
        </p>
      ) : null}

      {/* A STANDING DESIGNATION IS A RECORDED LINK, held apart from the
          per-execution choices below. Read from `/api/intake`; where the read
          has not answered or failed, that is said, never "none". */}
      {intake.error || intake.data?.error ? (
        <p className="wp-faint wp-designation">
          Whether a Persona is designated to carry intake as this name could not be read:{' '}
          {intake.error ?? intake.data?.error}
        </p>
      ) : !intake.data ? (
        <p className="wp-faint wp-designation">Reading the intake designation…</p>
      ) : designatedNow.length === 0 ? (
        <p className="wp-faint wp-designation">
          No standing designation has @{alias} carry requests addressed to nobody. An empty
          answer from the record.
        </p>
      ) : (
        <p className="wp-designation">
          {designatedNow.map((d, i) => (
            <span key={d.designation}>
              {i > 0 && ' · '}
              Carries requests addressed to nobody as{' '}
              <button className="wp-link" onClick={() => onInspect?.(d.persona)}>
                {d.persona_name ?? nameOfPersona(d.persona)}
              </button>
              <span className="wp-faint">
                {' '}
                · designated by{' '}
                <button className="wp-link" onClick={() => onInspect?.(d.designation)}>
                  {d.designation}
                </button>
                {intake.data!.carrier.resolved &&
                intake.data!.carrier.designation === d.designation
                  ? ' · in force'
                  : ' · stands, and intake does not resolve to one designation'}
              </span>
            </span>
          ))}
        </p>
      )}

      {(who.data?.conversations?.length ?? 0) > 0 && (
        <p className="wp-in">
          Participates in {who.data!.conversations!.length}{' '}
          {who.data!.conversations!.length === 1 ? 'Conversation' : 'Conversations'}.
        </p>
      )}

      {/* ---- everything historical, behind one fold ----------------------- */}
      <section className="wp-history">
        <h3 className="wp-history-head">
          History <span className="wp-faint">opens only when you ask</span>
        </h3>
        <button className="wp-fold" aria-expanded={open} onClick={() => setOpen(!open)}>
          <span className="caret" aria-hidden="true">
            {open ? '▾' : '▸'}
          </span>
          <span className="wp-fold-title">How has it actually been run?</span>
          <span className="wp-faint">
            {rows.length} {rows.length === 1 ? 'execution' : 'executions'}
          </span>
        </button>

        {open && (
          <div className="wp-fold-body">
            <h4>Personas it has been started as</h4>
            <p className="wp-faint">
              From delivery records. Chosen per execution, so this shows history, not an
              assignment.
            </p>
            {started.rows.length === 0 && started.listsNone === 0 && started.noRecord === 0 ? (
              <p className="wp-empty">None recorded. An empty answer from the records.</p>
            ) : (
              <ul className="wp-list">
                {started.rows.map(([id, c]) => (
                  <li key={id}>
                    <button className="wp-link" onClick={() => onInspect?.(id)}>
                      {nameOfPersona(id)}
                    </button>
                    {endedPersona(id) && <span className="wp-chip">{endedPersona(id)}</span>}
                    <span className="wp-faint">
                      {' '}
                      · {c.n} {c.n === 1 ? 'record' : 'records'}
                      {c.first ? ` · ${ago(c.first)} to ${ago(c.last)}` : ''}
                    </span>
                  </li>
                ))}
                {started.listsNone > 0 && (
                  <li>
                    <b>No Persona in the record</b>
                    <span className="wp-faint">
                      {' '}
                      · {started.listsNone} {started.listsNone === 1 ? 'record' : 'records'}.
                      Either none was selected or one was withheld; the record does not say which.
                    </span>
                  </li>
                )}
                {started.noRecord > 0 && (
                  <li>
                    <b>Unknown</b>
                    <span className="wp-faint">
                      {' '}
                      · {started.noRecord}{' '}
                      {started.noRecord === 1 ? 'execution has' : 'executions have'} no delivery
                      record
                    </span>
                  </li>
                )}
              </ul>
            )}

            {designatedBefore.length > 0 && (
              <>
                <h4>Intake designations that ended</h4>
                <ul className="wp-list wp-designations">
                  {designatedBefore.map((d) => (
                    <li key={d.designation}>
                      as{' '}
                      <button className="wp-link" onClick={() => onInspect?.(d.persona)}>
                        {d.persona_name ?? nameOfPersona(d.persona)}
                      </button>{' '}
                      <span className="wp-chip">ended</span>
                      <span className="wp-faint">
                        {' '}
                        · designation{' '}
                        <button className="wp-link" onClick={() => onInspect?.(d.designation)}>
                          {d.designation}
                        </button>
                        {d.superseded_by.length > 0 ? ' · superseded' : ''}
                      </span>
                    </li>
                  ))}
                </ul>
              </>
            )}

            <h4>Carried by</h4>
            {runtimes.length === 0 ? (
              <p className="wp-empty">No record names a runtime. An empty answer.</p>
            ) : (
              <p className="wp-chips">
                {runtimes.map(([r, n]) => (
                  <span key={r} className="wp-chip" title="Runtime: the carrier. Not an identity, not a Persona.">
                    {r} · {n}
                  </span>
                ))}
              </p>
            )}
            <p className="wp-faint">
              Runtime is a label on each execution. It changes nothing about what is composed.
            </p>

            <h4>Executions</h4>
            <ul className="wp-list">
              {(all ? newest : newest.slice(0, EXECUTIONS_SHOWN)).map((r) => (
                <li key={r.execution}>
                  <button className="wp-link" onClick={() => onOpenExecution?.(r.execution)}>
                    {r.at ? <span title={when(r.at)}>{ago(r.at)}</span> : 'undated'}
                  </button>
                  <span className="wp-faint">
                    {' · '}
                    {r.persona.answer === 'from_the_record'
                      ? `as ${nameOfPersona(r.persona.persona)}` +
                        (endedPersona(r.persona.persona) ? ` (${endedPersona(r.persona.persona)})` : '')
                      : r.persona.answer === 'lists_none'
                        ? 'no Persona in record'
                        : 'no delivery record'}
                    {r.runtime ? ` · ${r.runtime}` : ''}
                  </span>
                </li>
              ))}
            </ul>
            {newest.length > EXECUTIONS_SHOWN && (
              <button className="wp-link" onClick={() => setAll(!all)}>
                {all ? 'Fewer' : `All ${newest.length}`}
              </button>
            )}
            <p className="wp-faint wp-limit">
              From delivery records only. A record says what crossed. It never says an execution
              read or followed it.
            </p>
          </div>
        )}
      </section>
    </article>
  )
}
