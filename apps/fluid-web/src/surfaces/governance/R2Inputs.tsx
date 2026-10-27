import { useMemo, useState } from 'react'
import { useApi, type Id } from '../../api'
import { activityRows, storedRow, type ActivityRow } from './r2Model'

/* ------------------------------------------------------------------------ *
 * THE INPUTS A `form` MAY DECLARE THAT NAME OTHER ENTRIES OR HOLD ROWS.
 *
 * `participant` and `persona` choose one held Participant or Persona;
 * `activities` is a repeatable group of rows (key, what, who, Disciplines,
 * done when, coordinates). Generic by input: nothing here names a Kind, so
 * any Kind whose definition declares these gets them. The server checks
 * every reference where the body is written (`reference_refusal`), so a
 * stale choice is refused in words rather than saved.
 *
 * The row group is held as JSON text in the builder's own field state, the
 * same string-per-field shape every other input uses, and turned into rows
 * when the body is built (`fieldValue`).
 * ------------------------------------------------------------------------ */

interface Choice { id: Id; name: string }

function useParticipants(on: boolean): Choice[] {
  const got = useApi<{ participants: { participant: Id; alias: string }[] }>(on ? '/api/participants' : null)
  return (got.data?.participants ?? []).map((p) => ({ id: p.participant, name: p.alias }))
}

function usePersonas(on: boolean): Choice[] {
  const got = useApi<{ personas: { persona: Id; name: string }[] }>(on ? '/api/personas' : null)
  return (got.data?.personas ?? []).map((p) => ({ id: p.persona, name: p.name }))
}

