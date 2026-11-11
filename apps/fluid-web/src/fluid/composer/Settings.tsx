/* HOW THE ADDRESSED PERSON'S WORK RUNS, opened from their chip (#442 #4:
 * "selected runtimes also need their settings so the user can set the
 * runtime, persona and other capabilities").
 *
 * PRODUCTION'S DISPATCH LOGIC, A FLUID PRESENTATION. The rows and their
 * rules are production's Dispatch.tsx: nothing is required and every row's
 * first choice is "let it decide", which is a real answer; changing the
 * runtime drops a model chosen under another one, and the model drops an
 * effort from another model's vocabulary; whether it runs at all comes first
 * because it is the one with a cost. Each runtime says what it has left. */

import { useEffect, useState, type ReactNode } from 'react'
import { OPTIONAL, type Addressee } from '../../composer/draft'
import { EXECUTION_MODES, modelSays, runnable, type ExecutionInfo, type ExecutionMode, type RuntimeCapacity } from '../../composer/execution'
import { getJson } from '../conversation/facts'
import { whereOf, type Declared } from './words'
import { GRAVITY_TIP, followUpOf, gravityWords } from '../runs/gravity'
import { APPROVE_ALL_RISK, CONSENT_MODES, CONSENT_TIP, notAbsolute, workspacesOf } from '../runs/consent'
import Meters from './Meters'
import { EXECUTION_TIP, EXECUTION_WORDS, acceptUnrestricted, ackIsCurrent, availability, chooseExecution, effectiveExecution,
  fitExecution, modesFor } from './execmode'
import { personaOptions, unsetPersonaWords } from './designation'
import type { DesignatedPersona, Id, WhoRead } from '../../api'

interface PersonaChoice { persona: string; name: string; behaviour: string }

let personasHeld: PersonaChoice[] | null = null

/** A Persona's name by its id, for the addressee's chip (it said "persona"):
 *  read once something on screen has one chosen, as Settings reads them. */
export function usePersonaNames(want: boolean): (id: string) => string | null {
  const [, heard] = useState(0)
  useEffect(() => {
    if (!want || personasHeld) return
    let live = true
    void getJson<{ personas: PersonaChoice[] }>('/api/personas')
      .then((r) => { personasHeld = r.personas; if (live) heard((n) => n + 1) })
      .catch(() => {})
    return () => { live = false }
  }, [want])
  return (id) => personasHeld?.find((p) => p.persona === id)?.name ?? null
}

/* WHAT EACH ADDRESSEE'S DESIGNATED PERSONA IS, from `/api/who/<id>`
   (`designated_persona`): read once per name on the page, and again whenever
   its Settings open, since the owner may designate one at any moment. A name
   whose read fails or whose server does not say has no designation shown,
   which keeps the old words -- never a guessed Persona. */
const designationsHeld = new Map<Id, DesignatedPersona | null>()
const designationHeard = new Set<() => void>()
function readDesignation(participant: Id): Promise<void> {
  return getJson<WhoRead>('/api/who/' + encodeURIComponent(participant))
    .then((w) => { designationsHeld.set(participant, w.designated_persona ?? null) })
    .catch(() => { if (!designationsHeld.has(participant)) designationsHeld.set(participant, null) })
    .then(() => { for (const fn of [...designationHeard]) fn() })
}

/** Read a participant's designation again, now: the participant page calls it
 *  after the owner changes one, so the composer never says a stale Persona
 *  (found by the independent review). */
export function rereadDesignation(participant: Id): Promise<void> {
  return readDesignation(participant)
}

/** Each addressee's designated Persona by participant id, read for the
 *  names given (the addressees asked to work). */
export function useDesignations(participants: Id[]): (participant: Id) => DesignatedPersona | null {
  const [, heard] = useState(0)
  const key = participants.join(' ')
  useEffect(() => {
    const fn = () => heard((n) => n + 1)
    designationHeard.add(fn)
    for (const p of participants) if (!designationsHeld.has(p)) void readDesignation(p)
    return () => { designationHeard.delete(fn) }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key])
  return (p) => designationsHeld.get(p) ?? null
}

