/* ------------------------------------------------------------------------ *
 * THE ORDERED ACTIVITIES OF A WORKFLOW, edited one beside the sequence.
 *
 * Why this layout exists: an activity is not a field, it is a piece of work
 * with its own carrier, its own Disciplines and its own finish, and the thing
 * the author is actually deciding is WHERE IT BELONGS among the others. So
 * the ordered list stays on screen while one activity is edited, and the
 * record preview shows the same order.
 *
 * It is an order for people to read. Nothing here advances, schedules or
 * runs anything, exactly as the Kind's own meaning says.
 *
 * REMOVING ONE IS ASKED ABOUT, because the activity being removed is often
 * the one just written and nothing else holds it. The question says what
 * happens to the others: they keep their order.
 *
 * The rows live in the composer's own field state as JSON (`r2Model`), the
 * same string-per-field shape every other input uses, so the draft protection
 * that guards everything else guards a part-written activity too.
 * ------------------------------------------------------------------------ */
import { useRef, useState } from 'react'
import { activityRows, storedRow, type ActivityRow } from './r2Model'
import { Select, useDisciplines, useParticipants, usePersonas } from './R2Inputs'

/** How one activity reads in the sequence: its first sentence, or its key. */
export function activityTitle(a: ActivityRow, i: number): string {
  const first = (a.what ?? '').trim().split(/[.\n]/)[0].slice(0, 70).trim()
  return first || (a.key ?? '').trim() || `Untitled activity ${i + 1}`
}

