import { useState } from 'react'
import { useApi, qs, when } from '../../api'
import {
  allRows,
  endedTag,
  indexBy,
  isGovernedMaterial,
  nameOf,
  reachLabel,
  type AppliesAnswer,
  type AppliesRow,
  type ContextAnswer,
  type GovernedAnswer,
  type GovernedRow,
} from './InUseContext'
import './where-meets-who.css'

/* ---------------------------------------------------------------------- *
 * WHERE MEETS WHO -- the applicability investigation.
 *
 * Four columns and three arrows: governed material, why or where it
 * applies, the Participant and the Persona, and what that comes to. The
 * path is the answer; the columns are the steps of it, and a repeated cell
 * is merged rather than restated so that the shape of the path is visible.
 *
 * COMPUTED ONLY, BY DEFAULT. What this shows follows recorded links and
 * current standing, and consults no delivery record at all. Delivery
 * evidence is a SECOND question, asked on purpose with its own button, and
 * it arrives with its own limit: a delivery record says something crossed,
 * and crossing is not reading, understanding or compliance. The two are
 * never merged into one column and never given one legend.
 * ---------------------------------------------------------------------- */

export type WhereSubject =
  | { kind: 'material'; id: string }
  | { kind: 'participant'; id: string }
  | { kind: 'execution'; id: string }

export interface WhereMeetsWhoProps {
  /** the Conversation this trace is taken in, or null for Brain scope,
   *  where a trace is one row per Conversation with a drill-in. */
  conversation: string | null
  conversationName?: string | null
  /** what to trace on open. null is a real state: the subject bar is there
   *  and the body says what to choose. */
  subject?: WhereSubject | null
  /** leave the investigation. `backLabel` names the origin BY ITS OWN
   *  NAME -- "In use", "the execution record" -- never "Back". */
  onBack?: () => void
  backLabel?: string
  onPreview?: () => void
  onOpenExecution?: (execution: string) => void
  /** Brain scope only: trace this material inside one Conversation. */
  onDrillIn?: (conversation: string) => void
  onInspect?: (entry: string) => void
}

/* -- what the delivery routes answer, mirrored ---------------------------- */

interface ReceivedRow {
  execution: string
  answer: 'absent' | 'empty' | 'received'
  participant?: string
  runtime?: string
  conversation?: string
  at?: number
}

interface ExecutionSource {
  source_kind: string
  source_id: string | null
  scope: string
  how: string
  why: string
}

interface ExecutionSheet {
  execution: string
  record: 'absent' | 'empty' | 'present'
  participant?: string
  runtime?: string
  at?: number
  groups: Record<string, ExecutionSource[]>
  sources: number
  persona: { answer: 'from_the_record' | 'lists_none' | 'no_record'; persona?: string }
}

interface StandingThenNow {
  then: { state: 'candidate' | 'stands' | 'ended' | 'replaced' }
  now: { state: 'candidate' | 'stands' | 'ended' | 'replaced' }
}

interface HistoryAnswer {
  timeline: { entry: string; established: { at: number }[] }[]
}

/* ======================================================================== */

