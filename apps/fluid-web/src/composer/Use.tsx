import { useEffect, useMemo, useRef, useState } from 'react'
import { Floating } from '../bits'
import { read, useApi, type Id } from '../api'
import { useFloatingPlacement } from '../pop'
import { runnable, type ExecutionInfo } from './execution'

/* ------------------------------------------------------------------------ *
 * "USE…": NAMING THE GOVERNED MATERIAL THIS WORK IS DONE UNDER.
 *
 * WHAT IT IS. A request can carry `governed` -- references to standing
 * procedural material -- and every run of it is composed against what stands
 * when it runs. Asking somebody could carry it and the composer had no way to
 * say it; this is that way. It records nothing by itself: the ids ride on the
 * Turn's request and the server checks them.
 *
 * WHAT IS OFFERED, BY DECLARATION AND NEVER BY NAME. Rows come from the
 * governed register, standing only, and are kept where the row says its Kind
 * DIRECTS WORK (`governs`, i.e. `knowing: "how"`). Kinds whose authoring door
 * is a Persona are left out: a Persona is chosen per person in the dispatch
 * panel, because it is who the work is done as, not material it is done under.
 * Nothing here names a Kind, so a Kind added later -- a discipline, a
 * workflow -- appears here the moment its definition says it directs work.
 *
 * NOTHING IS HOVER-ONLY. Each row is a button with its words in it, the
 * preview is a button, and the sheet is ordinary tab order.
 * ------------------------------------------------------------------------ */

interface Row {
  entry: Id
  kind: string
  summary: string
  secondary?: string
  governs?: boolean
  placed_at?: { conversation: Id; name: string | null; whole_brain?: boolean }[]
}

interface Governed {
  groups: Record<string, Row[]>
  omitted: Record<string, number>
}

interface Authoring {
  kinds: { kind: string; form?: unknown; authoring: null | { door: string; section_label?: string | null } }[]
}

/** WHAT NAMING A PROCEDURE WOULD SET GOING, as `/api/entries/<id>/activities`
 *  reads it from the record. Nothing in it is granted or scheduled. */
interface Named { entry: Id; name: string | null; held: boolean; stands: boolean }
export interface Procedure {
  entry: Id
  name: string
  about: string
  stands: boolean
  carrier: Named | null
  persona: Named | null
  activities: {
    key: string
    what: string
    who: { role: string; persona: Named | null; participant: Named | null }
    /** the version that would reach a child now; `why` when it reaches nobody */
    disciplines: (Named & { pinned?: Id; why?: string | null; requires?: string[] })[]
    done_when: string
    coordinates: boolean
  }[]
  decisions: string[]
  done_when: string
  requires: Record<string, Id[]>
  coordinates: boolean
}

/** Who a procedure is usually carried by, handed to the composer to pre-fill
 *  through the ordinary addressee and its Dispatch row, where the owner sees
 *  and changes it. Never the coordinate grant: that stays the owner's toggle. */
export interface Carry {
  participant?: Id
  alias?: string
  persona?: Id
}

/** Kinds whose `form` declares an `activities` input: a procedure with a
 *  carrier, read by declaration and never by name. */
export function carriesActivities(authoring: Authoring['kinds']): Set<string> {
  return new Set(
    authoring
      .filter((k) =>
        Object.values((k.form && typeof k.form === 'object' ? k.form : {}) as Record<string, { input?: string } | null>).some(
          (f) => !!f && typeof f === 'object' && f.input === 'activities',
        ),
      )
      .map((k) => k.kind),
  )
}

/** The pre-fill a procedure offers: its default carrier and, where it stands,
 *  its default Persona. */
export function carryOf(p: Pick<Procedure, 'carrier' | 'persona'>): Carry | null {
  const persona = p.persona?.held && p.persona.stands ? p.persona.entry : undefined
  if (p.carrier?.held && p.carrier.name) return { participant: p.carrier.entry, alias: p.carrier.name, persona }
  return persona ? { persona } : null
}

interface Context {
  components: { source_kind: string; source_id: Id | null; scope: string; text: string; why: string }[]
  conflicts: { about: string; components: string[] }[]
  withheld: { source_id?: Id | null; why: string }[]
  payload_chars: number
}

