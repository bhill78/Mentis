/* OPERATIONS: ONE SETTINGS LIST, AND ONE KIND OF PULL-OUT (Quiet Chat Mark 2,
 * round 3; apps/fluid-web/mockups/quiet-mk2, owner-approved).
 *
 * THE SAME CONTROLS AS Settings.tsx, A DIFFERENT CHROME. Every setting the
 * shared Settings panel offers is here, with the same option sets, the same
 * words and the same transformation of the addressee on each pick: changing
 * the runtime drops a model chosen under another one (and fits the Execution
 * Mode, saying what it cleared), the model drops an effort from another
 * model's vocabulary, Permission Mode carries the typed workspaces, and
 * Unrestricted Host is only ever set through the server's notice. What is new
 * is only how they are laid out: one single-line row per setting -- label,
 * current value, chevron -- and every row opens the same kind of pull-out
 * beside the list, its options in a column, the current one ticked, one click
 * to choose. The list stays visible the whole time.
 *
 * WHERE THE PULL-OUT GOES. 310px wide, to the LEFT of the 380px list, its
 * right edge 10px inside the list's left edge (over the list's own padding),
 * opening at its row's top and shifted up only as far as it must to keep its
 * bottom on the list's bottom edge. Where the window leaves no room to the
 * left it is drawn over the list instead, so it is never off-screen. */

import { useEffect, useLayoutEffect, useRef, useState, type ReactNode } from 'react'
import { OPTIONAL, executionSpec, type Addressee } from '../../composer/draft'
import { EXECUTION_MODES, capacityMeters, capacityWords, modelSays, runnable,
  type ExecutionInfo, type ExecutionMode, type RuntimeCapacity } from '../../composer/execution'
import type { DesignatedPersona, Id } from '../../api'
import { whereOf, type Declared } from './words'
import { GRAVITY_TIP, followUpOf, gravityWords } from '../runs/gravity'
import { APPROVE_ALL_RISK, CONSENT_MODES, CONSENT_TIP, notAbsolute, workspacesOf } from '../runs/consent'
import { EXECUTION_SHORT, EXECUTION_TIP, EXECUTION_WORDS, acceptUnrestricted, ackIsCurrent, availability, chooseExecution,
  effectiveExecution, fitExecution, modesFor, permissionShort } from './execmode'
import { designatedName, personaOptions, personaToken } from './designation'
import { rereadDesignation, useDesignations, usePersonaChoices } from './Settings'
import './operations.css'

const AUTHORITY_TIP = 'Grants this request authority to coordinate: summon, open places, propose, answer. It does not carry over to their next request.'

/* -- the composer's one line: the summary that is the way in --------------- */

export interface SummaryPart { text: string; tone: 'key' | 'plain' | 'warn' }

/** THE SUMMARY ON THE COMPOSER'S ONE LINE: who they work as, where, on what
 *  model -- and Authority, Permission Mode and Execution Mode only where they
 *  differ from their defaults, in the chip's own few words (`tokenOf`'s
 *  "coordinates", `permissionShort`, `EXECUTION_SHORT`), marked as attention.
 *  A model slug that begins with its runtime's name drops that prefix, since
 *  the runtime was just named (`claude · opus-5-5`); any other is left whole. */
export function operationsSummary(a: Addressee, declared: Declared[], personaName?: (id: Id) => string | null,
  designated?: DesignatedPersona | null): SummaryPart[] {
  if (!a.dispatch) return [{ text: 'addressed only', tone: 'plain' }]
  const w = whereOf(a, declared)
  const parts: SummaryPart[] = []
  const persona = personaToken(a.persona, designated, personaName)
  if (persona) parts.push({ text: persona.replace(/ \(designated\)$/, ''), tone: 'key' })
  parts.push({ text: w.runtime ?? 'any runtime', tone: 'plain' })
  if (a.model) parts.push({ text: w.runtime && a.model.startsWith(w.runtime + '-') ? a.model.slice(w.runtime.length + 1) : a.model, tone: 'plain' })
  if (a.effort) parts.push({ text: a.effort, tone: 'plain' })
  if (a.coordinate) parts.push({ text: 'coordinates', tone: 'warn' })
  if (a.consent) parts.push({ text: permissionShort(a.consent.mode), tone: 'warn' })
  /* only a mode the dispatch will carry: an unaccepted Unrestricted Host is not one */
  const chosen = executionSpec(a).execution_mode
  if (chosen) parts.push({ text: EXECUTION_SHORT[chosen], tone: 'warn' })
  return parts
}