function Select({ label, value, choices, onChange, none }: {
  label: string; value: string; choices: Choice[]; onChange: (v: string) => void; none: string
}) {
  // A CHOICE NO LONGER LISTED IS STILL SHOWN, by reference, so editing never
  // silently drops what the body says.
  const listed = choices.some((c) => c.id === value)
  return <select aria-label={label} value={value} onChange={(e) => onChange(e.target.value)}>
    <option value="">{none}</option>
    {!listed && value && <option value={value}>{value}</option>}
    {choices.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
  </select>
}

/** One Participant or one Persona, chosen from those held. */
export function EntrySelect({ input, field, label, help, value, onChange }: {
  input: 'participant' | 'persona'; field: string; label: string; help?: string;
  value: string; onChange: (v: string) => void
}) {
  const people = useParticipants(input === 'participant')
  const personas = usePersonas(input === 'persona')
  return <label>{label}
    <Select label={field} value={value} onChange={onChange}
      choices={input === 'participant' ? people : personas}
      none={input === 'participant' ? 'Nobody by default' : 'No Persona by default'} />
    {help && <small>{help}</small>}</label>
}

interface Governed { groups: Record<string, { entry: Id; kind: string; summary: string; governs?: boolean }[]> }
interface Kinds { kinds: { kind: string; form?: unknown; authoring: null | { door: string } }[] }

/** Standing material an activity may hand to its delegated work: whatever
 *  directs how work is done, except Kinds chosen as a Persona and Kinds that
 *  carry activities of their own -- the same rule the server writes by. */
function useDisciplines(q: string): { choices: Choice[]; more: boolean } {
  const got = useApi<Governed & { omitted?: Record<string, number> }>(
    '/api/governed?state=standing&limit=200' + (q.trim() ? '&q=' + encodeURIComponent(q.trim()) : ''))
  const kinds = useApi<Kinds>('/api/governance/authoring')
  return useMemo(() => {
    const ks = kinds.data?.kinds ?? []
    const excluded = new Set(ks.filter((k) => k.authoring?.door === 'persona' ||
      Object.values((k.form && typeof k.form === 'object' ? k.form : {}) as Record<string, { input?: string }>)
        .some((f) => f && f.input === 'activities')).map((k) => k.kind))
    return {
      choices: (got.data?.groups.standing ?? []).filter((r) => r.governs === true && !excluded.has(r.kind))
        .map((r) => ({ id: r.entry, name: `${r.summary} (${r.kind})` })),
      more: !!got.data?.omitted?.standing,
    }
  }, [got.data, kinds.data])
}

/** A repeatable group of activity rows. Nothing here orders, sequences or
 *  links one activity to the next: a row is what is done, by whom, under
 *  which Disciplines, and when it is done. */
export function ActivitiesInput({ field, label, help, value, onChange }: {
  field: string; label: string; help?: string; value: string; onChange: (v: string) => void
}) {
  const rows = activityRows(value)
  const people = useParticipants(true)
  const personas = usePersonas(true)
  const [q, setQ] = useState('')
  const { choices: disciplines, more } = useDisciplines(q)
  const set = (next: ActivityRow[]) => onChange(JSON.stringify(next.map(storedRow)))
  const change = (i: number, patch: Partial<ActivityRow>) =>
    set(rows.map((r, j) => (j === i ? { ...r, ...patch } : r)))
  const who = (i: number, k: 'persona' | 'participant' | 'role', v: string) =>
    change(i, { who: { ...(rows[i].who ?? {}), [k]: v } })
  return <fieldset className="r2-activities" aria-label={field}>
    <legend>{label}</legend>
    {help && <small>{help}</small>}
    <label>Find a Discipline<input aria-label="find a discipline" value={q} onChange={(e) => setQ(e.target.value)} />
      {more && <small>More standing material exists than is listed; search to narrow it.</small>}</label>
    {rows.map((r, i) => {
      const chosen = new Set(r.disciplines ?? [])
      // A CHOSEN DISCIPLINE THAT DOES NOT STAND NOW is kept and said: it is
      // not in the standing list, and work handed it receives nothing.
      const shown = [...disciplines, ...[...chosen].filter((d) => !disciplines.some((c) => c.id === d))
        .map((d) => ({ id: d, name: q.trim() ? `${d} (chosen; not in this search)` : `${d} (does not stand now; reaches nobody)` }))]
      return <fieldset key={i} className="r2-activity" aria-label={`Activity ${i + 1}`}>
        <legend>Activity {i + 1}{r.key ? ` · ${r.key}` : ''}</legend>
        <label>Key<input aria-label="activity key" value={r.key ?? ''} onChange={(e) => change(i, { key: e.target.value })} /><small>Short name, unique here: letters, digits, _ . -</small></label>
        <label>What it is<textarea aria-label="activity what" rows={2} value={r.what ?? ''} onChange={(e) => change(i, { what: e.target.value })} /></label>
        <label>Carried as Persona<Select label="activity persona" value={r.who?.persona ?? ''} choices={personas} none="Any Persona" onChange={(v) => who(i, 'persona', v)} /></label>
        <label>Carried by<Select label="activity participant" value={r.who?.participant ?? ''} choices={people} none="Whoever the carrier hands it to" onChange={(v) => who(i, 'participant', v)} /></label>
        <label>Role<input aria-label="activity role" value={r.who?.role ?? ''} onChange={(e) => who(i, 'role', e.target.value)} /></label>
        <fieldset className="r2-capabilities" aria-label="activity disciplines"><legend>Disciplines its work is given</legend>
          {shown.length === 0 && <small>No standing Discipline yet.</small>}
          {shown.map((d) => <label key={d.id} className="r2-check"><input type="checkbox" checked={chosen.has(d.id)} onChange={() => {
            const next = new Set(chosen); if (next.has(d.id)) next.delete(d.id); else next.add(d.id)
            change(i, { disciplines: [...next] })
          }} />{d.name}</label>)}</fieldset>
        <label>Done when<input aria-label="activity done when" value={r.done_when ?? ''} onChange={(e) => change(i, { done_when: e.target.value })} /></label>
        <label className="r2-check"><input type="checkbox" aria-label="activity coordinates" checked={!!r.coordinates} onChange={(e) => change(i, { coordinates: e.target.checked })} />Carrying it out takes the coordinate grant (for example, picking up discovered work)</label>
        <button type="button" onClick={() => set(rows.filter((_, j) => j !== i))}>Remove activity {i + 1}</button>
      </fieldset>
    })}
    <button type="button" onClick={() => set([...rows, { key: '', what: '' }])}>+ Add activity</button>
  </fieldset>
}

/** How a row group reads in a review step. */
export const activitiesSaid = (value: string) => {
  const rows = activityRows(value)
  return rows.length ? `${rows.length} activit${rows.length === 1 ? 'y' : 'ies'}: ${rows.map((r) => r.key || '(no key)').join(', ')}` : ''
}

interface ReadProcedure {
  activities: null | { key: string; disciplines: { entry: Id; name: string | null; stands: boolean; why: string | null; pinned: Id }[] }[]
}

/** WHAT A PROCEDURE NAMES THAT WOULD REACH NOBODY, on its record: each
 *  activity Discipline that does not stand now, and each one revised since
 *  it was named (which is read as its current version). Nothing when all is
 *  well, and nothing for a Kind without activities. */
export function ActivityWarnings({ id }: { id: Id }) {
  const got = useApi<ReadProcedure>(`/api/entries/${id}/activities`)
  const rows = (got.data?.activities ?? []).flatMap((a) => a.disciplines.map((d) => ({ key: a.key, d })))
  const dead = rows.filter((r) => !r.d.stands)
  const moved = rows.filter((r) => r.d.stands && r.d.entry !== r.d.pinned)
  if (!dead.length && !moved.length) return null
  return <div className="r2-effect" role="note" aria-label="Activity Disciplines">
    {dead.map((r) => <p key={`x${r.key}${r.d.pinned}`}>Activity {r.key}: {r.d.name ?? r.d.pinned} {r.d.why ?? 'does not stand'}, so work handed it receives nothing.</p>)}
    {moved.map((r) => <p key={`m${r.key}${r.d.pinned}`}>Activity {r.key}: {r.d.name ?? r.d.entry} was revised; {r.d.pinned} is superseded by {r.d.entry}, which is what is delivered and required.</p>)}
  </div>
}
