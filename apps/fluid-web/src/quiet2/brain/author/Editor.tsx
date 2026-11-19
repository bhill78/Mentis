/* THE BRAIN RECORD EDITOR: one surface, used to make a record and to revise
 * one.
 *
 * It opens as a title, the one or two questions that Kind cannot do without,
 * a line saying what Record will do, Cancel and Record. Everything else is
 * behind one "+ Add" and appears only when asked for, or when it is needed to
 * finish. A finished optional part collapses to one line; an empty one goes
 * away. Nothing is validated until Record, and then one thing is said, with
 * the cursor put where it is answered.
 *
 * The compact modal (`AuthorModal`) and the record page's Revise
 * (`BrainRecord`) both draw this, over the same model (`model.ts`): the same
 * controls, the same checks, the same requests. There is no second editor.
 *
 * RECORDING WRITES A PROPOSAL. Nothing here can establish; that is a separate
 * act on the record, and the line beside Record says so. */
import { useEffect, useId, useImperativeHandle, useMemo, useRef, useState, type Ref as ReactRef } from 'react'
import { post, useApi, type Id } from '../../../api'
import type { KindAuthoring } from '../../../surfaces/governance/r2Model'
import { Select, useParticipants, usePersonas } from '../../../surfaces/governance/R2Inputs'
import Activities, { closeInner, Grow } from './Activities'
import Finder, { type Scope } from './Finder'
import {
  askOf, changes, consequence, createSteps, dirty as isDirty, draftFrom, emptyDraft, firstFields, hasValue, inputOf, kindExample, kindNote,
  addedBasis, nameOf, planOf, problem, reviseRequest, summaryOf,
  type Draft, type Problem, type Ref, type Step,
} from './model'

/** What a revision starts from, as the record's own read gives it. */
export interface Revising {
  id: Id
  body: Record<string, unknown>
  basis: Ref[]
  /** what the server says saving would do: `proposed`, `candidate`, `edited` */
  editMode: string | null
  /** how many places the record is placed now */
  placed: number
}

export interface Recorded { id: Id; kind: string; words: string; standingApt: boolean }
export interface Revised { version: Id; mode: string; says: string }

export interface EditorHandle {
  /** Escape: closes the innermost open thing; false where there is none */
  escape: () => boolean
  /** leave, asking first where something would be lost */
  leave: () => void
  dirty: () => boolean
}

/** The evidence a record may rest on: everything the server accepts. */
const EVIDENCE: Scope[] = ['records', 'posts', 'files']