export default function WhereMeetsWho({
  conversation,
  conversationName,
  subject: opened,
  onBack,
  backLabel,
  onPreview,
  onOpenExecution,
  onDrillIn,
  onInspect,
}: WhereMeetsWhoProps) {
  /* The subject is changed IN PLACE (I-74): the investigation is one
     surface asked repeatedly, not a new page per question. */
  const [subject, setSubject] = useState<WhereSubject | null>(opened ?? null)
  /* Delivery evidence is OFF until asked for. */
  const [crossed, setCrossed] = useState(false)
  const [shown, setShown] = useState(8)

  const governed = useApi<GovernedAnswer>('/api/governed' + qs({ limit: 200 }))
  const applies = useApi<AppliesAnswer>('/api/governance/applies')
  const people = useApi<{ participants: { participant: string; alias: string }[] }>(
    '/api/participants' + qs({ limit: 200 }),
  )
  const convs = useApi<{ conversations: { id: string; name: string }[] }>(
    '/api/conversations',
  )
  const ctx = useApi<ContextAnswer>('/api/context' + qs({ conversation }))

  const entry = subject?.kind === 'material' ? subject.id : null
  /* When it began to stand, for the evidence answer "it did not stand
     until ⟨date⟩". Read once here rather than once per row. */
  const history = useApi<HistoryAnswer>(
    entry ? '/api/governance/history' + qs({ entry }) : null,
  )
  const received = useApi<{ executions: ReceivedRow[] }>(
    crossed
      ? '/api/governance/questions' +
          qs({
            question: 'received',
            conversation,
            participant: subject?.kind === 'participant' ? subject.id : null,
          })
      : null,
  )

  const rows = allRows(governed.data)
  const index = indexBy(rows)
  const names: Record<string, string> = {}
  for (const c of convs.data?.conversations ?? []) names[c.id] = c.name
  const aliases: Record<string, string> = {}
  for (const p of people.data?.participants ?? []) aliases[p.participant] = p.alias
  const here = conversationName ?? (conversation ? names[conversation] ?? conversation : null)

  const appliesRow = applies.data?.rows.find((r) => r.entry === entry) ?? null
  const stoodFrom = establishedAt(history.data, entry)

  return (
    <section className="wmw" aria-label="Where meets Who">
      {onBack && (
        <button type="button" className="btn quiet wmw-back" onClick={onBack}>
          ← Back to {backLabel ?? 'where you came from'}
        </button>
      )}

      {/* The lede names the fourth column by what it will actually hold. */}
      <p className="wmw-lede">
        Governed material → why or where it applies → Participant · Persona →{' '}
        {crossed ? 'what executions actually received (history)' : 'what current composition does'}.
        Pick what to explain.
      </p>

      <div className="wmw-bar">
        <label className="wmw-field">
          <span>Governed material</span>
          <select
            value={subject?.kind === 'material' ? subject.id : ''}
            onChange={(e) =>
              setSubject(e.target.value ? { kind: 'material', id: e.target.value } : null)
            }
          >
            <option value="">Choose…</option>
            {rows.map((r) => (
              <option key={r.entry} value={r.entry}>
                {(r.summary || r.entry) + endedTag(r)}
              </option>
            ))}
          </select>
        </label>

        {conversation && (
          <label className="wmw-field">
            <span>or a Participant</span>
            <select
              value={subject?.kind === 'participant' ? subject.id : ''}
              onChange={(e) =>
                setSubject(
                  e.target.value ? { kind: 'participant', id: e.target.value } : null,
                )
              }
            >
              <option value="">Choose…</option>
              {(people.data?.participants ?? []).map((p) => (
                <option key={p.participant} value={p.participant}>
                  {p.alias}
                </option>
              ))}
            </select>
          </label>
        )}

        <div className="wmw-buttons">
          <button
            type="button"
            className="btn quiet"
            aria-pressed={crossed}
            onClick={() => setCrossed((v) => !v)}
          >
            {crossed ? 'Hide what actually crossed' : 'What actually crossed? (history)'}
          </button>
          {onPreview && (
            <button type="button" className="btn quiet" onClick={onPreview}>
              Preview what would compose now
            </button>
          )}
        </div>
      </div>

      <Title
        subject={subject}
        here={here}
        crossed={crossed}
        index={index}
        aliases={aliases}
      />

      {!subject ? (
        <p className="wmw-empty">
          Choose governed material to trace. At Brain scope a trace shows one row per
          Conversation, with a drill-in.
        </p>
      ) : subject.kind === 'execution' ? (
        <ExecutionTrace
          execution={subject.id}
          index={index}
          aliases={aliases}
          names={names}
          onInspect={onInspect}
        />
      ) : subject.kind === 'material' && conversation === null ? (
        <BrainRows
          row={appliesRow}
          names={names}
          onDrillIn={onDrillIn}
        />
      ) : (
        <Path
          subject={subject}
          conversation={conversation}
          here={here}
          crossed={crossed}
          ctx={ctx.data}
          appliesRow={appliesRow}
          allApplies={applies.data?.rows ?? []}
          executions={(received.data?.executions ?? []).slice(0, shown)}
          executionsTotal={received.data?.executions.length ?? 0}
          onShowMore={() => setShown((n) => n + 8)}
          stoodFrom={stoodFrom}
          index={index}
          aliases={aliases}
          onInspect={onInspect}
          onOpenExecution={onOpenExecution}
        />
      )}

      <Legend crossed={crossed} />
    </section>
  )
}