export default function R2Sequence({ value, onChange, onStructural, selected, onSelect }: {
  value: string
  onChange: (v: string) => void
  /** said when the shape of the draft changed without any field being typed
   *  into -- an added, moved or removed activity is a change to keep */
  onStructural: () => void
  selected: number
  onSelect: (i: number) => void
}) {
  const rows = activityRows(value)
  const people = useParticipants(true)
  const personas = usePersonas(true)
  const [q, setQ] = useState('')
  const { choices: disciplines, more } = useDisciplines(q)
  const [removing, setRemoving] = useState(false)
  const back = useRef<HTMLButtonElement>(null)

  const put = (next: ActivityRow[]) => onChange(JSON.stringify(next.map(storedRow)))
  const at = rows[selected] as ActivityRow | undefined
  const change = (patch: Partial<ActivityRow>) =>
    put(rows.map((r, j) => (j === selected ? { ...r, ...patch } : r)))
  const who = (k: 'persona' | 'participant' | 'role', v: string) =>
    change({ who: { ...(at?.who ?? {}), [k]: v } })
  const add = () => { put([...rows, { key: '', what: '' }]); onSelect(rows.length); onStructural() }
  const move = (to: number) => {
    if (to < 0 || to >= rows.length) return
    const next = rows.slice()
    const [moved] = next.splice(selected, 1)
    next.splice(to, 0, moved)
    put(next); onSelect(to); onStructural()
  }
  const remove = () => {
    put(rows.filter((_, j) => j !== selected))
    onSelect(Math.max(0, Math.min(selected, rows.length - 2)))
    onStructural(); setRemoving(false)
  }

  return <div className="r2c-workflow-main">
    <nav className="r2c-sequence" aria-label="Ordered activities">
      <header><h3>Activities</h3><span className="r2c-faint">{rows.length}</span></header>
      <ol>{rows.map((r, i) =>
        <li key={i}><button type="button" aria-current={selected === i ? 'true' : undefined}
          onClick={() => onSelect(i)} aria-label={`Activity ${i + 1}: ${activityTitle(r, i)}`}>
          <span className="r2c-number">{String(i + 1).padStart(2, '0')}</span>
          <span className="r2c-seq-label">{activityTitle(r, i)}</span>
        </button></li>)}</ol>
      <button type="button" className="r2c-add" onClick={add}>+ Add activity</button>
      <p className="r2c-hint">An order for people to follow. Nothing advances by itself.</p>
    </nav>

    <section className="r2c-section r2c-activity-detail">
      {!at ? <div className="r2c-activity-empty">
        <p className="r2c-eyebrow">The sequence starts here</p>
        <h3>What happens first?</h3>
        <p className="r2c-faint">Add an activity, then say who carries it and what shows it is done.</p>
        <button type="button" className="r2-primary" onClick={add}>+ Add activity</button>
      </div> : <>
        <div className="r2c-activity-title">
          <div><p className="r2c-eyebrow">Activity {selected + 1} of {rows.length}</p><h3>Edit this activity</h3></div>
          <span className="r2c-faint">In sequence</span>
        </div>
        <div className="r2c-move-actions">
          <button type="button" ref={back} disabled={selected === 0} onClick={() => move(selected - 1)}>↑ Move up</button>
          <button type="button" disabled={selected === rows.length - 1} onClick={() => move(selected + 1)}>↓ Move down</button>
          <button type="button" className="r2c-quiet" onClick={() => setRemoving(true)}>Remove activity</button>
        </div>

        <label>What happens<textarea aria-label="activity what" rows={5} value={at.what ?? ''}
          onChange={(e) => change({ what: e.target.value })} /><small>Describe this activity in the work.</small></label>
        <label>Key<input aria-label="activity key" value={at.key ?? ''}
          onChange={(e) => change({ key: e.target.value })} /><small>Short name, unique here: letters, digits, _ . -</small></label>
        <label>Who carries it<input aria-label="activity role" value={at.who?.role ?? ''}
          onChange={(e) => who('role', e.target.value)} /><small>A role in the work; name a participant or Persona below where it helps.</small></label>
        <div className="r2c-twofields">
          <label>Participant<Select label="activity participant" value={at.who?.participant ?? ''} choices={people}
            none="Whoever the carrier hands it to" onChange={(v) => who('participant', v)} /></label>
          <label>Persona<Select label="activity persona" value={at.who?.persona ?? ''} choices={personas}
            none="Any Persona" onChange={(v) => who('persona', v)} /></label>
        </div>

        <fieldset className="r2-capabilities" aria-label="activity disciplines">
          <legend>Disciplines its work is given</legend>
          <label className="r2c-find">Find a Discipline<input aria-label="find a discipline" value={q}
            onChange={(e) => setQ(e.target.value)} />
            {more && <small>More standing material exists than is listed; search to narrow it.</small>}</label>
          {(() => {
            const chosen = new Set(at.disciplines ?? [])
            /* A CHOSEN DISCIPLINE THAT DOES NOT STAND NOW is kept and said. */
            const shown = [...disciplines, ...[...chosen].filter((d) => !disciplines.some((c) => c.id === d))
              .map((d) => ({ id: d, name: q.trim() ? `${d} (chosen; not in this search)` : `${d} (does not stand now; reaches nobody)` }))]
            if (!shown.length) return <small>No standing Discipline yet.</small>
            return shown.map((d) => <label key={d.id} className="r2-check">
              <input type="checkbox" checked={chosen.has(d.id)} onChange={() => {
                const next = new Set(chosen)
                if (next.has(d.id)) next.delete(d.id); else next.add(d.id)
                change({ disciplines: [...next] })
              }} />{d.name}</label>)
          })()}
        </fieldset>

        <label>Done when<textarea aria-label="activity done when" rows={3} value={at.done_when ?? ''}
          onChange={(e) => change({ done_when: e.target.value })} /><small>What shows this activity has finished.</small></label>

        <details className="r2c-activity-more"><summary>How it is carried out</summary>
          <label className="r2-check"><input type="checkbox" aria-label="activity coordinates" checked={!!at.coordinates}
            onChange={(e) => change({ coordinates: e.target.checked })} />Carrying it out takes the coordinate grant (for example, picking up discovered work)</label>
          <label>Default tier<select aria-label="activity default tier" value={at.default_tier ?? ''}
            onChange={(e) => change({ default_tier: e.target.value })}>
            <option value="">None</option>
            <option value="economy">Economy (low effort)</option>
            <option value="coding">Coding (medium effort)</option>
            <option value="frontier">Frontier (high effort)</option>
          </select></label>
          <label className="r2-check"><input type="checkbox" aria-label="activity authority sensitive" checked={!!at.authority_sensitive}
            onChange={(e) => change({ authority_sensitive: e.target.checked })} />Changes authority, so it needs a frontier model at high effort</label>
        </details>

        <div className="r2c-neighbours">
          <p>Before <strong>{selected ? activityTitle(rows[selected - 1], selected - 1) : 'Start of this Workflow'}</strong></p>
          <p>After <strong>{selected < rows.length - 1 ? activityTitle(rows[selected + 1], selected + 1) : 'End of this Workflow'}</strong></p>
        </div>
        <div className="r2c-activity-navigation">
          <button type="button" disabled={selected === 0} onClick={() => onSelect(selected - 1)}>← Previous</button>
          <button type="button" disabled={selected === rows.length - 1} onClick={() => onSelect(selected + 1)}>Next →</button>
        </div>
      </>}
    </section>

    {/* REMOVING ONE IS ASKED ABOUT, in the same readable card the leave
        warning uses, and it says what happens to the activities around it. */}
    {removing && at && <div className="r2-create-guard r2c-remove-guard" role="alertdialog" aria-modal="true" aria-label="Remove this activity?">
      <div className="r2-create-guard-card">
        <h3>Remove this activity?</h3>
        <p>“{activityTitle(at, selected)}” and everything written in it — who carries it, its Disciplines and when it is done — is removed from this draft.
          The activities around it keep their order.</p>
        <div className="r2-actions">
          <button type="button" autoFocus onClick={() => { setRemoving(false); back.current?.focus() }}>Keep activity</button>
          <button type="button" onClick={remove}>Remove activity</button>
        </div>
      </div>
    </div>}
  </div>
}
