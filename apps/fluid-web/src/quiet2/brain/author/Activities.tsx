/* A WORKFLOW'S ACTIVITIES, growing one at a time.
 *
 * One activity is open; the others are one line each. An open activity asks
 * only what happens. Who does it, the disciplines it uses and when it is
 * finished appear when asked for; the settings an activity rarely needs
 * (a named participant or persona, its short name, how it is routed) are one
 * step further. Every part an activity can hold is reachable here: none of
 * them is on screen until it is wanted.
 *
 * It is an order for people to follow. Nothing here implies that anything
 * advances by itself, exactly as the Kind's own meaning says.
 *
 * Used unchanged for a new workflow and for revising one: an activity that
 * came from the record keeps its short name (its key), because delegated
 * work is labelled by it. */
import { useRef, useState } from 'react'
import { activityRows, storedRow, type ActivityRow } from '../../../surfaces/governance/r2Model'
import { Select, useDisciplines, useParticipants, usePersonas } from '../../../surfaces/governance/R2Inputs'
import Finder from './Finder'
import { activityLine, type Ref } from './model'

const count = (n: number, one: string) => `${n} ${one}${n === 1 ? '' : 's'}`

export default function Activities({ field, value, onChange, focusIndex }: {
  field: string
  value: string
  onChange: (v: string) => void
  /** the activity a refusal named, opened and focused */
  focusIndex?: { i: number; n: number } | null
}) {
  const rows = activityRows(value)
  const [open, setOpen] = useState(rows.length ? 0 : -1)
  const [detail, setDetail] = useState<number | null>(null)
  const [more, setMore] = useState(false)
  const [finding, setFinding] = useState(false)
  const [removed, setRemoved] = useState<{ row: ActivityRow; at: number } | null>(null)
  const box = useRef<HTMLDivElement>(null)
  const people = useParticipants(more)
  const personas = usePersonas(more)
  /* the names of what is chosen, so a line never shows a reference */
  const known = useDisciplines('')
  const nameOfD = (id: string) => known.choices.find((c) => c.id === id)?.name.replace(/\s*\([\w -]+\)$/, '') ?? 'A discipline not in effect now'

  /* a refusal that names an activity opens it */
  const seen = useRef(0)
  if (focusIndex && focusIndex.n !== seen.current) {
    seen.current = focusIndex.n
    if (open !== focusIndex.i) setOpen(focusIndex.i)
    window.setTimeout(() => box.current?.querySelector<HTMLElement>('[data-act-open] textarea')?.focus(), 0)
  }

  const put = (next: ActivityRow[]) => onChange(JSON.stringify(next.map(storedRow)))
  const focus = (sel: string) => { const go = () => { const to = box.current?.querySelector<HTMLElement>(sel); to?.focus(); return !!to }; queueMicrotask(() => { if (!go()) window.setTimeout(go, 0) }) }
  const show = (i: number) => { setOpen(i); setDetail(null); setMore(false); setFinding(false); focus('[data-act-open] textarea') }
  const change = (i: number, patch: Partial<ActivityRow>) => put(rows.map((r, j) => (j === i ? { ...r, ...patch } : r)))
  const who = (i: number, k: 'persona' | 'participant' | 'role', v: string) => change(i, { who: { ...(rows[i].who ?? {}), [k]: v } })
  const add = () => { put([...rows, { key: '', what: '' }]); setRemoved(null); show(rows.length) }
  const move = (i: number, d: number) => {
    const j = i + d
    if (j < 0 || j >= rows.length) return
    const next = rows.slice(); const [m] = next.splice(i, 1); next.splice(j, 0, m)
    put(next); setOpen(j); focus(`[data-act-move="${d < 0 ? 'up' : 'down'}"]:not(:disabled), [data-act-open] textarea`)
  }
  const remove = (i: number) => {
    setRemoved({ row: rows[i], at: i }); put(rows.filter((_, j) => j !== i))
    setOpen(Math.min(i, rows.length - 2)); setDetail(null); setFinding(false); focus('[data-act-open] textarea, [data-act-add]')
  }
  const undo = () => {
    if (!removed) return
    const next = rows.slice(); next.splice(removed.at, 0, removed.row)
    put(next); setRemoved(null); show(removed.at)
  }

  return (
    <div className="ba-acts" ref={box} data-part={field} role="group" aria-label="Activities">
      {rows.map((a, i) => {
        const chosen: Ref[] = (a.disciplines ?? []).map((d) => ({ ref: d, label: nameOfD(d), kind: 'Discipline' }))
        const said = [a.who?.role?.trim(), chosen.length ? count(chosen.length, 'discipline') : '', a.done_when?.trim() ? 'has a finish' : ''].filter(Boolean).join(' · ')
        if (i !== open) return (
          <div className="ba-act" key={i}>
            <button type="button" className="ba-act-line" aria-expanded="false" onClick={() => show(i)} aria-label={`Activity ${i + 1}: ${activityLine(a, i)}`}>
              <span className="ba-act-n">{i + 1}</span>
              <span className="ba-act-t">{activityLine(a, i)}{said && <small>{said}</small>}</span>
            </button>
          </div>
        )
        const detailed = detail === i
        const settings = !!(a.who?.participant || a.who?.persona || a.coordinates || a.default_tier || a.authority_sensitive)
        return (
          <div className="ba-act open" key={i} data-act-open
            onKeyDown={(e) => {
              if (e.altKey && e.key === 'ArrowUp') { e.preventDefault(); move(i, -1) }
              if (e.altKey && e.key === 'ArrowDown') { e.preventDefault(); move(i, 1) }
            }}>
            <label className="ba-lab" htmlFor={`ba-act-${i}`}>Activity {i + 1}: what happens?</label>
            <Grow id={`ba-act-${i}`} small value={a.what ?? ''} onChange={(v) => change(i, { what: v })} />
            {detailed && (
              <div className="ba-act-detail">
                <label className="ba-lab" htmlFor={`ba-act-who-${i}`}>Who does it?</label>
                <input id={`ba-act-who-${i}`} type="text" data-act-who value={a.who?.role ?? ''} onChange={(e) => who(i, 'role', e.target.value)} />
                <label className="ba-lab" htmlFor={`ba-act-done-${i}`}>When is it finished?</label>
                <Grow id={`ba-act-done-${i}`} small value={a.done_when ?? ''} onChange={(v) => change(i, { done_when: v })} />
                {finding ? (
                  <>
                    <span className="ba-lab">Disciplines it uses</span>
                    <Finder label="Disciplines it uses" scopes={['disciplines']} chosen={chosen}
                      onToggle={(r) => change(i, { disciplines: chosen.some((c) => c.ref === r.ref) ? chosen.filter((c) => c.ref !== r.ref).map((c) => c.ref) : [...chosen.map((c) => c.ref), r.ref] })}
                      onDone={() => { setFinding(false); focus('[data-act-disc]') }} />
                  </>
                ) : (
                  <div className="ba-line">
                    <span className="ba-line-n">Using</span>
                    <div className="ba-line-v">
                      {chosen.map((c) => (
                        <span className="ba-chip" key={c.ref}><span className="ba-chip-t" title={c.label}>{c.label}</span>
                          <button type="button" className="ba-x" aria-label={`Remove ${c.label}`} onClick={() => change(i, { disciplines: chosen.filter((x) => x.ref !== c.ref).map((x) => x.ref) })}>✕</button></span>
                      ))}
                      <button type="button" className="ba-quiet" data-act-disc onClick={() => setFinding(true)}>{chosen.length ? '+ another discipline' : 'Choose disciplines…'}</button>
                    </div>
                  </div>
                )}
                {more ? (
                  <div className="ba-act-more">
                    <label className="ba-lab">A named participant
                      <Select label="activity participant" value={a.who?.participant ?? ''} choices={people} none="Whoever it is handed to" onChange={(v) => who(i, 'participant', v)} /></label>
                    <label className="ba-lab">Acting as
                      <Select label="activity persona" value={a.who?.persona ?? ''} choices={personas} none="Any persona" onChange={(v) => who(i, 'persona', v)} /></label>
                    <label className="ba-lab" htmlFor={`ba-act-key-${i}`}>Short name</label>
                    <input id={`ba-act-key-${i}`} type="text" aria-label="activity key" value={a.key ?? ''} placeholder="Made from its words when recorded" spellCheck={false}
                      onChange={(e) => change(i, { key: e.target.value })} />
                    <label className="ba-lab">Model level
                      <select aria-label="activity default tier" value={a.default_tier ?? ''} onChange={(e) => change(i, { default_tier: e.target.value })}>
                        <option value="">None</option>
                        <option value="economy">Economy (low effort)</option>
                        <option value="coding">Coding (medium effort)</option>
                        <option value="frontier">Frontier (high effort)</option>
                      </select></label>
                    <label className="ba-check"><input type="checkbox" aria-label="activity coordinates" checked={!!a.coordinates} onChange={(e) => change(i, { coordinates: e.target.checked })} />May pick up work discovered along the way</label>
                    <label className="ba-check"><input type="checkbox" aria-label="activity authority sensitive" checked={!!a.authority_sensitive} onChange={(e) => change(i, { authority_sensitive: e.target.checked })} />Changes authority, so it needs the strongest model</label>
                  </div>
                ) : (
                  <button type="button" className="ba-quiet" data-act-more onClick={() => setMore(true)}>More settings…{settings ? ' (some are set)' : ''}</button>
                )}
              </div>
            )}
            <div className="ba-act-tools">
              <button type="button" className="ba-quiet" aria-expanded={detailed} data-act-detail
                onClick={() => { setDetail(detailed ? null : i); setMore(false); setFinding(false); if (!detailed) focus('[data-act-who]') }}>
                {detailed ? 'Fewer details' : `Who, disciplines, finished…${said || settings ? ' (some are set)' : ''}`}</button>
              <span className="ba-sp" />
              {rows.length > 1 && <>
                <button type="button" className="ba-btn s" data-act-move="up" aria-label={`Move activity ${i + 1} up`} disabled={i === 0} onClick={() => move(i, -1)}>↑</button>
                <button type="button" className="ba-btn s" data-act-move="down" aria-label={`Move activity ${i + 1} down`} disabled={i === rows.length - 1} onClick={() => move(i, 1)}>↓</button>
              </>}
              <button type="button" className="ba-btn s" data-act-remove onClick={() => remove(i)}>Remove</button>
            </div>
          </div>
        )
      })}
      {removed && <p className="ba-undo" role="status">Activity removed. <button type="button" className="ba-link" onClick={undo}>Undo</button></p>}
      <button type="button" className="ba-quiet" data-act-add onClick={add}>+ Add an activity</button>
    </div>
  )
}