export interface UseProps {
  at: HTMLElement | null
  chosen: Id[]
  onChange: (governed: Id[], said: Record<Id, string>) => void
  onClose: () => void
  /** for the preview: where the work would run, who would do it, and what is asked */
  conversation?: Id | null
  participant?: Id | null
  request?: string
  /** pre-fill who carries it, when a chosen procedure names a default */
  onCarry?: (c: Carry) => void
  /** what this machine can run, for checking what a procedure requires */
  execution?: { data: ExecutionInfo | null; loading: boolean; error?: string | null }
  /** whether whoever is marked for work already may coordinate */
  coordinating?: boolean
  /** ask the composer to read what this machine can run (it is not free) */
  onWantExecution?: () => void
}

/** Standing rows whose Kind directs work, without Kinds chosen as Personas. */
export function usable(rows: Row[], authoring: Authoring['kinds']): Row[] {
  const personaDoor = new Set(authoring.filter((k) => k.authoring?.door === 'persona').map((k) => k.kind))
  return rows.filter((r) => r.governs === true && !personaDoor.has(r.kind))
}

export default function Use({ at, chosen, onChange, onClose, conversation, participant, request, onCarry, execution, coordinating, onWantExecution }: UseProps) {
  const pop = useRef<HTMLDivElement>(null)
  const [q, setQ] = useState('')
  const [preview, setPreview] = useState(false)
  useFloatingPlacement(pop, at, 360)
  const kinds = useApi<Authoring>('/api/governance/authoring')
  const got = useApi<Governed>(
    '/api/governed?state=standing&limit=200' + (q.trim() ? '&q=' + encodeURIComponent(q.trim()) : ''),
  )
  const rows = useMemo(
    () => usable(got.data?.groups.standing ?? [], kinds.data?.kinds ?? []),
    [got.data, kinds.data],
  )
  const [said, setSaid] = useState<Record<Id, string>>({})

  useEffect(() => {
    const away = (e: MouseEvent) => {
      const t = e.target as Node
      if (!pop.current?.contains(t) && !at?.contains(t)) onClose()
    }
    const key = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('mousedown', away)
    document.addEventListener('keydown', key)
    return () => {
      document.removeEventListener('mousedown', away)
      document.removeEventListener('keydown', key)
    }
  }, [at, onClose])

  useEffect(() => {
    pop.current?.querySelector('input')?.focus()
  }, [])

  const procedural = useMemo(() => carriesActivities(kinds.data?.kinds ?? []), [kinds.data])
  /* WHICH KIND EACH CHOSEN ITEM IS, remembered past a search that hides it */
  const [seenKinds, setSeenKinds] = useState<Record<Id, string>>({})
  const kindOf = useMemo(
    () => new Map([...Object.entries(seenKinds), ...rows.map((r) => [r.entry, r.kind] as [Id, string])]),
    [rows, seenKinds],
  )
  const toggle = (r: Row) => {
    const adding = !chosen.includes(r.entry)
    setSeenKinds((k) => ({ ...k, [r.entry]: r.kind }))
    const next = adding ? [...chosen, r.entry] : chosen.filter((x) => x !== r.entry)
    const words = { ...said, [r.entry]: r.summary }
    setSaid(words)
    onChange(next, words)
    /* CHOOSING A PROCEDURE PRE-FILLS WHO CARRIES IT, once, at the moment it
       is chosen: the composer shows it as an ordinary addressee the owner can
       open and change. Removing the procedure leaves the addressee alone --
       un-choosing material is not un-asking a person. */
    if (adding && onCarry && procedural.has(r.kind)) {
      read<Procedure>(`/api/entries/${r.entry}/activities`)
        .then((p) => {
          const c = carryOf(p)
          if (c) onCarry(c)
        })
        .catch(() => undefined)
    }
  }

  const params = new URLSearchParams()
  if (conversation) params.set('conversation', conversation)
  if (participant) params.set('participant', participant)
  if (request?.trim()) params.set('request', request.trim())
  chosen.forEach((g) => params.append('behavioural', g))
  const ctx = useApi<Context>(preview ? '/api/context?' + params.toString() : null)

  return (
    <Floating>
      <div className="dispatch use-sheet" ref={pop} role="dialog" aria-label="Use governed material">
        <div className="dispatch-head">
          <b>Use…</b>
          <span>
            {chosen.length ? `${chosen.length} named for this work` : 'name what this work is done under'}
          </span>
        </div>
        <div className="dispatch-row">
          <input
            aria-label="Find governed material"
            placeholder="Find standing material…"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            style={{ width: '100%' }}
          />
          <span className="dispatch-why">
            Standing material whose Kind directs how work is done. It reaches this request only; nothing is placed.
          </span>
        </div>
        <div className="dispatch-rows" aria-label="Governed material to use">
          {got.error && <p role="alert" className="dispatch-why">could not read governed material: {got.error}</p>}
          {!got.data && !got.error && <p className="dispatch-why">Reading the register…</p>}
          {got.data && rows.length === 0 && (
            <p className="dispatch-why">{q.trim() ? 'Nothing standing matches.' : 'Nothing standing directs work in this Brain yet.'}</p>
          )}
          {rows.map((r) => (
            <button
              key={r.entry}
              className={'dispatch-fresh' + (chosen.includes(r.entry) ? ' on' : '')}
              aria-pressed={chosen.includes(r.entry)}
              onClick={() => toggle(r)}
            >
              <span className="faint">{r.kind} · </span>
              {r.summary}
            </button>
          ))}
          {!!got.data?.omitted?.standing && (
            <p className="dispatch-why">More standing material exists than is listed; search to narrow it.</p>
          )}
        </div>
        {chosen
          .filter((g) => procedural.has(kindOf.get(g) ?? ''))
          .map((g) => (
            <WhatHappens key={g} entry={g} execution={execution} coordinating={!!coordinating} onWantExecution={onWantExecution} />
          ))}
        <div className="dispatch-rows">
          <button
            className={'dispatch-fresh' + (preview ? ' on' : '')}
            aria-expanded={preview}
            onClick={() => setPreview(!preview)}
          >
            Preview what it receives
          </button>
          {preview && (
            <div className="use-preview" aria-label="What it receives" style={{ padding: '4px 8px' }}>
              {ctx.error && <p role="alert" className="dispatch-why">{ctx.error}</p>}
              {!ctx.data && !ctx.error && <p className="dispatch-why">Composing…</p>}
              {ctx.data && (
                <>
                  <p className="dispatch-why">
                    {ctx.data.components.length} parts · {ctx.data.payload_chars.toLocaleString()} characters
                    {ctx.data.conflicts.length ? ` · ${ctx.data.conflicts.length} conflict(s) reported` : ''}
                    {participant ? '' : ' · composed for nobody in particular'}
                  </p>
                  <ol style={{ margin: 0, paddingLeft: 18 }}>
                    {ctx.data.components.map((c, i) => (
                      <li key={i} className="dispatch-why">
                        <b>{c.source_kind}</b> — {c.why}
                        {c.source_id && chosen.includes(c.source_id) ? ' (named here)' : ''}: {c.text.slice(0, 140)}
                        {c.text.length > 140 ? '…' : ''}
                      </li>
                    ))}
                  </ol>
                  {ctx.data.withheld
                    .filter((w) => w.source_id && chosen.includes(w.source_id))
                    .map((w) => (
                      <p key={w.source_id!} className="dispatch-why">
                        Withheld {w.source_id}: {w.why}
                      </p>
                    ))}
                </>
              )}
            </div>
          )}
        </div>
      </div>
    </Floating>
  )
}