export default function Settings({ who, declared, onChange, execution, capacity }: {
  who: Addressee
  declared: Declared[]
  onChange: (next: Addressee) => void
  execution: { data: ExecutionInfo | null; loading: boolean; error?: string | null }
  capacity: { data: { capacity: Record<string, RuntimeCapacity> } | null; loading: boolean; error?: string | null }
}) {
  const [personas, setPersonas] = useState<PersonaChoice[] | null>(personasHeld)
  const [why, setWhy] = useState<string | null>(null)
  useEffect(() => {
    /* Asked on opening: a Persona can be defined at any moment. */
    let live = true
    void getJson<{ personas: PersonaChoice[] }>('/api/personas')
      .then((r) => { personasHeld = r.personas; if (live) setPersonas(r.personas) })
      .catch((e: Error) => live && setWhy(e.message))
    return () => { live = false }
  }, [])
  const designationOf = useDesignations([who.participant])
  useEffect(() => { void readDesignation(who.participant) }, [who.participant])
  const designated = designationOf(who.participant)
  const personaName = (id: Id) => personas?.find((p) => p.persona === id)?.name ?? null
  const runtimes = runnable(execution.data)
  const rt = runtimes.find((r) => r.kind === who.runtime)
  const model = rt?.models.find((m) => m.slug === who.model)
  const w = whereOf(who, declared)
  /* A mode the newly chosen runtime cannot run in is cleared, and why is
     said here until the next runtime change. */
  const [cleared, setCleared] = useState<string | null>(null)
  return (
    <div className="fc-settings">
      <div className="fc-shead"><b>{who.alias}</b><span>{who.dispatch ? 'will be asked to work' : 'addressed only'}</span></div>
      <button className={'fc-toggle' + (who.dispatch ? ' on' : '')} aria-pressed={who.dispatch}
        onClick={() => onChange({ ...who, dispatch: !who.dispatch })}>
        {who.dispatch ? 'Sending this starts work' : 'Sending this only addresses them'}
      </button>
      {who.dispatch && (
        <>
          <Row label="runtime"
            why={execution.loading ? 'looking for runtimes on this machine' : execution.error ? 'could not ask this machine: ' + execution.error : runtimes.length === 0 ? 'no runtime is installed on this machine' : null}
            chosen={who.runtime} unset={w.said === 'default' ? `their default (${w.runtime})` : 'let Mentis decide'}
            options={runtimes.map((r) => ({ key: r.kind, label: r.kind, note: r.version ?? undefined }))}
            onPick={(runtime) => {
              const next = { ...who, runtime, model: undefined, effort: undefined }
              const fit = fitExecution(next, whereOf(next, declared).runtime, execution.data)
              setCleared(fit.cleared)
              onChange(fit.who)
            }} />
          {(who.runtime ?? w.runtime) && (
            <div className="fc-srow fc-scap">
              <span className="fc-slabel">capacity</span>
              <Meters runtime={who.runtime ?? w.runtime!} capacity={capacity.data?.capacity?.[who.runtime ?? w.runtime!]} loading={capacity.loading} failed={!!capacity.error} />
            </div>
          )}
          {rt && (
            <Row label="model" why={rt.models.length === 0 ? rt.models_why_not ?? 'no models reported' : null}
              chosen={who.model} unset="the runtime's default"
              options={rt.models.map((m) => ({ key: m.slug, label: m.name, note: modelSays(m, rt.kind) }))}
              onPick={(m) => onChange({ ...who, model: m, effort: undefined })} />
          )}
          {model && model.efforts.length > 0 && (
            <Row label="effort" why={null} chosen={who.effort} unset="the model's default"
              options={model.efforts.map((e) => ({ key: e, label: e, note: e === model.default_effort ? 'default' : undefined }))}
              onPick={(e) => onChange({ ...who, effort: e })} />
          )}
          <Row label="persona"
            why={why ? 'could not read the Personas: ' + why : personas === null ? 'looking for Personas' : personas.length === 0 ? 'no Persona has been defined yet' : null}
            chosen={who.persona} unset={unsetPersonaWords(designated, personaName)}
            options={personaOptions(designated, personas ?? [], who.persona)}
            onPick={(p) => onChange({ ...who, persona: p })} />
          <div className="fc-stoggles">
            <button className={'fc-toggle' + (who.newInstance ? ' on' : '')} aria-pressed={!!who.newInstance}
              onClick={() => onChange({ ...who, newInstance: !who.newInstance })}>
              {who.newInstance ? 'A fresh instance, with no history' : 'Reuse the instance already running, if there is one'}
            </button>
            <button className={'fc-toggle' + (who.coordinate ? ' on' : '')} aria-pressed={!!who.coordinate}
              title="Grants this request authority to coordinate: summon, open places, propose, answer. It does not carry over to their next request."
              onClick={() => onChange({ ...who, coordinate: !who.coordinate })}>
              {who.coordinate ? 'May coordinate this work' : 'Does this work only'}
            </button>
            <button className={'fc-toggle' + (who.followUp !== undefined ? ' on' : '')} aria-pressed={who.followUp !== undefined}
              title={GRAVITY_TIP}
              onClick={() => onChange({ ...who, followUp: who.followUp === undefined ? 1 : who.followUp === 1 ? 2 : who.followUp === 2 ? 'unrestricted' : undefined })}>
              {gravityWords(followUpOf(who.followUp))}
            </button>
          </div>
          <ConsentRows who={who} onChange={onChange}
            execution={<ExecutionRows who={who} runtime={w.runtime} info={execution.data} cleared={cleared} onChange={onChange} />} />
        </>
      )}
    </div>
  )
}