/** Whether Escape has something of this editor's to close first: an open
 *  finder, then an activity's details. Asked by the editor's own Escape. */
export function closeInner(root: HTMLElement | null): boolean {
  const done = root?.querySelector<HTMLButtonElement>('.ba-acts [data-finder-done]')
  if (done) { done.click(); return true }
  const fewer = root?.querySelector<HTMLButtonElement>('.ba-acts [data-act-detail][aria-expanded="true"]')
  if (fewer && root?.querySelector('.ba-acts')?.contains(document.activeElement)) { fewer.click(); fewer.focus(); return true }
  return false
}

/** A writing area that grows with what is written. */
export function Grow({ id, value, onChange, small, label, rows = 2, onKeyDown, onBlur, autoFocus }: {
  id?: string; value: string; onChange: (v: string) => void; small?: boolean; label?: string; rows?: number
  onKeyDown?: (e: React.KeyboardEvent<HTMLTextAreaElement>) => void; onBlur?: () => void; autoFocus?: boolean
}) {
  const fit = (el: HTMLTextAreaElement | null) => { if (!el) return; el.style.height = 'auto'; el.style.height = `${el.scrollHeight + 2}px` }
  return <textarea id={id} ref={fit} aria-label={label} rows={small ? 1 : rows} className={small ? 'ba-small' : undefined} value={value} autoFocus={autoFocus}
    onChange={(e) => { onChange(e.target.value); fit(e.currentTarget) }} onKeyDown={onKeyDown} onBlur={onBlur} />
}