/* -- the list ------------------------------------------------------------- */

type RowKey = 'dispatch' | 'persona' | 'runtime' | 'model' | 'effort' | 'instance' | 'authority'
  | 'consent' | 'within' | 'also' | 'gravity' | 'execution'

interface Opt {
  key: string
  name: string
  note?: string
  title?: string
  /** the heading this option sits under, where the catalogue groups them */
  group?: string
  on: boolean
  /** dimmed, not refused: a reading beside it (no capacity left, not available) */
  off?: boolean
  warn?: boolean
  pick: () => void
}

interface Fly {
  title: string
  of?: string
  /** a long option set gets a filter box over a capped, scrolling list */
  filter?: { placeholder: string; label: string; match: (o: Opt, q: string) => boolean }
  opts: Opt[]
  /** why there is nothing to choose (still reading, could not read, none) */
  why?: string | null
  /** the one place a second step is drawn: the notice, the risk, the field */
  extra?: ReactNode
}

interface Row {
  key: RowKey
  label: string
  value: ReactNode
  /** said whole where the value is ellipsised */
  title?: string
  changed?: 'yes' | 'warn'
  /** a rule above it: the groups are what sending does, who and where, and how */
  sep?: boolean
  fly: () => Fly
}

const FLY_WIDTH = 310
const FLY_OVERLAP = 10