function Row({ label, chosen, unset, options, why, onPick }: {
  label: string
  chosen?: string
  unset: string
  options: { key: string; label: string; note?: string }[]
  why: string | null
  onPick: (v?: string) => void
}) {
  return (
    <div className="fc-srow">
      <span className="fc-slabel">{label}</span>
      {why ? <span className="fc-swhy">{why}</span> : (
        <div className="fc-sopts">
          <button aria-pressed={!chosen} className={!chosen ? 'on' : ''} onClick={() => onPick(undefined)}>{unset}</button>
          {options.map((o) => (
            <button key={o.key} aria-pressed={chosen === o.key} className={chosen === o.key ? 'on' : ''} title={o.note} onClick={() => onPick(o.key)}>{o.label}</button>
          ))}
        </div>
      )}
    </div>
  )
}

/* WHICH OPERATIONS NEED ASKING (docs/run-consent.md §1), beside Task Gravity
   and apart from it. Asking is the default and sends nothing; the other two
   name the task's workspaces, and routine work may also take the optional
   categories. The field keeps what is typed and the draft keeps the
   directories it reads, so a half-typed line is never lost. */
function ConsentRows({ who, onChange, execution }: { who: Addressee; onChange: (next: Addressee) => void; execution: ReactNode }) {
  const c = who.consent
  const [typed, setTyped] = useState(() => (c?.workspaces ?? []).join('\n'))
  const bad = c ? notAbsolute(c.workspaces) : []
  return (
    <>
      <div className="fc-srow" title={CONSENT_TIP}>
        <span className="fc-slabel">Permission</span>
        <div className="fc-sopts">
          {CONSENT_MODES.map((m) => {
            const on = (c?.mode ?? 'ask') === m.mode
            return (
              <button key={m.mode} aria-pressed={on} className={(on ? 'on' : '') + (m.mode === 'all' ? ' fc-all' : '')} title={m.mode === 'all' ? APPROVE_ALL_RISK : CONSENT_TIP}
                onClick={() => onChange({ ...who, consent: m.mode === 'ask' ? undefined : { mode: m.mode, workspaces: workspacesOf(typed), extra: c?.extra } })}>
                {m.words}
              </button>
            )
          })}
        </div>
      </div>
      {execution}
      {c?.mode === 'all' && <p className="fc-risk" role="alert">{APPROVE_ALL_RISK}</p>}
      {c && (
        <div className="fc-srow">
          <span className="fc-slabel">within</span>
          <div>
            <textarea className="fc-sarea" rows={2} value={typed} aria-label="the task's workspaces, absolute directories"
              placeholder="Absolute directories, one per line. The request's repository is always included."
              onChange={(ev) => { setTyped(ev.target.value); onChange({ ...who, consent: { ...c, workspaces: workspacesOf(ev.target.value) } }) }}
              onKeyDown={(ev) => { if (ev.key === 'Escape') ev.stopPropagation() }} />
            {bad.length > 0 && <span className="fc-swhy">Not an absolute directory: {bad.join(', ')}</span>}
          </div>
        </div>
      )}
      {c?.mode === 'task' && (
        <div className="fc-srow">
          <span className="fc-slabel">also</span>
          <div className="fc-sopts">
            {OPTIONAL.map((x) => {
              const on = !!c.extra?.includes(x)
              return (
                <button key={x} aria-pressed={on} className={on ? 'on' : ''}
                  title={`Count ${x} as routine for this task; read, edit, test, build, run and git always are`}
                  onClick={() => {
                    const extra = on ? c.extra!.filter((y) => y !== x) : [...(c.extra ?? []), x]
                    onChange({ ...who, consent: { ...c, extra: extra.length ? extra : undefined } })
                  }}>
                  {x}
                </button>
              )
            })}
          </div>
        </div>
      )}
    </>
  )
}