/* -------------------------------- title ---------------------------------- */

function Title({
  subject,
  here,
  crossed,
  index,
  aliases,
}: {
  subject: WhereSubject | null
  here: string | null
  crossed: boolean
  index: Record<string, GovernedRow>
  aliases: Record<string, string>
}) {
  if (!subject) return null
  if (subject.kind === 'execution') {
    return (
      <header className="wmw-title">
        <h3>Why did this execution receive what it received?</h3>
      </header>
    )
  }
  if (subject.kind === 'participant') {
    const who = aliases[subject.id] ?? subject.id
    return (
      <header className="wmw-title">
        <h3>
          What reached {who}
          {here ? ` in ${here}` : ''}, and why?
        </h3>
        <p className="wmw-sub">
          From delivery records here, plus what stands here now and has not reached it
          yet.
        </p>
      </header>
    )
  }
  const what = nameOf(subject.id, index)
  if (!here) {
    return (
      <header className="wmw-title">
        <h3>Where does “{what}” reach work?</h3>
        <p className="wmw-sub">
          One row per Conversation. Trace in one to see the Participants.
        </p>
      </header>
    )
  }
  return (
    <header className="wmw-title">
      <h3>
        {crossed
          ? `Why does “${what}” reach work in ${here}?`
          : `Why does “${what}” apply to work in ${here}?`}
      </h3>
    </header>
  )
}

/* ------------------------------ brain scope ------------------------------ */

/** One summary row per Conversation, with a drill-in. Material placed on
 *  the Whole Brain gets one row saying so -- every Conversation, now and
 *  later, and Brain-scope work -- because that placement is an explicit
 *  destination, not a list of Conversations. A piece of material placed
 *  nowhere reaches no Conversation from where it sits -- which is an empty
 *  answer with its own reason, not a blank table. */