export default function Operations({ who, declared, execution, capacity, onChange, onClose }: {
  who: Addressee
  declared: Declared[]
  onChange: (next: Addressee) => void
  onClose: () => void
  execution: { data: ExecutionInfo | null; loading: boolean; error?: string | null }
  capacity: { data: { capacity: Record<string, RuntimeCapacity> } | null; loading: boolean; error?: string | null }
}) {
  const { personas, why: personasWhy } = usePersonaChoices()
  const designationOf = useDesignations([who.participant])
  useEffect(() => { void rereadDesignation(who.participant) }, [who.participant])
  const designated = designationOf(who.participant)
  const personaName = (id: Id) => personas?.find((p) => p.persona === id)?.name ?? null
  const info = execution.data
  const runtimes = runnable(info)
  const rt = runtimes.find((r) => r.kind === who.runtime)
  const model = rt?.models.find((m) => m.slug === who.model)
  const w = whereOf(who, declared)
  const caps = capacity.data?.capacity ?? {}

  /* Settings' own local state, kept here for the same reasons: what the
     runtime change cleared, the typed workspaces (a half-typed line is never
     lost), and the Unrestricted Host notice being asked. */
  const [cleared, setCleared] = useState<string | null>(null)
  const c = who.consent
  const [typed, setTyped] = useState(() => (c?.workspaces ?? []).join('\n'))
  const modes = modesFor(info, w.runtime)
  const notice = info?.unrestricted_host_notice ?? null
  const stale = who.executionMode === 'unrestricted-host' && !!notice && !ackIsCurrent(who, info)
  const [asking, setAsking] = useState(stale)
  const [execWhy, setExecWhy] = useState<string | null>(null)
  const [open, setOpen] = useState<RowKey | null>(stale ? 'execution' : null)
  const [q, setQ] = useState('')

  const list = useRef<HTMLUListElement>(null)
  const flyBox = useRef<HTMLElement>(null)
  const rowsAt = useRef<Partial<Record<RowKey, HTMLButtonElement | null>>>({})
  const [place, setPlace] = useState<{ top: number; beside: boolean } | null>(null)

  const close = (key: RowKey | null = open) => {
    setOpen(null); setQ(''); setPlace(null)
    if (key) rowsAt.current[key]?.focus()
  }
  const toggle = (key: RowKey) => { if (open === key) close(key); else { setOpen(key); setQ(''); setPlace(null) } }
  /* One click chooses, closes the pull-out and updates the row. */
  const choose = (next: Addressee) => { onChange(next); close() }

  /* -- each row, from the same option sets Settings offers ----------------- */
  const rows: Row[] = []
  rows.push({
    key: 'dispatch', label: 'Sending this', value: who.dispatch ? 'Starts work' : 'Only addresses them',
    fly: () => ({
      title: 'Sending this', opts: [
        { key: 'work', name: 'Sending this starts work', on: who.dispatch, pick: () => choose({ ...who, dispatch: true }) },
        { key: 'address', name: 'Sending this only addresses them', on: !who.dispatch, pick: () => choose({ ...who, dispatch: false }) },
      ],
    }),
  })
  if (who.dispatch) {
    const dName = designatedName(designated, personaName)
    const personaOpts = personaOptions(designated, personas ?? [], who.persona)
    const personaChosen = who.persona ? personaOpts.find((o) => o.key === who.persona)?.label ?? personaName(who.persona) ?? who.persona : null
    rows.push({
      key: 'persona', label: 'As', sep: true, changed: who.persona ? 'yes' : undefined,
      value: personaChosen ?? (dName ? `${dName} (designated)` : 'as themselves'),
      fly: () => ({
        title: 'As',
        why: personasWhy ? 'could not read the Personas: ' + personasWhy : personas === null ? 'looking for Personas'
          : personas.length === 0 ? 'no Persona has been defined yet' : null,
        opts: [
          { key: '', name: dName ? `as ${dName} (designated)` : 'as themselves', note: 'nothing chosen', on: !who.persona,
            pick: () => choose({ ...who, persona: undefined }) },
          ...personaOpts.map((o) => ({ key: o.key, name: o.label, note: o.key === 'none' ? 'explicitly no Persona' : undefined, title: o.note,
            on: who.persona === o.key, pick: () => choose({ ...who, persona: o.key }) })),
        ],
      }),
    })

    const runtimeWhy = execution.loading ? 'looking for runtimes on this machine' : execution.error ? 'could not ask this machine: ' + execution.error
      : runtimes.length === 0 ? 'no runtime is installed on this machine' : null
    const unsetRuntime = w.said === 'default' ? `their default (${w.runtime})` : 'let Mentis decide'
    const effective = who.runtime ?? w.runtime
    const capOf = (kind: string) => capacityWords(caps[kind])?.short ?? null
    const firstCap = (kind: string | null) => (kind ? capOf(kind)?.split(' · ')[0] ?? null : null)
    const out = (kind: string) => { const m = capacityMeters(caps[kind]); return m.length > 0 && m.every((x) => x.left === 0) }
    rows.push({
      key: 'runtime', label: 'Runtime', changed: who.runtime ? 'yes' : undefined,
      value: <>{who.runtime ?? unsetRuntime}{firstCap(effective) && <span className="fc-ops-cap"> · {firstCap(effective)}</span>}</>,
      title: [who.runtime ?? unsetRuntime, effective ? capOf(effective) : null].filter(Boolean).join(' · '),
      fly: () => ({
        title: 'Runtime', of: 'this machine', why: runtimeWhy,
        filter: runtimes.length > 7 ? { placeholder: 'Filter runtimes…', label: 'filter runtimes', match: (o, s) => o.key.toLowerCase().includes(s) } : undefined,
        opts: [
          { key: '', name: unsetRuntime, note: 'nothing chosen', on: !who.runtime, pick: () => pickRuntime(undefined) },
          ...runtimes.map((r) => ({ key: r.kind, name: r.kind, note: capOf(r.kind) ?? r.version ?? undefined, title: r.version ?? undefined,
            off: out(r.kind), on: who.runtime === r.kind, pick: () => pickRuntime(r.kind) })),
        ],
      }),
    })
    if (rt) {
      const modelWhy = rt.models.length === 0 ? rt.models_why_not ?? 'no models reported' : null
      /* GROUPED BY WHO SERVES THE MODEL, where the catalogue says so. Round
         3's mockup grouped a SAMPLE by model family; a family read off a slug
         would be this interface inventing a grouping and mis-filing anything
         whose name does not parse (`gpt-oss-120b`, `qwen3.5:9b`). `provider`
         is the grouping the server actually reports, and the picking-relevant
         one -- it is the distinction an owner already lost twenty minutes to
         (execution.ts `modelSays`). A catalogue where no model declares a
         provider stays one flat list. */
      const grouped = rt.models.some((m) => m.provider)
      rows.push({
        key: 'model', label: 'Model', changed: who.model ? 'yes' : undefined,
        value: modelWhy ?? who.model ?? "the runtime's default", title: modelWhy ?? who.model ?? undefined,
        fly: () => ({
          title: 'Model', of: rt.kind, why: modelWhy,
          filter: { placeholder: 'Filter models…', label: 'filter models',
            match: (o, s) => !o.key || [o.key, o.note ?? '', ...(rt.models.find((m) => m.slug === o.key)?.aliases ?? [])].some((x) => x.toLowerCase().includes(s)) },
          opts: [
            { key: '', name: "the runtime's default", note: 'nothing chosen', on: !who.model, pick: () => choose({ ...who, model: undefined, effort: undefined }) },
            /* THE SLUG IS THE NAME -- it is what is sent, and the pull-out is
               where the whole of it is read. The note beside it is a real
               field: the aliases that also reach this model, else the
               catalogue's own display name where it differs from the slug. */
            ...rt.models.map((m) => ({ key: m.slug, name: m.slug, group: grouped ? modelSays(m, rt.kind) : undefined,
              note: m.aliases?.length ? `alias ${m.aliases.join(', ')}` : m.name !== m.slug ? m.name : undefined,
              title: `${m.name} · ${modelSays(m, rt.kind)}`,
              on: who.model === m.slug, pick: () => choose({ ...who, model: m.slug, effort: undefined }) })),
          ],
        }),
      })
    }
    if (model && model.efforts.length > 0) {
      rows.push({
        key: 'effort', label: 'Effort', changed: who.effort ? 'yes' : undefined, value: who.effort ?? "the model's default",
        fly: () => ({
          title: 'Effort', of: model.slug, opts: [
            { key: '', name: "the model's default", on: !who.effort, pick: () => choose({ ...who, effort: undefined }) },
            ...model.efforts.map((e) => ({ key: e, name: e, note: e === model.default_effort ? 'default' : undefined,
              on: who.effort === e, pick: () => choose({ ...who, effort: e }) })),
          ],
        }),
      })
    }
    rows.push({
      key: 'instance', label: 'Instance', changed: who.newInstance ? 'yes' : undefined,
      value: who.newInstance ? 'A fresh instance' : 'Reuse the one running',
      fly: () => ({
        title: 'Instance', opts: [
          { key: 'reuse', name: 'Reuse the instance already running', note: 'if there is one', on: !who.newInstance, pick: () => choose({ ...who, newInstance: false }) },
          { key: 'fresh', name: 'A fresh instance, with no history', on: !!who.newInstance, pick: () => choose({ ...who, newInstance: true }) },
        ],
      }),
    })
    rows.push({
      key: 'authority', label: 'Authority', sep: true, changed: who.coordinate ? 'warn' : undefined,
      value: who.coordinate ? 'May coordinate this work' : 'Does this work only', title: AUTHORITY_TIP,
      fly: () => ({
        title: 'Authority', opts: [
          { key: 'only', name: 'Does this work only', on: !who.coordinate, pick: () => choose({ ...who, coordinate: false }) },
          { key: 'coordinate', name: 'May coordinate this work', note: 'this request only', title: AUTHORITY_TIP, on: !!who.coordinate,
            pick: () => choose({ ...who, coordinate: true }) },
        ],
      }),
    })
    const consentMode = c?.mode ?? 'ask'
    const consentWords = CONSENT_MODES.find((m) => m.mode === consentMode)?.words ?? 'Ask for permission'
    rows.push({
      key: 'consent', label: 'Permission Mode', title: CONSENT_TIP, changed: consentMode !== 'ask' ? 'warn' : undefined,
      value: consentWords.replace(/ \(.*\)$/, ''),
      fly: () => ({
        title: 'Permission Mode',
        opts: CONSENT_MODES.map((m) => {
          const [, name, note] = /^(.*?)(?: \((.*)\))?$/.exec(m.words) ?? [m.words, m.words, undefined]
          return { key: m.mode, name, note: note ?? (m.mode === 'ask' ? 'the default' : m.mode === 'all' ? 'nothing is asked' : undefined),
            title: m.mode === 'all' ? APPROVE_ALL_RISK : CONSENT_TIP, warn: m.mode === 'all', on: consentMode === m.mode,
            pick: () => {
              const next = { ...who, consent: m.mode === 'ask' ? undefined : { mode: m.mode as 'task' | 'deny' | 'all', workspaces: workspacesOf(typed), extra: c?.extra } }
              /* Approve All stays open on its risk, which is said wherever it is chosen. */
              if (m.mode === 'all') onChange(next); else choose(next)
            } }
        }),
        extra: c?.mode === 'all' ? <p className="fc-ops-risk" role="alert">{APPROVE_ALL_RISK}</p> : null,
      }),
    })
    if (c) {
      const dirs = c.workspaces.length
      const bad = notAbsolute(c.workspaces)
      rows.push({
        key: 'within', label: 'Within', changed: dirs ? 'yes' : undefined,
        value: dirs ? `${dirs} director${dirs === 1 ? 'y' : 'ies'}` : "the request's repository", title: c.workspaces.join('\n') || undefined,
        fly: () => ({
          title: 'Within', opts: [],
          extra: <div className="fc-ops-within">
            <textarea className="fc-sarea" rows={4} value={typed} aria-label="the task's workspaces, absolute directories" autoFocus
              placeholder="Absolute directories, one per line. The request's repository is always included."
              onChange={(ev) => { setTyped(ev.target.value); onChange({ ...who, consent: { ...c, workspaces: workspacesOf(ev.target.value) } }) }} />
            {bad.length > 0 && <p className="fc-ops-why">Not an absolute directory: {bad.join(', ')}</p>}
          </div>,
        }),
      })
    }
    if (c?.mode === 'task') {
      rows.push({
        key: 'also', label: 'Also', changed: c.extra?.length ? 'yes' : undefined, value: c.extra?.length ? c.extra.join(', ') : 'nothing more',
        fly: () => ({
          title: 'Also',
          opts: OPTIONAL.map((x) => {
            const on = !!c.extra?.includes(x)
            return { key: x, name: x, on, title: `Count ${x} as routine for this task; read, edit, test, build, run and git always are`,
              pick: () => {
                const extra = on ? c.extra!.filter((y) => y !== x) : [...(c.extra ?? []), x]
                onChange({ ...who, consent: { ...c, extra: extra.length ? extra : undefined } })
              } }
          }),
        }),
      })
    }
    const depth = (v: number | 'unrestricted' | undefined) => gravityWords(followUpOf(v))
    rows.push({
      key: 'gravity', label: 'Side work', title: GRAVITY_TIP, changed: who.followUp !== undefined ? 'yes' : undefined, value: depth(who.followUp),
      fly: () => ({
        title: 'Side work',
        opts: ([undefined, 1, 2, 'unrestricted'] as const).map((v) => ({ key: String(v), name: depth(v), title: GRAVITY_TIP,
          on: who.followUp === v, pick: () => choose({ ...who, followUp: v }) })),
      }),
    })
    if (modes) {
      const eff = effectiveExecution(who, w.runtime, info)
      const shown: ExecutionMode | undefined = asking ? 'unrestricted-host' : eff?.mode
      const pickMode = (m: ExecutionMode) => {
        const can = availability(modes, m)
        if (!can.ok) { setExecWhy(`${EXECUTION_WORDS[m]}: ${can.why}`); return }
        setExecWhy(null)
        if (m === 'unrestricted-host') { if (!(eff?.mode === m && ackIsCurrent(who, info))) setAsking(true); else close(); return }
        setAsking(false)
        choose(chooseExecution(who, m, modes))
      }
      rows.push({
        key: 'execution', label: 'Execution Mode', title: EXECUTION_TIP,
        changed: eff?.source === 'selected' ? (eff.mode === 'unrestricted-host' ? 'warn' : 'yes') : undefined,
        value: eff ? EXECUTION_WORDS[eff.mode] : '',
        fly: () => ({
          title: 'Execution Mode', of: w.runtime ?? undefined,
          opts: EXECUTION_MODES.map((m) => {
            const can = availability(modes, m)
            const st = modes.modes[m]
            return { key: m, name: EXECUTION_WORDS[m], on: shown === m, off: !can.ok, warn: m === 'unrestricted-host' && can.ok,
              note: m === modes.default ? 'default' : can.ok ? st?.mechanism ?? undefined : can.why ?? undefined,
              title: can.ok ? [EXECUTION_WORDS[m], st?.mechanism, st?.permission_enforcement].filter(Boolean).join(' — ') : `${EXECUTION_WORDS[m]}: ${can.why}`,
              pick: () => pickMode(m) }
          }),
          extra: <>
            {asking && (
              <div className="fc-ops-notice" role="alertdialog" aria-label="Unrestricted Host">
                <p>{notice ? notice.text : 'This server gave no notice to accept, so Unrestricted Host cannot be chosen here.'}</p>
                {stale && <p className="fc-ops-why">The notice changed since you accepted it.</p>}
                <div className="fc-ops-acts">
                  <button type="button" className="fc-ops-accept" disabled={!notice}
                    onClick={() => { setAsking(false); if (notice) choose(acceptUnrestricted(who, notice.id)) }}>Accept</button>
                  <button type="button" className="fc-ops-cancel"
                    onClick={() => { setAsking(false); if (stale) onChange(chooseExecution(who, modes.default, modes)) }}>Cancel</button>
                </div>
              </div>
            )}
            {(execWhy || cleared) && <p className="fc-ops-why" role="status">{execWhy ?? cleared}</p>}
            {!asking && eff?.state?.permission_enforcement && <p className="fc-ops-enforce">{eff.state.permission_enforcement}</p>}
          </>,
        }),
      })
    }
  }

  function pickRuntime(runtime: string | undefined) {
    const next = { ...who, runtime, model: undefined, effort: undefined }
    const fit = fitExecution(next, whereOf(next, declared).runtime, info)
    setCleared(fit.cleared)
    choose(fit.who)
  }

  const shownRow = rows.find((r) => r.key === open)
  const fly = shownRow?.fly() ?? null
  const needle = q.trim().toLowerCase()
  const opts = fly ? (fly.filter && needle ? fly.opts.filter((o) => o.key !== '' && fly.filter!.match(o, needle)) : fly.opts) : []
  const counted = fly?.opts.filter((o) => o.key !== '').length ?? 0
  const matched = opts.filter((o) => o.key !== '').length

  /* A row that is no longer offered (the runtime was cleared, so no model)
     takes its pull-out with it. */
  useEffect(() => { if (open && !shownRow) close(null) })

  /* PLACING THE PULL-OUT: at its row's top, clamped to the list's bottom,
     beside the list where the window has room, over it where it has not. */
  useLayoutEffect(() => {
    const el = flyBox.current
    const row = open ? rowsAt.current[open] : null
    const panel = el?.offsetParent as HTMLElement | null
    if (!el || !row || !panel) return
    const measure = () => {
      const p = panel.getBoundingClientRect(), r = row.getBoundingClientRect()
      const h = el.offsetHeight
      const top = Math.round(Math.max(8 - p.top, Math.min(r.top - p.top, p.height - h)))
      const beside = p.left >= FLY_WIDTH - FLY_OVERLAP + 8
      setPlace((was) => (was && was.top === top && was.beside === beside ? was : { top, beside }))
    }
    measure()
    const watch = new ResizeObserver(measure)
    watch.observe(el)
    window.addEventListener('resize', measure)
    return () => { watch.disconnect(); window.removeEventListener('resize', measure) }
  }, [open, opts.length])

  /* Focus: the first row on opening; the filter, else the ticked option, on a pull-out. */
  useEffect(() => { rowsAt.current[open ?? rows[0].key]?.focus() }, []) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (!open || !flyBox.current) return
    const box = flyBox.current
    const target = box.querySelector<HTMLElement>('input, textarea') ?? box.querySelector<HTMLElement>('[aria-checked="true"]') ?? box.querySelector<HTMLElement>('[role="menuitemradio"], [role="menuitemcheckbox"]')
    target?.focus()
  }, [open])

  /* ESC CLOSES THE PULL-OUT FIRST. Float closes the whole panel on Escape from
     a document capture listener; this one is on the window, which hears the
     key before the document does, so it can take it while a pull-out is open. */
  useEffect(() => {
    if (!open) return
    const key = (e: KeyboardEvent) => {
      if (e.key !== 'Escape') return
      e.preventDefault(); e.stopPropagation()
      if (asking) { setAsking(false); return }
      close()
    }
    window.addEventListener('keydown', key, true)
    return () => window.removeEventListener('keydown', key, true)
  })

  const rowKeys = (e: React.KeyboardEvent<HTMLUListElement>) => {
    /* THE ROW AND ITS BUTTON TRAVEL TOGETHER. A row no longer offered (no
       model, because the runtime was cleared) leaves a null ref behind, so
       indexing `rows` by a position in the button list opened the wrong
       setting; the pair is carried instead. */
    const all = rows.flatMap((r) => { const b = rowsAt.current[r.key]; return b ? [[r, b] as const] : [] })
    const at = all.findIndex(([, b]) => b === document.activeElement)
    if (at < 0) return
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      e.preventDefault()
      all[(at + (e.key === 'ArrowDown' ? 1 : -1) + all.length) % all.length][1].focus()
    } else if (e.key === 'ArrowRight') {
      e.preventDefault()
      const k = all[at][0].key
      if (open !== k) toggle(k)
    }
  }
  const optKeys = (e: React.KeyboardEvent<HTMLElement>) => {
    const box = e.currentTarget
    const all = [...box.querySelectorAll<HTMLElement>('[role="menuitemradio"], [role="menuitemcheckbox"]')]
    const field = box.querySelector<HTMLInputElement>('input')
    const at = all.indexOf(document.activeElement as HTMLElement)
    if (e.key === 'ArrowLeft' && document.activeElement?.tagName !== 'INPUT' && document.activeElement?.tagName !== 'TEXTAREA') { e.preventDefault(); close(); return }
    if (e.key === 'Enter' && document.activeElement === field) { e.preventDefault(); all[0]?.click(); return }
    if (e.key !== 'ArrowDown' && e.key !== 'ArrowUp') return
    if (document.activeElement?.tagName === 'TEXTAREA') return
    if (!all.length) return
    e.preventDefault()
    const next = e.key === 'ArrowDown' ? (at < 0 ? 0 : Math.min(all.length - 1, at + 1)) : at <= 0 ? -1 : at - 1
    if (next < 0) (field ?? all[0]).focus()
    else all[next].focus()
  }

  const footSaid = !modes && cleared ? cleared : null
  return (
    <div className="fc-ops" data-rows={rows.length}>
      <header className="fc-ops-head">
        <h2>Operations <span>· {who.alias}</span></h2>
        <button type="button" className="fc-ops-close" aria-label="Close Operations" onClick={onClose}>×</button>
      </header>
      <ul ref={list} className="fc-ops-set" aria-label={`Operations for ${who.alias}`} onKeyDown={rowKeys}>
        {rows.map((r) => (
          <li key={r.key} className={r.sep ? 'sep' : undefined}>
            <button type="button" ref={(b) => { rowsAt.current[r.key] = b }} className="fc-ops-row" data-row={r.key}
              data-changed={r.changed} data-open={open === r.key || undefined} aria-haspopup="true" aria-expanded={open === r.key}
              title={r.title} onClick={() => toggle(r.key)}>
              <span className="fc-ops-l">{r.label}</span>
              <span className="fc-ops-v">{r.value}</span>
              <span className="fc-ops-c" aria-hidden="true">›</span>
            </button>
          </li>
        ))}
      </ul>
      {footSaid
        ? <p className="fc-ops-foot fc-ops-said" role="status" title={footSaid}>{footSaid}</p>
        : <p className="fc-ops-foot"><span>↑↓ move</span><span>→ open</span><span>Esc back to writing</span></p>}
      {fly && shownRow && (
        <aside ref={flyBox} className={'fc-ops-fly' + (place && !place.beside ? ' fc-ops-over' : '')} aria-label={fly.title}
          style={{ top: place?.top ?? 0, visibility: place ? undefined : 'hidden' }} onKeyDown={optKeys}>
          <header className="fc-ops-flyhead">{fly.title}{fly.of && <span className="fc-ops-of">{fly.of}</span>}</header>
          {fly.why ? <p className="fc-ops-why fc-ops-pad">{fly.why}</p> : <>
            {fly.filter && (
              <label className="fc-ops-filter">
                <input type="text" value={q} placeholder={fly.filter.placeholder} aria-label={fly.filter.label} spellCheck={false}
                  onChange={(e) => setQ(e.target.value)} />
                <span className="fc-ops-n" aria-live="polite">{needle ? `${matched} of ${counted}` : counted}</span>
              </label>
            )}
            {opts.length > 0 && (
              <ul className={'fc-ops-olist' + (fly.filter ? ' tall' : '')} role="menu" aria-label={fly.title}>
                {opts.map((o, i) => (
                  <li key={o.key || '(unset)'}>
                    {/* the heading only where this option begins a new group,
                        so a filtered list keeps the headings it still has */}
                    {o.group && o.group !== opts[i - 1]?.group && (
                      <p className="fc-ops-ogrp" role="presentation">{o.group}</p>
                    )}
                    <button type="button" role={shownRow.key === 'also' ? 'menuitemcheckbox' : 'menuitemradio'} aria-checked={o.on}
                      className={'fc-ops-o' + (o.on ? ' on' : '') + (o.off ? ' off' : '') + (o.warn ? ' warn' : '')}
                      title={o.title ?? o.note} onClick={o.pick}>
                      <span className="fc-ops-tick" aria-hidden="true">{o.on ? '✓' : ''}</span>
                      <span className="fc-ops-on">{o.name}</span>
                      <span className="fc-ops-note">{o.note ?? ''}</span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
            {fly.filter && needle && matched === 0 && <p className="fc-ops-why fc-ops-pad">Nothing matches “{q.trim()}”.</p>}
          </>}
          {fly.extra}
        </aside>
      )}
    </div>
  )
}
