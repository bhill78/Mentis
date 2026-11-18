/* ------------------------------------------------------------------------ *
 * THE RECORD AS IT WILL READ, while it is being written.
 *
 * One rendering of a draft, from the same `fields` the composer holds and the
 * same `form` declaration the body is built from (`r2Model.fieldValue`), so
 * what is shown here and what is written are read from one place. It renders
 * what the draft says and nothing else: it resolves no identity it was not
 * given, claims no standing, and never says a record exists.
 *
 * Every value is put in as text. Markup typed into a field is shown as the
 * characters typed, because React escapes it; nothing here sets HTML.
 * ------------------------------------------------------------------------ */
import { activityRows, type ActivityRow, type FieldForm } from './r2Model'
import { useDisciplines, useParticipants, usePersonas, type Choice } from './R2Inputs'

/** What the draft is, around the fields: how it would reach anybody, whether
 *  standing is being asked for, and what it says it was concluded from. */
export interface ShownMeta {
  kindLabel: string
  icon: string
  /** written as a proposal (no standing conferred) */
  proposed: boolean
  /** how it would reach anybody, in the composer's own words */
  reach: string
  /** why it belongs where it is placed, where one is given */
  reason: string
  basis: string
  basisReason: string
  /** the activity being edited, so the preview can show where it is; -1 for none */
  selected: number
}

const named = (choices: Choice[], id: string) => choices.find((c) => c.id === id)?.name ?? id

function Detail({ label, value }: { label: string; value: string }) {
  if (!value.trim()) return null
  return <div className="r2c-detail"><strong className="r2c-label">{label}</strong>
    <p className="r2c-value">{value}</p></div>
}

function Listed({ label, value }: { label: string; value: string }) {
  const rows = value.split(/\r?\n/).map((v) => v.trim()).filter(Boolean)
  if (!rows.length) return null
  return <div className="r2c-detail"><strong className="r2c-label">{label}</strong>
    <ul>{rows.map((v, i) => <li key={i}>{v}</li>)}</ul></div>
}

/** THE ORDERED SEQUENCE, in the order the record carries it. The names it
 *  shows are the held ones this Brain answers with; an id it cannot name is
 *  shown as the id, never dropped. */
function Sequence({ rows, selected }: { rows: ActivityRow[]; selected: number }) {
  const people = useParticipants(true)
  const personas = usePersonas(true)
  const { choices: disciplines } = useDisciplines('')
  if (!rows.length) return null
  return <div className="r2c-detail"><strong className="r2c-label">Activities · {rows.length}</strong>
    <ol className="r2c-activities">{rows.map((a, i) => {
      const who = [a.who?.role, a.who?.participant && named(people, a.who.participant),
        a.who?.persona && named(personas, a.who.persona)].filter(Boolean).join(' · ')
      const given = (a.disciplines ?? []).filter((d) => d.trim())
      return <li key={i} id={`r2c-preview-activity-${i}`} className={i === selected ? 'r2c-here' : undefined}>
        <p className={a.what?.trim() ? undefined : 'r2c-placeholder'}>{a.what?.trim() || 'Activity not yet written'}</p>
        {a.key?.trim() ? <small>Key · {a.key}</small> : null}
        <small>Carried by · {who || 'Not yet specified'}</small>
        {given.length ? <small>Disciplines · {given.map((d) => named(disciplines, d)).join(', ')}</small> : null}
        <small>Done when · {a.done_when?.trim() || 'Not yet specified'}</small>
      </li>
    })}</ol></div>
}

export default function R2Shown({ kind, fields, form, meta }: {
  kind: string
  fields: Record<string, string>
  form: Record<string, FieldForm>
  meta: ShownMeta
}) {
  const at = (f: string) => fields[f] ?? ''
  const label = (f: string, fallback: string) => form[f]?.label ?? fallback
  const short = kind === 'decision' || kind === 'conversation-instruction'
  const body = at('text')
  return <article className="r2c-record">
    <div className="r2c-record-top">
      <span>{meta.icon} {meta.kindLabel}</span>
      <span className="r2c-badge">{meta.proposed ? 'Proposed' : 'Owner established'}</span>
    </div>
    <div className="r2c-record-body">
      {short ? <>
        <p className={`r2c-text${body.trim() ? '' : ' r2c-placeholder'}`}>{body.trim() || 'Your words will appear here as you write.'}</p>
        <Detail label={label('about', 'About')} value={at('about')} />
      </> : <>
        <h3 className={at('name').trim() ? undefined : 'r2c-placeholder'}>{at('name').trim() || `Untitled ${kind}`}</h3>
        <Detail label={label('about', 'When it applies')} value={at('about')} />
        <strong className="r2c-label">{label('text', kind === 'workflow' ? 'How the work proceeds' : 'Principles and procedure')}</strong>
        <p className={`r2c-value${body.trim() ? '' : ' r2c-placeholder'}`}>{body.trim() || 'Your words will appear here as you write.'}</p>
      </>}
      {kind === 'discipline' && <>
        <Listed label="Tools it uses · named, not granted" value={at('tools')} />
        <Detail label="Tool use · not verified by Mentis" value={at('tool_use')} />
        <Listed label="Requires · runtime capabilities" value={at('requires')} />
        {(['inputs', 'outputs', 'verification', 'limits'] as const).map((f) =>
          <Detail key={f} label={label(f, f)} value={at(f)} />)}
      </>}
      {kind === 'workflow' && <>
        <Listed label={label('projects', 'Projects it applies to')} value={at('projects')} />
        <Sequence rows={activityRows(at('activities'))} selected={meta.selected} />
        <Listed label={label('decisions', 'Decisions reserved to the owner')} value={at('decisions')} />
        {(['done_when', 'evidence', 'interrupted'] as const).map((f) =>
          <Detail key={f} label={label(f, f)} value={at(f)} />)}
        <Carried carrier={at('carrier')} persona={at('persona')}
          carrierLabel={label('carrier', 'Usually carried by')} personaLabel={label('persona', 'Carried as')} />
        <Listed label="Requires · runtime capabilities" value={at('requires')} />
      </>}
      <Detail label="Supporting entries" value={meta.basis} />
      <Detail label="How they support this record" value={meta.basisReason} />
    </div>
    <div className="r2c-record-bottom">
      <span>{meta.reach}</span>
      {meta.reason.trim() ? <span>{meta.reason}</span> : null}
      <span>{meta.proposed ? 'Proposal · no standing conferred' : 'Established explicitly by the owner'}</span>
    </div>
  </article>
}

/** The carrier defaults, by the names this Brain holds for them. */
function Carried({ carrier, persona, carrierLabel, personaLabel }: {
  carrier: string; persona: string; carrierLabel: string; personaLabel: string
}) {
  const people = useParticipants(true)
  const personas = usePersonas(true)
  return <>
    <Detail label={carrierLabel} value={carrier ? named(people, carrier) : ''} />
    <Detail label={personaLabel} value={persona ? named(personas, persona) : ''} />
  </>
}