function BrainRows({
  row,
  names,
  onDrillIn,
}: {
  row: AppliesRow | null
  names: Record<string, string>
  onDrillIn?: (conversation: string) => void
}) {
  if (!row) {
    return (
      <p className="wmw-empty">
        Nothing stands under that id, so there is no path to follow. That is an empty
        answer.
      </p>
    )
  }
  if (row.placed_at.length === 0) {
    return (
      <p className="wmw-empty">
        No path to show. {row.why}. That is an empty answer.
      </p>
    )
  }
  return (
    <table className="wmw-table">
      <thead>
        <tr>
          <th>Conversation</th>
          <th>How it applies there</th>
          <th>Trace</th>
        </tr>
      </thead>
      <tbody>
        {row.whole_brain && (
          <tr key="whole-brain">
            <td>Every Conversation, now and later, and Brain-scope work</td>
            <td className="wmw-computed">Placed · Whole Brain</td>
            <td />
          </tr>
        )}
        {row.placed_at.filter((cid) => !row.whole_brain_at?.includes(cid)).map((cid) => (
          <tr key={cid}>
            <td>{names[cid] ?? cid}</td>
            <td className="wmw-computed">{row.whole_brain
              ? `Placed · ${names[cid] ?? cid} · also on the Whole Brain`
              : reachLabel(row, names)}</td>
            <td>
              {onDrillIn && (
                <button type="button" className="wmw-link" onClick={() => onDrillIn(cid)}>
                  Trace in {names[cid] ?? cid}
                </button>
              )}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

/* -------------------------- the four-column path -------------------------- */

interface PathProps {
  subject: WhereSubject
  conversation: string | null
  here: string | null
  crossed: boolean
  ctx: ContextAnswer | null
  appliesRow: AppliesRow | null
  allApplies: AppliesRow[]
  executions: ReceivedRow[]
  executionsTotal: number
  onShowMore: () => void
  stoodFrom: number | null
  index: Record<string, GovernedRow>
  aliases: Record<string, string>
  onInspect?: (entry: string) => void
  onOpenExecution?: (execution: string) => void
}

function Path(p: PathProps) {
  const { subject, crossed, ctx, appliesRow, allApplies, index } = p

  /* The material this trace is about. For a Participant subject it is
     everything that would reach anybody here; for a material subject it is
     the one item, and the path is the ways it can arrive. */
  const material: string[] =
    subject.kind === 'material'
      ? [subject.id]
      : (ctx?.components ?? []).filter(isGovernedMaterial).map((c) => c.source_id!)

  if (material.length === 0) {
    return (
      <p className="wmw-empty">
        No path to show.{' '}
        {crossed
          ? 'No delivery record here names this Participant, and nothing stands here.'
          : 'Nothing places, selects or names it.'}{' '}
        That is an empty answer.
      </p>
    )
  }

  /* COMPUTED ONLY. One row per way the material can arrive; the Participant
     cell is whoever that way admits, because no record is consulted. */
  if (!crossed) {
    return (
      <table className="wmw-table">
        <thead>
          <tr>
            <th>Governed material</th>
            <th aria-hidden="true">→</th>
            <th>Why · where it applies</th>
            <th aria-hidden="true">→</th>
            <th>Participant · Persona</th>
            <th aria-hidden="true">→</th>
            <th>What current composition does</th>
          </tr>
        </thead>
        <tbody>
          {material.map((id, i) => {
            const row = appliesRow?.entry === id
              ? appliesRow
              : allApplies.find((r) => r.entry === id) ?? null
            const included = (ctx?.components ?? []).some((c) => c.source_id === id)
            const withheld = (ctx?.withheld ?? []).find((w) => w.source_id === id)
            return (
              <tr key={id}>
                {/* A repeated first cell is merged: at a single-material
                    trace there is one, and a Participant trace repeats the
                    Participant instead, below. */}
                <td>
                  <button
                    type="button"
                    className="wmw-link"
                    onClick={p.onInspect && (() => p.onInspect!(id))}
                  >
                    {nameOf(id, index)}
                  </button>
                </td>
                <td className="wmw-arrow" aria-hidden="true">→</td>
                <td className="wmw-computed">{row ? row.why : 'nothing stands under this id'}</td>
                <td className="wmw-arrow" aria-hidden="true">→</td>
                {i === 0 || subject.kind === 'material' ? (
                  <td rowSpan={subject.kind === 'participant' ? material.length : 1}>
                    {subject.kind === 'participant'
                      ? p.aliases[subject.id] ?? subject.id
                      : admits(row)}
                    <span className="wmw-faint"> · Persona not consulted here</span>
                  </td>
                ) : null}
                <td className="wmw-arrow" aria-hidden="true">→</td>
                <td className="wmw-computed">
                  {withheld
                    ? `withheld: ${withheld.why}`
                    : included
                      ? 'current composition includes it'
                      : row
                        ? 'no path here'
                        : 'no path here'}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    )
  }

  /* DELIVERY EVIDENCE, ASKED FOR. One row per execution in scope; the
     fourth column is what that execution's record says, and each row asks
     the record for itself. */
  if (p.executions.length === 0) {
    return (
      <p className="wmw-empty">
        No path to show. No delivery record here names this Participant, and nothing
        stands here. That is an empty answer.
      </p>
    )
  }
  return (
    <>
      <table className="wmw-table">
        <thead>
          <tr>
            <th>Governed material</th>
            <th aria-hidden="true">→</th>
            <th>Why · where it applies</th>
            <th aria-hidden="true">→</th>
            <th>Participant · Persona</th>
            <th aria-hidden="true">→</th>
            <th>Execution · delivery evidence (history)</th>
          </tr>
        </thead>
        <tbody>
          {p.executions.map((ex, i) => (
            <EvidenceRow
              key={ex.execution}
              execution={ex}
              /* THE MERGED CELL. One material traced across many
                 executions says its name once. */
              showMaterial={i === 0}
              span={p.executions.length}
              material={material}
              appliesRow={appliesRow}
              stoodFrom={p.stoodFrom}
              index={index}
              aliases={p.aliases}
              onInspect={p.onInspect}
              onOpenExecution={p.onOpenExecution}
            />
          ))}
        </tbody>
      </table>
      {p.executions.length < p.executionsTotal && (
        <button type="button" className="btn quiet wmw-more" onClick={p.onShowMore}>
          Show 8 more of {p.executionsTotal}
        </button>
      )}
    </>
  )
}

/** Who a way of applying admits, computed and said as a class of people
 *  rather than as a list read from any record. */
function admits(row: AppliesRow | null): string {
  if (!row) return 'nobody: nothing stands'
  if (row.applies === 'placed') return 'whoever acts here, whatever Persona they wear'
  if (row.applies === 'by_persona') return 'whoever an execution is started as it'
  return 'whoever names it for an execution'
}

/* ----------------------------- evidence rows ------------------------------ */

/** One execution, asked what its own record says.
 *
 *  Each row reads for itself so that an absent record on one execution is
 *  that execution's answer and never the table's. The two reads are the
 *  execution sheet and `stands(as_at=)` -- what the record said THEN, which
 *  is a different statement from what it says now and is never merged with
 *  it. */
function EvidenceRow({
  execution,
  showMaterial,
  span,
  material,
  appliesRow,
  stoodFrom,
  index,
  aliases,
  onInspect,
  onOpenExecution,
}: {
  execution: ReceivedRow
  showMaterial: boolean
  span: number
  material: string[]
  appliesRow: AppliesRow | null
  stoodFrom: number | null
  index: Record<string, GovernedRow>
  aliases: Record<string, string>
  onInspect?: (entry: string) => void
  onOpenExecution?: (execution: string) => void
}) {
  const sheet = useApi<ExecutionSheet>(
    '/api/governance/execution' + qs({ execution: execution.execution }),
  )
  const subjectEntry = material.length === 1 ? material[0] : null
  const standing = useApi<StandingThenNow>(
    subjectEntry && execution.at
      ? '/api/governance/standing' + qs({ entry: subjectEntry, as_at: execution.at })
      : null,
  )

  const sources = sheet.data ? Object.values(sheet.data.groups).flat() : []
  const hits = subjectEntry ? sources.filter((s) => s.source_id === subjectEntry) : []

  return (
    <tr>
      {showMaterial && (
        <td rowSpan={span}>
          {material.map((id) => (
            <div key={id}>
              <button
                type="button"
                className="wmw-link"
                onClick={onInspect && (() => onInspect(id))}
              >
                {nameOf(id, index)}
              </button>
            </div>
          ))}
        </td>
      )}
      <td className="wmw-arrow" aria-hidden="true">→</td>
      {showMaterial && (
        <td rowSpan={span} className="wmw-computed">
          {appliesRow ? appliesRow.why : 'nothing stands under this id'}
        </td>
      )}
      <td className="wmw-arrow" aria-hidden="true">→</td>
      <td>
        <span>{aliases[execution.participant ?? ''] ?? execution.participant ?? 'UNKNOWN'}</span>
        <span className="wmw-recorded"> · {personaCell(sheet.data)}</span>
      </td>
      <td className="wmw-arrow" aria-hidden="true">→</td>
      <td>
        <button
          type="button"
          className="wmw-link"
          onClick={onOpenExecution && (() => onOpenExecution(execution.execution))}
        >
          {/* A record with no time is named by its id, which is a true
              name. Nothing is left blank because a field was absent. */}
          {when(execution.at) || execution.execution}
        </button>
        <div className="wmw-recorded">
          {evidence(sheet.data, hits.length, standing.data, appliesRow, stoodFrom)}
        </div>
        {/* THE COMPUTED LINE, MARKED AS COMPUTED. It sits beside the
            recorded answer and never inside it. */}
        {appliesRow?.applies === 'placed' && standing.data?.now.state === 'stands' && (
          <div className="wmw-computed">
            current composition would include it (computed now, not a record)
          </div>
        )}
      </td>
    </tr>
  )
}

/** `persCell()` -- four answers, and none of them the word "none".
 *
 *  A record listing no Persona says that none was RECORDED. Whether one was
 *  worn is a different question and this does not answer it. */
function personaCell(sheet: ExecutionSheet | null): string {
  if (!sheet) return 'reading the record…'
  if (sheet.record === 'absent') return 'Persona unknown — last execution has no record'
  if (sheet.persona.answer === 'from_the_record') {
    return `as ${sheet.persona.persona} — last record`
  }
  if (sheet.persona.answer === 'no_record') {
    return 'Persona unknown — last execution has no record'
  }
  return 'last record lists no Persona: UNKNOWN'
}

/** `evCell()` -- five answers, kept apart.
 *
 *  Absent, empty and unknown are three different things and none of them is
 *  zero. "Not in its record" always carries WHY, read from what the record
 *  said at the time rather than from what it says now. */
function evidence(
  sheet: ExecutionSheet | null,
  hits: number,
  standing: StandingThenNow | null,
  row: AppliesRow | null,
  stoodFrom: number | null,
): string {
  if (!sheet) return 'reading the record…'
  if (sheet.record === 'absent') return 'unknown: no delivery record'
  if (hits > 0) {
    return hits > 1 ? `received it · and ${hits - 1} earlier records` : 'received it'
  }
  const then = standing?.then.state
  if (then === 'ended' || then === 'replaced') return 'not in its record · it had ended by then'
  if (then === 'candidate') {
    return stoodFrom
      ? `not in its record · it did not stand until ${when(stoodFrom)}`
      : 'not in its record · it did not stand then, and no establishing act is in the record to date'
  }
  if (row?.applies === 'when_named') return 'not in its record · not named for it'
  if (then === 'stands') return 'not in its record · it stood, but was not composed for it'
  return 'not in its record · the record does not say what stood then'
}

/* --------------------------- the execution trace -------------------------- */

/** One execution asked why it received what it received.
 *
 *  THREE REASONS CAN MEET AT ONE EXECUTION and the grouping is the answer:
 *  where it ran, who it was started as, and what was named for it. The
 *  runtime is in the record and is not one of them. */
function ExecutionTrace({
  execution,
  index,
  aliases,
  names,
  onInspect,
}: {
  execution: string
  index: Record<string, GovernedRow>
  aliases: Record<string, string>
  names: Record<string, string>
  onInspect?: (entry: string) => void
}) {
  const sheet = useApi<ExecutionSheet & { conversation?: string }>(
    '/api/governance/execution' + qs({ execution }),
  )
  if (sheet.error) return <p className="wmw-error">{sheet.error}</p>
  if (!sheet.data) return <p className="wmw-faint">Reading the record…</p>
  const d = sheet.data

  if (d.record === 'absent') {
    return (
      <p className="wmw-empty">
        No delivery record exists for this execution. What it received is{' '}
        <strong>absent from the record</strong>. It is not “nothing”, and it will not be
        reconstructed from what stands.
      </p>
    )
  }

  const sources = Object.values(d.groups).flat()
  return (
    <>
      <p className="wmw-sub">
        {aliases[d.participant ?? ''] ?? d.participant ?? 'UNKNOWN'}
        {d.conversation ? ` in ${names[d.conversation] ?? d.conversation}` : ''} ·{' '}
        {when(d.at)}. Three reasons can meet at one execution: where it ran, who it was
        started as, and what was named for it.
      </p>

      {sources.length === 0 ? (
        <p className="wmw-empty">
          The record lists <strong>no behavioural material</strong>. That is an empty
          list, read from the record, not an unknown.
        </p>
      ) : (
        <table className="wmw-table">
          <thead>
            <tr>
              <th>Governed material</th>
              <th aria-hidden="true">→</th>
              <th>Why · where it applies</th>
              <th aria-hidden="true">→</th>
              <th>Participant · Persona</th>
              <th aria-hidden="true">→</th>
              <th>Execution · delivery evidence (history)</th>
            </tr>
          </thead>
          <tbody>
            {sources.map((s, i) => (
              <tr key={(s.source_id ?? s.source_kind) + i}>
                <td>
                  {s.source_id ? (
                    <button
                      type="button"
                      className="wmw-link"
                      onClick={onInspect && (() => onInspect(s.source_id!))}
                    >
                      {nameOf(s.source_id, index)}
                    </button>
                  ) : (
                    /* No durable identity: nothing to open, and its text
                       existed only for this execution. */
                    <span>{s.source_kind} — no durable identity</span>
                  )}
                </td>
                <td className="wmw-arrow" aria-hidden="true">→</td>
                <td className="wmw-recorded">{s.why}</td>
                <td className="wmw-arrow" aria-hidden="true">→</td>
                {i === 0 && (
                  <td rowSpan={sources.length}>
                    <span>{aliases[d.participant ?? ''] ?? d.participant ?? 'UNKNOWN'}</span>
                    <span className="wmw-recorded"> · {personaCell(d)}</span>
                  </td>
                )}
                <td className="wmw-arrow" aria-hidden="true">→</td>
                <td className="wmw-recorded">received it</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {d.runtime && (
        <p className="wmw-note">
          carried by {d.runtime}, which is not a reason anything applied
        </p>
      )}

      <p className="wmw-foot">
        Also in the record, and not governed material: orientation (computed at the time)
        and the request. What composition withheld at the time is{' '}
        <strong>unknown</strong>: that list is not kept.
      </p>
    </>
  )
}

/* -------------------------------- legend ---------------------------------- */

/** The legend, and the limit that goes with whichever answer is on screen.
 *
 *  The limits are different statements and are never shown together as if
 *  they were one. */
function Legend({ crossed }: { crossed: boolean }) {
  return (
    <footer className="wmw-legend">
      <ul>
        {crossed && <li className="wmw-recorded">recorded</li>}
        <li className="wmw-computed">computed now</li>
        {crossed && <li className="wmw-unknown">unknown</li>}
        <li className="wmw-faint">empty / no path</li>
      </ul>
      <p>
        {crossed
          ? 'This trace includes delivery records. Delivery is not reading, understanding or compliance.'
          : 'Follows recorded links and current standing only. No delivery record is consulted.'}
      </p>
    </footer>
  )
}

/* --------------------------------- reading -------------------------------- */

/** When this entry began to stand, from the establishing act in its own
 *  timeline. Null where nobody established it -- which is a real answer and
 *  is rendered as one, never as a date nobody recorded. */
function establishedAt(history: HistoryAnswer | null, entry: string | null): number | null {
  if (!history || !entry) return null
  const row = history.timeline.find((t) => t.entry === entry)
  const at = row?.established?.[0]?.at
  return typeof at === 'number' ? at : null
}