/* EXECUTION MODE (round 3), beside Permission and independent of it.
   Offered only where the runtime catalogue says what this runtime can run in;
   a mode it cannot is shown, not offered, with the server's why. The
   runtime's default is "nothing sent". Unrestricted Host is chosen through
   the server's notice: Accept stores the mode with the notice's id, Cancel
   leaves the mode as it was. Nothing is asked again per command. */
function ExecutionRows({ who, runtime, info, cleared, onChange }: {
  who: Addressee
  runtime: string | null
  info: ExecutionInfo | null
  cleared: string | null
  onChange: (next: Addressee) => void
}) {
  const modes = modesFor(info, runtime)
  const notice = info?.unrestricted_host_notice ?? null
  /* An acceptance of an older notice is asked for again, before sending. */
  const stale = who.executionMode === 'unrestricted-host' && !!notice && !ackIsCurrent(who, info)
  const [asking, setAsking] = useState(stale)
  const [why, setWhy] = useState<string | null>(null)
  if (!modes) return cleared ? <p className="fc-risk fc-swhy" role="status">{cleared}</p> : null
  const eff = effectiveExecution(who, runtime, info)
  const shown: ExecutionMode | undefined = asking ? 'unrestricted-host' : eff?.mode
  const pick = (m: ExecutionMode) => {
    const can = availability(modes, m)
    if (!can.ok) { setWhy(`${EXECUTION_WORDS[m]}: ${can.why}`); return }
    setWhy(null)
    if (m === 'unrestricted-host') { if (!(eff?.mode === m && ackIsCurrent(who, info))) setAsking(true); return }
    setAsking(false)
    onChange(chooseExecution(who, m, modes))
  }
  return (
    <>
      <div className="fc-srow" title={EXECUTION_TIP}>
        <span className="fc-slabel">Execution</span>
        <div className="fc-sopts" role="group" aria-label="Execution Mode">
          {EXECUTION_MODES.map((m) => {
            const can = availability(modes, m)
            const on = shown === m
            const st = modes.modes[m]
            return (
              <button key={m} aria-pressed={on} aria-disabled={!can.ok || undefined}
                className={(on ? 'on' : '') + (m === 'unrestricted-host' ? ' fc-all' : '') + (can.ok ? '' : ' fc-off')}
                title={can.ok ? [EXECUTION_WORDS[m], st?.mechanism, st?.permission_enforcement].filter(Boolean).join(' — ') : `${EXECUTION_WORDS[m]}: ${can.why}`}
                onClick={() => pick(m)}>
                {EXECUTION_WORDS[m]}{m === modes.default ? ' (default)' : ''}
              </button>
            )
          })}
        </div>
      </div>
      {asking && (
        <div className="fc-notice" role="alertdialog" aria-label="Unrestricted Host">
          <p className="fc-risk">{notice ? notice.text : 'This server gave no notice to accept, so Unrestricted Host cannot be chosen here.'}</p>
          {stale && <p className="fc-swhy">The notice changed since you accepted it.</p>}
          <div className="fc-sopts">
            <button className="on" disabled={!notice} onClick={() => { setAsking(false); if (notice) onChange(acceptUnrestricted(who, notice.id)) }}>Accept</button>
            <button onClick={() => { setAsking(false); if (stale) onChange(chooseExecution(who, modes.default, modes)) }}>Cancel</button>
          </div>
        </div>
      )}
      {(why || cleared) && <p className="fc-risk fc-swhy" role="status">{why ?? cleared}</p>}
      {!asking && eff?.state?.permission_enforcement && <p className="fc-risk fc-swhy">{eff.state.permission_enforcement}</p>}
    </>
  )
}