/** "WHAT WILL HAPPEN" FOR ONE CHOSEN PROCEDURE: who carries it and as what,
 *  its activities with their Disciplines, the decisions reserved to the
 *  owner, and what it and its Disciplines require checked against what this
 *  machine can run. One line that opens -- folded on a phone, open on a desk
 *  -- and every word visible, nothing on hover. It describes; it starts,
 *  grants and schedules nothing. */
function WhatHappens({ entry, execution, coordinating, onWantExecution }: {
  entry: Id
  execution?: UseProps['execution']
  coordinating: boolean
  onWantExecution?: () => void
}) {
  const got = useApi<Procedure>(`/api/entries/${entry}/activities`)
  const needs = Object.keys(got.data?.requires ?? {}).length > 0
  useEffect(() => {
    if (needs) onWantExecution?.()
  }, [needs, onWantExecution])
  const [open, setOpen] = useState(() =>
    typeof window === 'undefined' || !window.matchMedia ? true : !window.matchMedia('(max-width: 600px)').matches,
  )
  const p = got.data
  if (got.error) return <p role="alert" className="dispatch-why">could not read what it sets going: {got.error}</p>
  if (!p) return <p className="dispatch-why">Reading the procedure…</p>
  const caps = Object.keys(p.requires)
  const runtimes = runnable(execution?.data ?? null)
  const on = (cap: string) => runtimes.filter((r) => r.capabilities.includes(cap)).map((r) => r.kind)
  const coordinated = p.activities.filter((a) => a.coordinates).map((a) => a.key)
  /* REQUIREMENTS SELECTION WILL NOT COUNT, said rather than dropped: a
     Discipline that does not stand reaches nobody, so what it requires is not
     asked of a runtime either. */
  const unstanding = p.activities.flatMap((a) => a.disciplines).filter((d) => !d.stands).length
  const uncounted = p.activities.flatMap((a) => a.disciplines).filter((d) => !d.stands && d.requires?.length)
  const who = p.carrier?.name ?? 'whoever you mark for work'
  const as = p.persona?.name ? ` as ${p.persona.name}` : ''
  const n = p.activities.length
  const line =
    `${p.name || 'Procedure'}: ${who}${as} · ${n} activit${n === 1 ? 'y' : 'ies'}` +
    (p.decisions.length ? ` · ${p.decisions.length} owner decision${p.decisions.length === 1 ? '' : 's'}` : '') +
    (caps.length ? ` · requires ${caps.join(', ')}` : '') +
    (unstanding ? ` · ${unstanding} Discipline${unstanding === 1 ? '' : 's'} reach${unstanding === 1 ? 'es' : ''} nobody` : '')
  return (
    <div className="dispatch-rows use-plan" aria-label={`What will happen: ${p.name}`}>
      <button className={'dispatch-fresh' + (open ? ' on' : '')} aria-expanded={open} onClick={() => setOpen(!open)}>
        What will happen — {line}
      </button>
      {open && (
        <div className="use-preview" style={{ padding: '4px 8px' }}>
          {!p.stands && <p className="dispatch-why">Not established: it reaches nobody until it is.</p>}
          <p className="dispatch-why">
            <b>Carried by</b> {p.carrier?.name ?? 'nobody named by default'}
            {p.persona?.name ? `, as ${p.persona.name}` : ''}. Pre-filled on the addressee chip, where you can change
            it; nothing is sent until you send.
          </p>
          <ol style={{ margin: 0, paddingLeft: 18 }} aria-label="Activities">
            {p.activities.map((a) => (
              <li key={a.key} className="dispatch-why">
                <b>{a.key}</b> — {a.what}
                {a.who.participant?.name || a.who.persona?.name || a.who.role
                  ? ` · ${[a.who.participant?.name, a.who.persona?.name && `as ${a.who.persona.name}`, a.who.role].filter(Boolean).join(', ')}`
                  : ''}
                {a.disciplines.length > 0 &&
                  ` · under ${a.disciplines.map((d) => `${d.name ?? d.entry}${d.stands ? '' : ` (${d.why ?? 'does not stand'}: reaches nobody)`}`).join(', ')}`}
                {a.done_when ? ` · done when ${a.done_when}` : ''}
              </li>
            ))}
          </ol>
          {p.decisions.length > 0 && (
            <p className="dispatch-why">
              <b>Decisions reserved to you</b>: {p.decisions.join(' · ')}. The carrier asks them; it never makes them.
            </p>
          )}
          {p.done_when && (
            <p className="dispatch-why">
              <b>Done when</b> {p.done_when}
            </p>
          )}
          {caps.length > 0 && (
            <p className="dispatch-why" aria-label="Requires">
              <b>Requires</b>:{' '}
              {caps
                .map((c) =>
                  execution?.data
                    ? on(c).length
                      ? `${c} (on ${on(c).join(', ')})`
                      : `${c} (no runtime on this machine declares it; the work would be refused before it starts)`
                    : `${c} (${execution?.loading ? 'checking this machine…' : 'not checked against this machine'})`,
                )
                .join(' · ')}
            </p>
          )}
          {uncounted.length > 0 && (
            <p className="dispatch-why" role="note">
              Not counted, because the Discipline does not stand:{' '}
              {uncounted.map((d) => `${d.name ?? d.entry} would require ${d.requires!.join(', ')}`).join(' · ')}.
            </p>
          )}
          {coordinated.length > 0 && !coordinating && (
            <p className="dispatch-why" role="note">
              {coordinated.join(', ')} take{coordinated.length === 1 ? 's' : ''} the coordinate grant (such as picking up
              discovered work). It is not granted for you: turn on “May coordinate this work” on the carrier chip if you
              want it.
            </p>
          )}
        </div>
      )}
    </div>
  )
}