export default function BrainEditor({ mode, k, capabilities, me, seed, revising, here, handle, onCancel, onRecorded, onRevised, onDirty }: {
  mode: 'create' | 'revise'
  k: KindAuthoring
  /** the runtime capability vocabulary, for a field that chooses from it */
  capabilities: string[]
  me: Id | null
  /** what the door that opened this already knows */
  seed?: Partial<Draft>
  revising?: Revising
  /** the conversation the reader is in: offered first, never assumed */
  here?: { id: Id; name: string } | null
  handle?: ReactRef<EditorHandle>
  onCancel: () => void
  onRecorded?: (r: Recorded) => void
  onRevised?: (r: Revised) => void
  onDirty?: (dirty: boolean) => void
}) {
  const plan = useMemo(() => planOf(k, mode), [k, mode])
  const start = useMemo<Draft>(() => (revising ? draftFrom(plan, revising.body, revising.basis) : { ...emptyDraft(), ...seed, fields: firstFields(plan) }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [plan, revising?.id])
  const [d, setD] = useState<Draft>(start)
  const [editing, setEditing] = useState<string | null>(null)
  const [menu, setMenu] = useState(false)
  const [finding, setFinding] = useState<null | 'basis' | 'context' | 'place' | 'conversation'>(null)
  const [diffing, setDiffing] = useState(false)
  const [example, setExample] = useState(false)
  const [err, setErr] = useState<Problem | null>(null)
  const [nudge, setNudge] = useState(0)
  const [busy, setBusy] = useState(false)
  const [asking, setAsking] = useState(false)
  /* a record already made whose later acts did not complete: retried from here */
  /* THE ACTS ARE THE ONES DECIDED WHEN THE RECORD WAS MADE (`steps`), kept
     with it: a retry sends exactly what is left of them, never a list made
     again from a draft that has since been touched. */
  const [made, setMade] = useState<{ id: Id; done: number; steps: Step[] } | null>(null)
  const root = useRef<HTMLElement>(null)
  const addBtn = useRef<HTMLButtonElement>(null)
  const title = useId()
  const uid = useId()
  const people = useParticipants([...plan.first, ...plan.optional].some((f) => inputOf(plan, f) === 'participant'))
  const personas = usePersonas([...plan.first, ...plan.optional].some((f) => inputOf(plan, f) === 'persona'))
  const subjects = useApi<{ subjects: { about: string }[] }>(d.open.includes('about') && k.authoring?.door !== 'persona' ? '/api/governance/subjects' : null)
  const names = useMemo(() => Object.fromEntries([...people, ...personas].map((c) => [c.id, c.name])), [people, personas])

  const changed = isDirty(plan, start, d) || !!made
  const telling = useRef(onDirty)
  telling.current = onDirty
  useEffect(() => { telling.current?.(changed); return () => telling.current?.(false) }, [changed])
  /* A RELOAD OR A CLOSED TAB WARNS while something written is unrecorded */
  useEffect(() => {
    if (!changed) return
    const warn = (e: BeforeUnloadEvent) => { e.preventDefault(); e.returnValue = '' }
    window.addEventListener('beforeunload', warn)
    return () => window.removeEventListener('beforeunload', warn)
  }, [changed])

  /* FOCUS MOVES AT ONCE: as soon as what was asked for has been drawn, so
     words typed straight after a press land where the press put them. */
  const soon = (go: () => boolean) => queueMicrotask(() => { if (!go()) window.setTimeout(go, 0) })
  const focusPart = (part: string) => soon(() => {
    const el = root.current?.querySelector<HTMLElement>(`[data-part="${part}"]`)
    const to = el?.matches('input,textarea,select,button') ? el : el?.querySelector<HTMLElement>('textarea,input,select,button')
    to?.focus(); to?.scrollIntoView?.({ block: 'nearest' })
    return !!to
  })
  useEffect(() => { focusPart(plan.first[0] ?? '') }, [])  // eslint-disable-line react-hooks/exhaustive-deps

  const set = (patch: Partial<Draft>) => { setD((was) => ({ ...was, ...patch })); setErr(null) }
  const setField = (f: string, v: string) => { setD((was) => ({ ...was, fields: { ...was.fields, [f]: v } })); setErr(null) }
  const openPart = (p: string) => {
    setMenu(false)
    setD((was) => ({ ...was, open: was.open.includes(p) ? was.open : [...was.open, p],
      ...(p === 'place' && !was.place ? { place: { to: plan.placeable ? 'conversation' as const : 'persona' as const, where: plan.placeable ? here?.id ?? '' : '', name: plan.placeable ? here?.name ?? '' : '', reason: '' } } : {}) }))
    if (p === 'basis' || p === 'context') setFinding(p)
    else if (inputOf(plan, p) === 'text' || inputOf(plan, p) === 'line' || p === 'because') setEditing(p)
    if (p !== 'basis' && p !== 'context') focusPart(p)
  }
  const dropPart = (p: string, focus = true) => {
    setD((was) => ({
      ...was, open: was.open.filter((x) => x !== p),
      ...(p === 'basis' ? { basis: [], basisReason: '' } : p === 'context' ? { context: null } : p === 'place' ? { place: null }
        : p === 'because' ? { because: '' } : { fields: { ...was.fields, [p]: '' } }),
    }))
    setErr(null); if (editing === p) setEditing(null)
    if (focus) soon(() => { const to = (addBtn.current ?? root.current?.querySelector<HTMLElement>('textarea,input')); to?.focus(); return !!to })
  }
  /* an optional writing part that is left: one line if it says something, gone if not */
  const settle = (p: string) => {
    const v = p === 'because' ? d.because : d.fields[p] ?? ''
    if (!v.trim()) dropPart(p, false)
    setEditing((e) => (e === p ? null : e))
  }

  /* LEAVING AN OPTIONAL PART COLLAPSES IT, BUT NEVER UNDER A PRESS. A part
     that folded the moment focus left it moved everything below it up between
     the press and the release, so the button being pressed (Record, most
     often) was no longer under the pointer and the press did nothing. While
     the pointer is down the fold waits for the release. */
  const down = useRef(false)
  const waiting = useRef<string | null>(null)
  const settleLive = useRef(settle)
  settleLive.current = settle
  const settleSoon = (p: string) => { if (down.current) waiting.current = p; else settle(p) }
  useEffect(() => {
    const up = () => { down.current = false; const p = waiting.current; waiting.current = null; if (p) window.setTimeout(() => settleLive.current(p), 0) }
    window.addEventListener('pointerup', up); window.addEventListener('pointercancel', up)
    return () => { window.removeEventListener('pointerup', up); window.removeEventListener('pointercancel', up) }
  }, [])

  /* WHAT "+ ADD" STILL OFFERS: every optional part not on screen */
  const offered = [...plan.optional, ...plan.extras].filter((p) => !d.open.includes(p))

  const leave = () => { if (busy) return; if (changed && !made) setAsking(true); else onCancel() }
  const escape = (): boolean => {
    if (asking) { setAsking(false); focusPart(plan.first[0] ?? ''); return true }
    if (menu) { setMenu(false); addBtn.current?.focus(); return true }
    if (finding) { const was = finding; closeFinder(); focusPart(was === 'conversation' ? 'conversation' : was); return true }
    if (closeInner(root.current)) return true
    if (editing && root.current?.querySelector(`[data-part="${editing}"]`)?.contains(document.activeElement)) { const p = editing; settle(p); soon(() => { const to = (root.current?.querySelector<HTMLElement>(`[data-sum="${p}"]`) ?? addBtn.current); to?.focus(); return !!to }); return true }
    if (diffing) { setDiffing(false); return true }
    if (example) { setExample(false); return true }
    return false
  }
  useImperativeHandle(handle, () => ({ escape, leave, dirty: () => changed && !made }))

  const closeFinder = () => {
    const was = finding
    setFinding(null)
    if (was === 'basis' && !d.basis.length && !plan.needsBasis) dropPart('basis', false)
    if (was === 'context' && !d.context) dropPart('context', false)
  }

  const record = async () => {
    if (busy) return
    if (finding) closeFinder()
    if (!me) { setErr({ message: 'An attributed owner is needed to record this.', part: plan.first[0] ?? '' }); return }
    const p = made ? null : problem(plan, k, d, mode, start)
    if (p) {
      setErr(p); setNudge((n) => n + 1)
      if (p.part === 'basisReason' || p.part === 'placeReason') focusPart(p.part)
      else if (p.part === 'because') openPart('because')
      else if (p.part === 'basis' && !plan.needsBasis) { if (!d.open.includes('basis')) openPart('basis'); else focusPart('basis') }
      else if (p.index == null) { if (!plan.first.includes(p.part) && p.part !== 'basis' && p.part !== 'conversation' && p.part !== 'place' && !d.open.includes(p.part)) openPart(p.part); else { if (plan.optional.includes(p.part)) setEditing(p.part); focusPart(p.part) } }
      return
    }
    setBusy(true); setErr(null)
    try {
      if (mode === 'revise' && revising) {
        /* EVIDENCE ADDED AND NOTHING ELSE: there is no new version to write,
           so it is cited on the record as it is (`derive-from`, with its
           reason), which changes no standing. */
        const more = addedBasis(plan, start, d)
        if (more) {
          await post(`/api/entries/${revising.id}/derive-from`, { attributed_to: me, from: more.map((x) => x.ref), because: d.because.trim() })
          telling.current?.(false)
          onRevised?.({ version: revising.id, mode: 'evidence', says: 'Added to what it is based on. Nothing else changed.' })
          return
        }
        const r = await post<Revised>(`/api/entries/${revising.id}/edit`, reviseRequest(plan, start, d, me))
        telling.current?.(false)
        onRevised?.(r)
        return
      }
      const steps = made?.steps ?? createSteps(plan, k, d, me)
      let id: Id | null = made?.id ?? null
      for (let i = made?.done ?? 0; i < steps.length; i++) {
        try {
          const got = await post<{ entry?: Id; persona?: Id }>(steps[i].path(id), steps[i].body)
          if (i === 0) id = got.entry ?? got.persona ?? null
          if (id) setMade({ id, done: i + 1, steps })
        } catch (e) {
          const what = steps[i].name === 'evidence' ? 'what it is based on' : steps[i].name === 'placement' ? 'where it applies' : ''
          setErr({ message: id ? `It was recorded as a proposal, but ${what} was not: ${(e as Error).message} Try again, or open the record.` : (e as Error).message,
            part: steps[i].name === 'evidence' ? 'basis' : steps[i].name === 'placement' ? 'place' : plan.first[0] ?? '' })
          return
        }
      }
      if (id) {
        telling.current?.(false)
        const words = (d.fields[plan.first[0] ?? ''] ?? '').trim() || (d.fields.text ?? '').trim()
        onRecorded?.({ id, kind: k.kind, words, standingApt: k.authoring?.standing_apt === true })
      }
    } catch (e) {
      setErr({ message: (e as Error).message, part: plan.first[0] ?? '' })
    } finally { setBusy(false) }
  }

  /* ---- one field's control: the same whether creating or revising ------ */
  const control = (f: string, opts: { first: boolean }) => {
    const input = inputOf(plan, f)
    const id = `${uid}-${f}`
    const raw = d.fields[f] ?? ''
    if (input === 'activities') return <Activities field={f} value={raw} onChange={(v) => setField(f, v)}
      focusIndex={err?.part === f && err.index != null ? { i: err.index, n: nudge } : null} />
    if (input === 'capabilities') {
      const picked = new Set(raw.split(/\r?\n/).map((x) => x.trim()).filter(Boolean))
      const flip = (c: string) => { const next = new Set(picked); if (next.has(c)) next.delete(c); else next.add(c); setField(f, [...next].join('\n')) }
      /* a capability the record names that the vocabulary no longer lists is
         still shown, so revising never drops it silently */
      const all = [...capabilities, ...[...picked].filter((c) => !capabilities.includes(c))]
      return <fieldset className="ba-checks" data-part={f} aria-label={nameOf(plan, f)}>
        {all.map((c) => <label key={c} className="ba-check"><input type="checkbox" checked={picked.has(c)} onChange={() => flip(c)} />{c}</label>)}
        {!all.length && <span className="ba-none">Reading what can be required…</span>}
      </fieldset>
    }
    if (input === 'participant' || input === 'persona') return <span data-part={f}><Select label={nameOf(plan, f)} value={raw}
      choices={input === 'participant' ? people : personas} none={input === 'participant' ? 'Nobody by default' : 'No persona by default'} onChange={(v) => setField(f, v)} /></span>
    if (input === 'list' || input === 'refs') {
      const items = raw === '' ? [''] : raw.split(/\r?\n/)
      const put = (next: string[]) => setField(f, next.join('\n'))
      return <div className="ba-rows" data-part={f}>
        {items.map((it, i) => <div className="ba-row" key={i}>
          <input type="text" aria-label={`${nameOf(plan, f)} ${i + 1}`} value={it} onChange={(e) => put(items.map((x, j) => (j === i ? e.target.value : x)))}
            onKeyDown={(e) => { if (e.key === 'Enter' && !e.ctrlKey && !e.metaKey) { e.preventDefault(); e.stopPropagation(); put([...items.slice(0, i + 1), '', ...items.slice(i + 1)]); soon(() => { const to = (root.current?.querySelectorAll<HTMLElement>(`[data-part="${f}"] input`)[i + 1]); to?.focus(); return !!to }) } }} />
          {items.length > 1 && <button type="button" className="ba-x" aria-label={`Remove ${nameOf(plan, f)} ${i + 1}`} onClick={() => put(items.filter((_, j) => j !== i))}>✕</button>}
        </div>)}
        <button type="button" className="ba-quiet" onClick={() => { put([...items, '']); soon(() => { const all = root.current?.querySelectorAll<HTMLElement>(`[data-part="${f}"] input`); const to = all?.[all.length - 1] as HTMLInputElement | undefined; to?.focus(); return !!to && to.value === '' }) }}>+ another</button>
      </div>
    }
    const subject = f === 'about' && k.authoring?.door !== 'persona'
    if (input === 'line' || subject) return <>
      <input id={id} data-part={f} type="text" value={raw} list={subject ? `${uid}-subjects` : undefined} onChange={(e) => setField(f, e.target.value)}
        onBlur={opts.first ? undefined : () => window.setTimeout(() => { if (!root.current?.querySelector(`[data-part="${f}"]`)?.matches(':focus')) settleSoon(f) }, 0)}
        onKeyDown={opts.first ? undefined : (e) => { if (e.key === 'Enter' && !e.ctrlKey && !e.metaKey) { e.preventDefault(); e.stopPropagation(); settle(f); soon(() => { const to = (root.current?.querySelector<HTMLElement>(`[data-sum="${f}"]`) ?? addBtn.current); to?.focus(); return !!to }) } }} />
      {subject && <datalist id={`${uid}-subjects`}>{(subjects.data?.subjects ?? []).map((x) => <option key={x.about} value={x.about} />)}</datalist>}
    </>
    return <span data-part={f} className="ba-area"><Grow id={id} value={raw} rows={opts.first && plan.first.length === 1 ? 3 : 2} small={!opts.first}
      onChange={(v) => setField(f, v)}
      onBlur={opts.first ? undefined : () => window.setTimeout(() => { if (!root.current?.querySelector(`[data-part="${f}"]`)?.contains(document.activeElement)) settleSoon(f) }, 0)} /></span>
  }

  const chips = (refs: Ref[], onRemove: (r: Ref) => void) => refs.map((r) => (
    <span className="ba-chip" key={r.ref}><span className="ba-chip-k">{r.kind}</span><span className="ba-chip-t" title={r.label}>{r.label}</span>
      <button type="button" className="ba-x" aria-label={`Remove: ${r.label.slice(0, 50)}`} onClick={() => onRemove(r)}>✕</button></span>
  ))
  const toggleBasis = (r: Ref) => set({ basis: d.basis.some((c) => c.ref === r.ref) ? d.basis.filter((c) => c.ref !== r.ref) : [...d.basis, r] })

  /* ---- what the record is based on ------------------------------------- */
  const basisPart = () => {
    const required = plan.needsBasis
    if (finding === 'basis') return <div className="ba-part" data-part="basis" key="basis">
      <span className="ba-lab">Choose what this is based on</span>
      <Finder label="What this is based on" scopes={EVIDENCE} chosen={d.basis} here={here?.id ?? null} paste onToggle={toggleBasis}
        onDone={() => { closeFinder(); focusPart(d.basis.length || required ? 'basis' : plan.first[0] ?? '') }} />
    </div>
    if (!d.basis.length) return required
      ? <button type="button" key="basis" className={'ba-need' + (err?.part === 'basis' ? ' bad' : '')} data-part="basis" onClick={() => setFinding('basis')}>Choose what this is based on…</button>
      : null
    return <div className="ba-part" key="basis">
      <div className="ba-line"><span className="ba-line-n">Based on</span>
        <div className="ba-line-v">{chips(d.basis, (r) => { const left = d.basis.filter((c) => c.ref !== r.ref); if (!left.length && !required) dropPart('basis'); else { set({ basis: left }); focusPart('basis') } })}
          <button type="button" className="ba-quiet" data-part="basis" onClick={() => setFinding('basis')}>+ another</button></div></div>
      {/* asked only where an act will carry it: a basis the Kind does not
          require is cited with the reason it supports the record */}
      {mode === 'create' && !required && <>
        <label className="ba-lab" htmlFor={`${uid}-why`}>How does this lead to the {plan.title}?</label>
        <span data-part="basisReason" className="ba-area"><Grow id={`${uid}-why`} small value={d.basisReason} onChange={(v) => set({ basisReason: v })} /></span>
      </>}
    </div>
  }

  const placePart = () => {
    const p = d.place
    if (!p) return null
    const choose = (to: 'conversation' | 'persona') => set({ place: { ...p, to, where: to === 'conversation' ? here?.id ?? '' : '', name: to === 'conversation' ? here?.name ?? '' : '' } })
    return <div className="ba-part" key="place" data-part="place">
      <div className="ba-part-head"><span className="ba-lab">Where should it apply once it is in effect?</span>
        <button type="button" className="ba-x" aria-label="Remove where it applies" onClick={() => dropPart('place')}>✕</button></div>
      {plan.placeable && plan.personaPlaceable && <div className="ba-radios" role="radiogroup" aria-label="Where it applies">
        <label className="ba-check"><input type="radio" name={`${uid}-to`} checked={p.to === 'conversation'} onChange={() => choose('conversation')} />In a conversation</label>
        <label className="ba-check"><input type="radio" name={`${uid}-to`} checked={p.to === 'persona'} onChange={() => choose('persona')} />On a persona</label>
      </div>}
      {finding === 'place'
        ? <Finder label={p.to === 'persona' ? 'The persona' : 'The conversation'} scopes={[p.to === 'persona' ? 'personas' : 'conversations']} multi={false} chosen={[]}
          onToggle={(r) => { set({ place: { ...p, where: r.ref, name: r.label } }); setFinding(null); focusPart('placeReason') }} onDone={() => { setFinding(null); focusPart('place') }} />
        : <div className="ba-line"><span className="ba-line-n">{p.to === 'persona' ? 'Persona' : 'Conversation'}</span>
          <button type="button" className="ba-sum" onClick={() => setFinding('place')}>{p.name || (p.to === 'persona' ? 'Choose a persona…' : 'Choose a conversation…')}</button></div>}
      <label className="ba-lab" htmlFor={`${uid}-place-why`}>Why does it belong there?</label>
      <input id={`${uid}-place-why`} data-part="placeReason" type="text" value={p.reason} onChange={(e) => set({ place: { ...p, reason: e.target.value } })} />
      <p className="ba-hint">A proposal that is placed reaches nobody until it is established. Without this it applies only when a run names it.</p>
    </div>
  }

  const contextPart = () => {
    if (finding === 'context') return <div className="ba-part" key="context" data-part="context">
      <span className="ba-lab">The question it settles: a post or a conversation</span>
      <Finder label="The question it settles" scopes={['posts', 'conversations']} multi={false} chosen={d.context ? [d.context] : []} here={here?.id ?? null}
        onToggle={(r) => { set({ context: r }); setFinding(null); focusPart('context') }} onDone={() => { closeFinder(); focusPart(d.context ? 'context' : plan.first[0] ?? '') }} />
    </div>
    if (!d.context) return null
    return <div className="ba-part" key="context"><div className="ba-line"><span className="ba-line-n">Settles</span>
      <div className="ba-line-v">{chips([d.context], () => dropPart('context'))}
        <button type="button" className="ba-quiet" data-part="context" onClick={() => setFinding('context')}>Change</button></div></div></div>
  }

  /* ---- an optional field: open while it is being written, then one line - */
  const optionalField = (f: string) => {
    const input = inputOf(plan, f)
    const writing = input === 'text' || input === 'line'
    if (writing && editing !== f && hasValue(plan, f, d.fields[f])) return <div className="ba-part" key={f}><div className="ba-line">
      <span className="ba-line-n">{nameOf(plan, f)}</span>
      <button type="button" className="ba-sum" data-sum={f} title="Edit" onClick={() => { setEditing(f); focusPart(f) }}>{summaryOf(plan, f, d.fields[f] ?? '', names)}</button>
      <button type="button" className="ba-x" aria-label={`Remove ${nameOf(plan, f).toLowerCase()}`} onClick={() => dropPart(f)}>✕</button></div></div>
    return <div className="ba-part" key={f}>
      <div className="ba-part-head"><label className="ba-lab" htmlFor={`${uid}-${f}`}>{nameOf(plan, f)}</label>
        {!writing && <button type="button" className="ba-x" aria-label={`Remove ${nameOf(plan, f).toLowerCase()}`} onClick={() => dropPart(f)}>✕</button>}</div>
      {control(f, { first: false })}
      {plan.form[f]?.help && <p className="ba-hint">{plan.form[f]!.help}</p>}
    </div>
  }

  const becausePart = () => (editing !== 'because' && d.because.trim()
    ? <div className="ba-part" key="because"><div className="ba-line"><span className="ba-line-n">Because</span>
      <button type="button" className="ba-sum" data-sum="because" onClick={() => { setEditing('because'); focusPart('because') }}>{d.because.trim()}</button>
      <button type="button" className="ba-x" aria-label="Remove why it is changing" onClick={() => dropPart('because')}>✕</button></div></div>
    : <div className="ba-part" key="because"><label className="ba-lab" htmlFor={`${uid}-because`}>Why is it changing?</label>
      <input id={`${uid}-because`} data-part="because" type="text" value={d.because} onChange={(e) => set({ because: e.target.value })}
        onBlur={() => settleSoon('because')} onKeyDown={(e) => { if (e.key === 'Enter' && !e.ctrlKey && !e.metaKey) { e.preventDefault(); e.stopPropagation(); settle('because') } }} /></div>)

  const what = changes(plan, start, d)
  const basisChanged = mode === 'revise' && JSON.stringify(start.basis.map((r) => r.ref)) !== JSON.stringify(d.basis.map((r) => r.ref))
  const note = consequence(mode, { standingApt: k.authoring?.standing_apt === true, editMode: revising?.editMode, placed: revising?.placed })

  return (
    <section ref={root} className={'ba ba-' + mode} role="group" aria-labelledby={title} data-author={k.kind}
      onPointerDownCapture={() => { down.current = true }}
      onKeyDown={(e) => { if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) { e.preventDefault(); if (!asking) void record() } }}>
      <h2 id={title}>{mode === 'create' ? `New ${plan.title}` : `Revise ${plan.title}`}</h2>
      {mode === 'revise' && <p className="ba-was">
        <button type="button" className="ba-link" aria-expanded={diffing} data-diff onClick={() => setDiffing((v) => !v)}>{diffing ? 'Hide what changes' : 'Show what changes'}</button>
      </p>}
      {mode === 'revise' && diffing && <div className="ba-diff" data-diff-shown>
        {!what.length && !basisChanged && <p className="ba-none">Nothing has changed yet.</p>}
        {what.map((c) => <div key={c.field}><span className="ba-line-n">{c.name}</span>
          <p>{c.pieces.map((p, i) => (p.op === 'add' ? <ins key={i}>{p.text}</ins> : p.op === 'cut' ? <del key={i}>{p.text}</del> : <span key={i}>{p.text}</span>))}</p></div>)}
        {basisChanged && <p>What it is based on changes: {start.basis.length} before, {d.basis.length} now.</p>}
      </div>}

      {/* ONCE IT IS RECORDED, OR WHILE THE DISCARD QUESTION IS UP, the draft is
          not for editing: what was sent is what a retry finishes, and the
          question is answered before anything else is touched. */}
      <div style={{ display: 'contents' }} inert={asking || !!made ? true : undefined}>
      {plan.first.map((f) => <div className="ba-first" key={f}>
        <label className="ba-ask" htmlFor={`${uid}-${f}`}>{askOf(plan, f)}</label>
        {control(f, { first: true })}
      </div>)}
      {mode === 'create' && kindExample(k.kind) && <p className="ba-hint">
        <button type="button" className="ba-link" aria-expanded={example} onClick={() => setExample((v) => !v)}>{example ? 'Hide the example' : 'See an example'}</button>
        {example && <span className="ba-example">{kindExample(k.kind)}</span>}</p>}

      {plan.needsConversation && (finding === 'conversation'
        ? <div className="ba-part" data-part="conversation"><span className="ba-lab">The conversation it is for</span>
          <Finder label="The conversation it is for" scopes={['conversations']} multi={false} chosen={[]}
            onToggle={(r) => { set({ conversation: { id: r.ref, name: r.label } }); setFinding(null); focusPart('conversation') }} onDone={() => { setFinding(null); focusPart('conversation') }} /></div>
        : d.conversation
          ? <div className="ba-line"><span className="ba-line-n">For</span>
            <button type="button" className="ba-sum" data-part="conversation" title="Choose another conversation" onClick={() => setFinding('conversation')}>{d.conversation.name || 'This conversation'}</button></div>
          : <button type="button" className={'ba-need' + (err?.part === 'conversation' ? ' bad' : '')} data-part="conversation" onClick={() => setFinding('conversation')}>Choose the conversation it is for…</button>)}

      {(plan.needsBasis || (mode === 'revise' && d.basis.length > 0 && !d.open.includes('basis'))) && basisPart()}
      {d.open.map((p) => (p === 'basis' ? basisPart() : p === 'context' ? contextPart() : p === 'place' ? placePart() : p === 'because' ? becausePart() : optionalField(p)))}

      {offered.length > 0 && <div className="ba-menuwrap">
        <button ref={addBtn} type="button" className="ba-quiet" data-add aria-haspopup="menu" aria-expanded={menu} onClick={() => setMenu((m) => !m)}>+ Add</button>
        {menu && <div className="ba-menu" role="menu" aria-label="Add to this record"
          ref={(el) => { el?.querySelector<HTMLElement>('button')?.focus() }}
          onKeyDown={(e) => {
            const all = [...e.currentTarget.querySelectorAll<HTMLElement>('button')], i = all.indexOf(document.activeElement as HTMLElement)
            if (e.key === 'ArrowDown') { e.preventDefault(); all[(i + 1) % all.length]?.focus() }
            if (e.key === 'ArrowUp') { e.preventDefault(); all[(i - 1 + all.length) % all.length]?.focus() }
            if (e.key === 'Tab') setMenu(false)
          }}>
          {offered.map((p) => <button key={p} type="button" role="menuitem" data-add-part={p} onClick={() => openPart(p)}>{nameOf(plan, p)}</button>)}
        </div>}
      </div>}

      {kindNote(k.kind) && mode === 'create' && <p className="ba-hint">{kindNote(k.kind)}</p>}
      </div>
      {err && <p className="ba-err" role="alert">{err.message}</p>}
      {asking
        ? <div key="ask" className="ba-foot" role="alertdialog" aria-modal="true" aria-label="Discard what you wrote?">
          <span className="ba-note">Discard what you wrote? It has not been recorded.</span>
          <button type="button" className="ba-btn" autoFocus data-keep onClick={() => { setAsking(false); focusPart(plan.first[0] ?? '') }}>Keep writing</button>
          <button type="button" className="ba-btn" data-discard onClick={() => { telling.current?.(false); onCancel() }}>Discard</button>
        </div>
        : <div key="foot" className="ba-foot">
          <span className="ba-note">{made ? 'Recorded as a proposal. The rest did not complete.' : note}</span>
          <button type="button" className="ba-btn quiet" data-cancel disabled={busy} onClick={made ? onCancel : leave}>{made ? 'Close' : 'Cancel'}</button>
          <button type="button" className="ba-btn go" data-record disabled={busy || !me} onClick={() => void record()}>{busy ? 'Recording…' : made ? 'Try the rest again' : 'Record'}</button>
        </div>}
    </section>
  )
}
