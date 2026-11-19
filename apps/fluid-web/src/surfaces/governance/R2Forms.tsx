import { useEffect, useRef, useState } from 'react'
import { post, useApi, type Id } from '../../api'
import { fieldValue, formOf, type FieldForm, type KindAuthoring } from './r2Model'
import { ActivitiesInput, activitiesSaid, EntrySelect } from './R2Inputs'
import R2Shaped, { SHAPED, SHAPED_WORDS } from './R2Shaped'
import R2Shown from './R2Shown'
import { writingUnsaved } from './acting'
import { basisIds, basisRefusal, citesAfterCreate, entryCreateBody, requiresBasis, startsProposed } from './creating'

/* ------------------------------------------------------------------------ *
 * THE BUILDER, FROM THE KIND'S OWN DECLARATIONS.
 *
 * A Kind may declare how it is authored (`authoring`: section, door,
 * placeable, persona_placeable, basis) and how each field is asked for
 * (`form`: label, help, input, rows); see `seed.KIND_PROPERTIES`. This form
 * reads those and nothing else, so a Kind defined later gets a working
 * builder by being defined. The words below that name `rule`, `decision`
 * and `lesson` are the FALLBACK for the Kinds this surface has always known,
 * used only where their definitions declare no `form` -- which keeps an
 * existing Brain's builders exactly as they were.
 *
 * Every write is an existing generic door: `POST /api/entries`, then
 * `derive-from`, `establish` and `place` on `/api/entries/<id>/<act>`. A
 * Persona destination is the same `place` act with a Persona's id.
 * ------------------------------------------------------------------------ */

/** The fallback words for the Kinds this surface has always known. */
const KNOWN_LABEL: Record<string, string> = {
  rule: 'How work should be done',
  decision: 'The question and what was settled',
  lesson: 'What went wrong and why',
}
const KNOWN_EFFECT: Record<string, string> = {
  rule: 'Writing a directive gives it no authority. Propose it for consideration, or explicitly establish it as owner.',
  lesson: 'Record a conclusion from findings or outcomes, not a direct observation. Cite the held material that led to it.',
  decision: 'Record a question already settled and its answer. To answer an open ask, use its existing reply choices in the conversation; this form does not close that request.',
}

type Reach = 'named' | 'placed' | 'persona'
export type CreateProgress = { id: Id | null; busy: boolean; establishment: string; remaining: string[] }

export default function R2Create({ kinds, initial, conversation, names, me, onCancel, onDone, basis: initialBasis, onUnsaved, quiet = false, onProgress, onKind }: {
  kinds: KindAuthoring[]; initial: string; conversation: Id | null;
  names: Record<string, string>; me: Id | null; onCancel: () => void; onDone: (id: Id) => void
  /** the held material this is being written from, where the door that
   *  opened the form already knows it (a record's "Propose a rule from it") */
  basis?: Id
  /** WHETHER THERE ARE WORDS HERE NOTHING HAS RECORDED, said whenever it
   *  changes and said false on the way out. A surface that can be navigated
   *  away from (Quiet Chat's Brain pages) asks before leaving on it; one that
   *  cannot simply ignores it. This form knows what it holds, not who asks. */
  onUnsaved?: (unsaved: boolean) => void
  quiet?: boolean
  onProgress?: (progress: CreateProgress | null) => void
  /** WHICH KIND THE FORM IS WRITING NOW, said when it opens and whenever the
   *  reader changes it, so a host that names the Kind names the current one. */
  onKind?: (kind: string) => void
}) {
  const [kind, setKind] = useState(initial)
  const k = kinds.find(k => k.kind === kind)
  const [fields, setFields] = useState<Record<string, string>>({})
  const [where, setWhere] = useState(conversation ?? '')
  const [reach, setReach] = useState<Reach>('named')
  const [proposed, setProposed] = useState(startsProposed(kinds.find(x => x.kind === initial)))
  const [basis, setBasis] = useState(initialBasis ?? '')
  const [basisReason, setBasisReason] = useState('')
  const [context, setContext] = useState('')
  const [derived, setDerived] = useState(false)
  const [approved, setApproved] = useState(false)
  const [citationPending, setCitationPending] = useState(false)
  const [reason, setReason] = useState('')
  const [falsifier, setFalsifier] = useState('')
  const [step, setStep] = useState(1)
  const [created, setCreated] = useState<Id | null>(null)
  const [creation, setCreation] = useState<{ standing: boolean; establishedOnCreation: boolean; establishAfterCitation: boolean; placement: boolean } | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [guard, setGuard] = useState<'leave' | 'kind' | null>(null)
  const [nextKind, setNextKind] = useState('')
  /* WHAT A SHAPED LAYOUT HOLDS BESIDE THE FIELDS: which part of the job is
     open, which activity is being edited, and whether the shape of the draft
     was changed without anything being typed -- an added activity or list row
     that is still empty is a change, and closing on one must still warn. */
  const [section, setSection] = useState('overview')
  const [selected, setSelected] = useState(0)
  const [structural, setStructural] = useState(false)
  const [settingsOpen, setSettingsOpen] = useState(false)
  /* WHAT THIS FORM HOLDS THAT NOTHING HAS RECORDED (`acting.ts`). */
  const unsaved = (quiet && (structural || reach !== 'named' || proposed !== startsProposed(kinds.find(x => x.kind === kind)) || where !== (conversation ?? ''))) || writingUnsaved({
    created: !!created,
    typed: [...Object.values(fields), basisReason, context, reason, falsifier],
    basis, basisGiven: initialBasis ?? '',
  })
  const telling = useRef(onUnsaved)
  telling.current = onUnsaved
  useEffect(() => { telling.current?.(unsaved); return () => telling.current?.(false) }, [unsaved])
  const naming = useRef(onKind)
  naming.current = onKind
  useEffect(() => { naming.current?.(kind) }, [kind])
  /* A REFUSAL IS ABOUT THE DRAFT AS IT WAS. Once the reader changes what it
     complained about, or moves between steps, it is no longer true of what is
     on screen, so it is taken down; the next attempt says what still holds. */
  useEffect(() => { setError(null) }, [step, kind, reach, where, proposed, basis, basisReason, reason, falsifier, context, fields])
  /* CANCEL IS THE READER DISCARDING IT DELIBERATELY: said before whatever
     Cancel leads to, so nothing asks again about work they just let go of. */
  const cancel = () => {
    if (busy) return
    if (quiet && (unsaved || created)) { setGuard('leave'); return }
    telling.current?.(false); onCancel()
  }
  const resetKind = (next: string) => {
    setKind(next); setFields({}); setReach('named'); setWhere(conversation ?? '')
    setProposed(startsProposed(kinds.find(x => x.kind === next)))
    setBasis(initialBasis ?? ''); setContext(''); setBasisReason(''); setDerived(false)
    setApproved(false); setCitationPending(false); setReason(''); setFalsifier('')
    setCreated(null); setCreation(null); setError(null); setStep(1)
    setSection('overview'); setSelected(0); setStructural(false); setSettingsOpen(false)
  }
  useEffect(() => {
    const escape = (e: KeyboardEvent) => { if (e.key === 'Escape' && !busy) { e.preventDefault(); if (guard) setGuard(null); else cancel() } }
    window.addEventListener('keydown', escape)
    return () => window.removeEventListener('keydown', escape)
  })
  const a = k?.authoring
  // READ AS FAR AS IT CAN BE, never trusted: see `formOf`.
  const declaredForm = formOf(k?.form)
  const form: Record<string, FieldForm> = declaredForm ?? {}
  // Read choices from the real store, including when arriving at Brain scope.
  const convs = useApi<{ conversations: { id: Id; name: string }[] }>('/api/conversations')
  // SUBJECTS ALREADY NAMED, offered so one subject is not written two ways:
  // conflicts are found by comparing `about`, never by reading the words.
  const subjects = useApi<{ subjects: { about: string; count: number }[] }>('/api/governance/subjects')
  // Asked only where this Kind's form or placement needs them.
  const vocabulary = useApi<{ capabilities?: string[] }>(
    Object.values(form).some(f => f.input === 'capabilities') ? '/api/governance/authoring' : null)
  const personas = useApi<{ personas: { persona: Id; name: string }[] }>(a?.persona_placeable ? '/api/personas' : null)
  const choices = { ...names, ...Object.fromEntries((convs.data?.conversations ?? []).map(c => [c.id, c.name])) }
  const personaNames = Object.fromEntries((personas.data?.personas ?? []).map(p => [p.persona, p.name]))
  if (!k || !a) return <p role="alert">This Brain has not declared an authoring door for that Kind.</p>
  const instruction = a.door === 'instruction'
  const offersBasis = a.basis === true || requiresBasis(k)
  const sourceIds = basisIds(basis)
  /* A KIND THAT REQUIRES A BASIS is written with it: the field is required,
     an empty one is refused here, and the references ride on the create
     (`creating.ts`). The reason is asked only where an act will carry it. */
  const needsBasis = requiresBasis(k)
  const asksReason = sourceIds.length > 0 && (!needsBasis || (a.standing_apt === true && !proposed))
  const basisNote = needsBasis ? 'required' : 'optional'
  const establishes = a.standing_apt === true && !proposed
  const onPersona = !instruction && a.persona_placeable === true && reach === 'persona'
  const needsPlace = instruction || (a.placeable && reach === 'placed') || onPersona
  const destination = onPersona ? personaNames[where] : choices[where]
  const labelOf = (f: string) => form[f]?.label ?? (f === 'text' && KNOWN_LABEL[kind] && !declaredForm ? KNOWN_LABEL[kind] : quiet ? f.replace(/[_-]+/g, ' ').replace(/^./, c => c.toUpperCase()) : f)
  const remaining = [citationPending && !derived ? 'citation' : '', creation?.establishAfterCitation && !approved ? 'establishment' : '', creation?.placement ? 'placement' : ''].filter(Boolean)
  const establishment = !creation ? '' : !creation.standing ? 'Standing does not apply.' : approved ? 'Establishment completed.' : creation.establishedOnCreation ? 'Establishment was requested on creation.' : 'The record was created as a proposal.'
  const progress: CreateProgress = { id: created, busy, establishment, remaining }
  // The host reads the latest held state at the moment navigation is attempted.
  onProgress?.(progress)
  const shown = (f: string) => {
    if (form[f]?.input === 'activities') return activitiesSaid(fields[f] ?? '')
    const v = fieldValue(fields[f] ?? '', form[f]?.input)
    return Array.isArray(v) ? v.join(', ') : v
  }
  /* A REFUSAL ABOUT REACH, STANDING OR THE BASIS OPENS WHERE IT IS ANSWERED,
     so a shaped layout never refuses in words whose control is folded away. */
  const refuse = (m: string) => { setSettingsOpen(true); setError(m) }
  const write = async () => {
    setError(null)
    if (!me) return setError('An attributed owner is needed.')
    if (created && citationPending && !derived && !sourceIds.length) return refuse('Name a held supporting reference to finish the pending citation, or inspect the created proposal.')
    const unbased = created ? null : basisRefusal(k, basis)
    if (unbased) return refuse(unbased)
    if (asksReason && !basisReason.trim()) return refuse('Say how the supporting material leads to this conclusion.')
    if (needsPlace && !where) return refuse(onPersona ? 'Choose a persona.' : 'Choose a conversation.')
    if (!instruction && needsPlace && !reason.trim()) return refuse('Say why this belongs there.')
    if (establishes && a.expects_falsifier && !falsifier.trim()) return refuse('This Kind requires a falsifier.')
    setBusy(true)
    let id = created
    let cited = derived
    try {
      if (!id) {
        if (instruction) {
          const body = Object.fromEntries(k.fields.map(f => [f, fields[f] ?? '']))
          const r = await post<{ entry: Id }>(`/api/conversations/${where}/instructions`, {
            ...body, attributed_to: me, establish: establishes,
          })
          id = r.entry
        } else if (a.door === 'persona') {
          const body = Object.fromEntries(k.fields.map(f => [f, fields[f] ?? '']))
          const r = await post<{ persona: Id }>('/api/personas', {
            ...body, attributed_to: me, propose: !establishes, establish: establishes,
          })
          id = r.persona
        } else {
          // EACH FIELD AS ITS FORM DECLARES IT: a list input is stored as a list.
          const body = Object.fromEntries(k.fields.map(f => [f, fieldValue(fields[f] ?? '', form[f]?.input)]))
          const r = await post<{ entry: Id }>('/api/entries', entryCreateBody({
            k, body, me, establishes, falsifier, context, sources: sourceIds,
          }))
          id = r.entry
          // The basis went with the record: nothing is left to cite.
          if (needsBasis) { cited = true; setDerived(true) }
        }
        setCreation({ standing: a.standing_apt === true, establishedOnCreation: establishes && (instruction || a.door === 'persona' || !sourceIds.length), establishAfterCitation: !!sourceIds.length && establishes, placement: !instruction && !!needsPlace })
        setCreated(id)
        setCitationPending(citesAfterCreate(k, sourceIds))
      }
      if (sourceIds.length && !cited) {
        await post(`/api/entries/${id}/derive-from`, { attributed_to: me, from: sourceIds, because: basisReason.trim() })
        setDerived(true)
      }
      // Cite the basis before conferring standing. A failed citation leaves a
      // proposal and preserves its identity for retry, never an uncited approval.
      if (sourceIds.length && establishes && !approved) {
        await post(`/api/entries/${id}/establish`, { attributed_to: me, because: basisReason.trim(), falsifier })
        setApproved(true)
      }
      // The existing API has separate creation and placement acts. Keep the
      // new identity on refusal so Retry cannot create a duplicate.
      if (!instruction && needsPlace) await post(`/api/entries/${id}/place`, {
        attributed_to: me, where, because: reason.trim(),
      })
      onDone(id)
    } catch (e) {
      setError((id ? `Created ${id}; remaining acts have not completed. Retry, or inspect the created record. ` : '') + (e as Error).message)
    } finally { setBusy(false) }
  }
  /* THE ONE LEAVE WARNING, rendered by whichever layout is on screen.
     A record being written exists nowhere else, so this is a separate
     readable card and not a browser confirm: Keep editing returns to
     everything typed -- including a part-written activity and an empty list
     row -- and discarding is explicit. After a record has been created it
     stops offering to discard and says what has and has not completed, so a
     partial write is disclosed rather than hidden. */
  const leaveGuard = () => quiet && guard
    ? <div className="r2-create-guard" role="alertdialog" aria-modal="true" aria-label={created ? 'Created record' : 'Discard this draft?'}>
      <div className="r2-create-guard-card">
        <h3>{created ? `Created ${created}` : 'Discard this draft?'}</h3>
        <p>{created
          ? `${establishment} Remaining: ${remaining.join(', ') || 'none'}. Leaving does not undo recorded acts.`
          : 'Your changes have not been recorded. Keep editing returns to everything you typed, including unfinished activities and list rows.'}</p>
        <div className="r2-actions">
          <button autoFocus onClick={() => setGuard(null)}>Keep editing</button>
          {created
            ? <button onClick={() => { telling.current?.(false); onDone(created) }}>Inspect created record</button>
            : <button onClick={() => { setGuard(null); if (guard === 'kind') resetKind(nextKind); else { telling.current?.(false); onCancel() } }}>Discard draft</button>}
        </div>
      </div>
    </div>
    : null
  const field = (f: string) => {
    const spec = form[f] ?? {}
    const set = (v: string) => setFields({ ...fields, [f]: v })
    const help = spec.help ? <small>{spec.help}</small> : null
    if (f === 'about' && a.door !== 'persona' && (!spec.input || spec.input === 'line')) return <label key={f}>{spec.label ?? 'Subject (optional)'}<input aria-label={f} list="r2-subjects" value={fields[f] ?? ''} onChange={e => set(e.target.value)} />{help ?? <small>What it speaks to. Material naming the same subject differently is reported as a conflict when both reach a run; reuse a subject already named where it is the same thing.</small>}<datalist id="r2-subjects">{(subjects.data?.subjects ?? []).map(x => <option key={x.about} value={x.about} />)}</datalist></label>
    if (spec.input === 'participant' || spec.input === 'persona') return <EntrySelect key={f} input={spec.input} field={f} label={labelOf(f)} help={spec.help} value={fields[f] ?? ''} onChange={set} />
    if (spec.input === 'activities') return <ActivitiesInput key={f} field={f} label={labelOf(f)} help={spec.help} value={fields[f] ?? ''} onChange={set} />
    if (spec.input === 'line') return <label key={f}>{labelOf(f)}<input aria-label={f} value={fields[f] ?? ''} onChange={e => set(e.target.value)} />{help}</label>
    if (spec.input === 'capabilities') {
      const picked = new Set(fieldValue(fields[f] ?? '', 'list') as string[])
      const flip = (c: string) => { const next = new Set(picked); if (next.has(c)) next.delete(c); else next.add(c); set([...next].join('\n')) }
      return <fieldset key={f} className="r2-capabilities" aria-label={f}><legend>{labelOf(f)}</legend>
        {(vocabulary.data?.capabilities ?? []).map(c => <label key={c} className="r2-check"><input type="checkbox" checked={picked.has(c)} onChange={() => flip(c)} />{c}</label>)}
        {vocabulary.loading && !vocabulary.data && <small>Reading the capability vocabulary…</small>}{help}</fieldset>
    }
    const rows = spec.rows ?? (spec.input === 'refs' ? 2 : f === k.fields[0] ? 4 : 2)
    return <label key={f}>{labelOf(f)}<textarea aria-label={f} value={fields[f] ?? ''} rows={rows} onChange={e => set(e.target.value)} />
      {help ?? (spec.input === 'refs' ? <small>Held entry ids, separated by spaces or commas.</small> : spec.input === 'list' ? <small>One per line.</small> : null)}</label>
  }
  /* ------------------------------------------------------------------ *
   * THE FOUR KINDS WITH A WORKSPACE OF THEIR OWN (`R2Shaped`).
   *
   * Nothing below is a second builder: the fields, the write, the guard and
   * what is held unrecorded are the same ones the generic flow uses, laid
   * out around the job instead of stacked, with the record beside the
   * writing and creation in that preview. No step bar and no review step:
   * the preview is the review, and it is always on screen.
   * ------------------------------------------------------------------ */
  const shaped = quiet && SHAPED.has(kind)
  const words = SHAPED_WORDS[kind]
  const changeKind = (next: string) => {
    if (created || busy) return
    if (unsaved) { setNextKind(next); setGuard('kind') } else resetKind(next)
  }
  const kindSwitch = kinds.length > 1 && <label className="r2c-kindswitch">Kind
    <select aria-label="Kind" value={kind} onChange={e => changeKind(e.target.value)}>
      {kinds.map(x => <option key={x.kind}>{x.kind}</option>)}</select></label>
  const reachWords = instruction || reach === 'placed'
    ? `Conversation · ${destination ?? 'Not chosen yet'}`
    : onPersona ? `Persona · ${destination ?? 'Not chosen yet'}`
      : 'Only when named for a run'
  const primaryWords = busy ? 'Recording…' : created ? 'Retry remaining acts'
    : establishes ? `Create and establish ${kind.replace(/-/g, ' ')}` : `Create ${kind.replace(/-/g, ' ')}`

  if (shaped) return <section className="r2-form r2-create-quiet r2-create-shaped-host" role="dialog" aria-label={`Create ${kind}`}>
    <div style={{ display: 'contents' }} inert={quiet && !!guard ? true : undefined}>
      <R2Shaped
        parts={{
          kind, k, form, fields, set: (f, v) => setFields({ ...fields, [f]: v }),
          onStructural: () => setStructural(true),
          capabilities: vocabulary.data?.capabilities ?? [], capabilitiesLoading: vocabulary.loading,
          selected, onSelect: setSelected, section, onSection: setSection,
        }}
        header={<>
          {/* The host page already says which Kind is being made, so this
              says only what is not already on screen: that a write has
              part-completed, and the way out. */}
          <div className="r2-panel-head">{created ? <span className="r2-tag">Created; finish remaining acts</span> : <span />}
            <button onClick={cancel} disabled={busy} aria-label="Close creation">×</button></div>
          <h2>{words.task}</h2>
          <p className="r2-dim">Write beside the record as it will read. Create it there when it is ready.</p>
          <div className="r2c-kindtools"><span className="r2c-pill">{words.icon} {words.name}</span>{kindSwitch}</div>
          <p className="r2c-meaning">{k.meaning}</p>
        </>}
        destination={<label>Conversation
          <select aria-label="Creation conversation" value={where} onChange={e => setWhere(e.target.value)}>
            <option value="">Choose a conversation</option>
            {Object.entries(choices).map(([id, name]) => <option key={id} value={id}>{name}</option>)}</select>
          <small>This instruction applies in the Conversation chosen here, to everyone working in it.</small></label>}
        participant={form.carrier ? <EntrySelect input="participant" field="carrier" label={form.carrier.label ?? 'Usually carried by'}
          help={form.carrier.help} value={fields.carrier ?? ''} onChange={v => setFields({ ...fields, carrier: v })} /> : null}
        persona={form.persona ? <EntrySelect input="persona" field="persona" label={form.persona.label ?? 'Carried as'}
          help={form.persona.help} value={fields.persona ?? ''} onChange={v => setFields({ ...fields, persona: v })} /> : null}
        settings={<details className="r2c-placement" open={settingsOpen}
          onToggle={e => setSettingsOpen((e.target as HTMLDetailsElement).open)}>
          <summary>Use, standing &amp; supporting material</summary>
          <section className="r2c-section">
            {instruction
              ? <p className="r2c-notice">This instruction is for the Conversation chosen above. It reaches everyone working there, whatever Persona they wear.</p>
              : <>
                {(a.placeable || a.persona_placeable) && <label>Where it reaches
                  <select aria-label="Where it reaches" value={reach} onChange={e => { setReach(e.target.value as Reach); setWhere(e.target.value === 'placed' ? conversation ?? '' : '') }}>
                    <option value="named">Only when named for a run</option>
                    {a.placeable && <option value="placed">Place in a conversation{a.placement_directs_work ? '' : ' for context; still only when named'}</option>}
                    {a.persona_placeable && <option value="persona">Place on a persona</option>}</select></label>}
                {needsPlace && <>
                  {onPersona
                    ? <label>Persona<select aria-label="Creation persona" value={where} onChange={e => setWhere(e.target.value)}><option value="">Choose a persona</option>{(personas.data?.personas ?? []).map(p => <option key={p.persona} value={p.persona}>{p.name}</option>)}</select></label>
                    : <label>Conversation<select aria-label="Creation conversation" value={where} onChange={e => setWhere(e.target.value)}><option value="">Choose a conversation</option>{Object.entries(choices).map(([id, name]) => <option key={id} value={id}>{name}</option>)}</select></label>}
                  <label>Why it belongs there<textarea aria-label="Placement reason" value={reason} rows={2} onChange={e => setReason(e.target.value)} /></label>
                  <p className="r2c-notice">A placement can be ended later from the record; its reach stops there and the placement stays in the history. Nothing is erased.</p></>}
              </>}
            {a.standing_apt === true && <label>Initial status
              <select aria-label="Initial status" value={proposed ? 'proposed' : 'force'} onChange={e => setProposed(e.target.value === 'proposed')}>
                <option value="proposed">Keep proposed</option>
                <option value="force">I am establishing this as owner</option></select>
              <small>A new record starts as a proposal. Giving it standing is a separate, deliberate owner act.</small></label>}
            {a.expects_falsifier && establishes && <label>What would prove this wrong?<textarea aria-label="Falsifier" value={falsifier} onChange={e => setFalsifier(e.target.value)} /></label>}
            {offersBasis && <>
              <label>Supporting material references ({basisNote})<textarea aria-label="Supporting references" value={basis} rows={2} onChange={e => setBasis(e.target.value)} />
                <small>Held entry ids, separated by spaces or commas. Supporting references record the basis; they confer no standing.</small></label>
              {asksReason && <label>How this basis supports the conclusion<textarea aria-label="Derivation reason" value={basisReason} onChange={e => setBasisReason(e.target.value)} /></label>}</>}
          </section>
        </details>}
        preview={<R2Shown kind={kind} fields={fields} form={form} meta={{
          kindLabel: words.name, icon: words.icon, proposed: !establishes, reach: reachWords,
          reason, basis, basisReason,
          selected: kind === 'workflow' && section === 'activities' ? selected : -1,
        }} />}
        commit={<>
          {created && citationPending && !derived && <>
            <label>Correct supporting references<textarea aria-label="Correct supporting references" value={basis} onChange={e => setBasis(e.target.value)} /></label>
            <label>Derivation reason<textarea aria-label="Correct derivation reason" value={basisReason} onChange={e => setBasisReason(e.target.value)} /></label></>}
          <button className="r2-primary" disabled={busy || !me} onClick={() => void write()}>{primaryWords}</button>
          {/* WHAT CREATING IT WOULD DO, AND WHAT A PART-DONE WRITE LEFT: the
              same words the generic flow's own review and guard use. */}
          <p className="r2c-commitnote">{created
            ? `${establishment} Remaining acts: ${remaining.join(', ') || 'none'}.`
            : establishes ? (sourceIds.length ? 'Established after citing the basis.' : 'Established on creation.')
              : a.standing_apt === true ? 'Creates a proposal. No standing is conferred.'
                : 'Recorded without conferring standing; this Kind does not declare that standing applies.'}</p>
          {!created && !instruction && needsPlace && <p className="r2c-commitnote">Creation and placement are two recorded acts. If placement fails, the created record remains and you can retry its placement.</p>}
          {error && <p role="alert" className="r2-error">{error}</p>}
          {created && <button disabled={busy} onClick={() => onDone(created)}>Inspect created record</button>}
        </>}
      />
    </div>
    {leaveGuard()}
  </section>

  return <section className={`r2-form${quiet ? ' r2-create-quiet' : ''}`} role="dialog" aria-label={`Create ${kind}`}>
    <div style={{ display: 'contents' }} inert={quiet && !!guard ? true : undefined}>
    <div className="r2-panel-head"><span className="r2-tag">{created ? 'Created; finish remaining acts' : `Step ${step} of 3`}</span>
      <button onClick={cancel} disabled={busy} aria-label="Close creation">×</button></div>
    <h2>{a.door === 'persona' ? 'Create persona' : instruction ? 'Add instruction' : `Record ${kind}`}</h2>
    <p className="r2-dim">{k.meaning}</p>
    {quiet && <div className="r2-create-steps" aria-label="Progress">{['Details', 'Reach & status', 'Review'].map((name, i) => <span key={name} aria-current={step === i + 1 ? 'step' : undefined}><b>{i + 1}</b>{name}</span>)}</div>}
    {step === 1 && <>
      {kinds.length > 1 && <label>Kind<select aria-label="Kind" value={kind} onChange={e => { const next = e.target.value; if (quiet && (created || busy)) return; if (quiet && unsaved) { setNextKind(next); setGuard('kind') } else if (quiet) resetKind(next); else { setKind(next); setFields({}); setReach('named'); setWhere(conversation ?? ''); setProposed(startsProposed(kinds.find(x => x.kind === next))); setBasis(''); setContext(''); setBasisReason(''); setDerived(false) } }}>{kinds.map(x => <option key={x.kind}>{x.kind}</option>)}</select></label>}
      {k.fields.map(field)}
      {offersBasis && <>
        {KNOWN_EFFECT[kind] && !declaredForm && <p className="r2-effect">{KNOWN_EFFECT[kind]}</p>}
        {kind === 'decision' && !declaredForm && <label>Question context reference (optional)<input aria-label="Question context reference" value={context} onChange={e => setContext(e.target.value)} /><small>Records context only; it does not claim to answer an ask.</small></label>}
        <label>{kind === 'lesson' && !declaredForm ? 'Supporting findings or outcomes' : 'Supporting material'} references ({basisNote})<textarea aria-label="Supporting references" aria-required={needsBasis || undefined} value={basis} onChange={e => setBasis(e.target.value)} rows={2} /><small>Held entry ids, separated by spaces or commas. Records what this was concluded from.{needsBasis ? ' A record of this Kind cannot be recorded without at least one.' : ''}</small></label>
        {asksReason && <label>How this basis supports the conclusion<textarea aria-label="Derivation reason" value={basisReason} onChange={e => setBasisReason(e.target.value)} /></label>}
      </>}
    </>}
    {step === 2 && <>
      {(a.placeable || a.persona_placeable) && !instruction && <label>Where it reaches<select aria-label="Where it reaches" value={reach} onChange={e => { setReach(e.target.value as Reach); setWhere(e.target.value === 'placed' ? conversation ?? '' : '') }}>
        <option value="named">Only when named for a run</option>
        {a.placeable && <option value="placed">Place in a conversation{a.placement_directs_work ? '' : ' for context; still only when named'}</option>}
        {a.persona_placeable && <option value="persona">Place on a persona</option>}</select></label>}
      {needsPlace && <>{onPersona
        ? <label>Persona<select aria-label="Creation persona" value={where} onChange={e => setWhere(e.target.value)}><option value="">Choose a persona</option>{(personas.data?.personas ?? []).map(p => <option key={p.persona} value={p.persona}>{p.name}</option>)}</select></label>
        : <label>Conversation<select aria-label="Creation conversation" value={where} onChange={e => setWhere(e.target.value)}><option value="">Choose a conversation</option>{Object.entries(choices).map(([id, name]) => <option key={id} value={id}>{name}</option>)}</select></label>}
        {!instruction && <label>Why it belongs there<textarea aria-label="Placement reason" value={reason} onChange={e => setReason(e.target.value)} /></label>}
        <p className="r2-effect">A placement can be ended later from the record (End placement); its reach stops there and the placement stays in the history. Nothing is erased.</p></>}
      {a.door === 'persona' && <p className="r2-effect">Personas apply to runs started as them. They are not placed in conversations.</p>}
      {a.standing_apt === true && <label>Initial status<select aria-label="Initial status" value={proposed ? 'proposed' : 'force'} onChange={e => setProposed(e.target.value === 'proposed')}><option value="proposed">Keep proposed</option><option value="force">I am establishing this as owner</option></select></label>}
      {offersBasis && <p className="r2-dim">Supporting references record the basis; they confer no standing. Owner establishment is a separate deliberate choice.</p>}
      {a.expects_falsifier && establishes && <label>What would prove this wrong?<textarea aria-label="Falsifier" value={falsifier} onChange={e => setFalsifier(e.target.value)} /></label>}
    </>}
    {step === 3 && <><h3>Review before recording</h3>{quiet && !created && <button type="button" onClick={() => setStep(1)}>Edit details</button>}{k.fields.map(f => <div key={f}><span className="r2-tag">{quiet ? labelOf(f) : form[f]?.label ?? f}</span><p className="r2-prose">{shown(f) || 'Not supplied'}</p></div>)}
      {created && citationPending && !derived && <><label>Correct supporting references<textarea aria-label="Correct supporting references" value={basis} onChange={e => setBasis(e.target.value)} /></label><label>Derivation reason<textarea aria-label="Correct derivation reason" value={basisReason} onChange={e => setBasisReason(e.target.value)} /></label></>}
      {context.trim() && <p>Question context: {context.trim()} · does not answer an ask.</p>}
      {!created && !!sourceIds.length && <p>Concluded from {sourceIds.length} held references: {sourceIds.join(', ')}. {needsBasis ? 'They are recorded with the record when it is created.' : `${basisReason} Creation, citation and any establishment are separate acts; an incomplete citation leaves a proposal.`}</p>}
      <p className="r2-effect">{created ? `${establishment} Remaining acts: ${remaining.join(', ') || 'none'}.` : establishes ? sourceIds.length ? 'Established after citing the basis.' : 'Established on creation.' : a.standing_apt === true ? 'Proposed; governs nothing until established.' : 'Recorded without conferring standing; this Kind does not declare that standing applies.'} {!created && (needsPlace ? (onPersona ? `Placed on the persona ${destination ?? 'selected'}.` : `Placed in ${destination ?? 'the selected conversation'}.${a.placement_directs_work ? '' : ' Placement does not deliver this Kind; it still reaches only runs that name it.'}`) : a.door === 'persona' ? 'Applies when selected as a persona.' : 'Reaches only runs that name it.')}</p>
      {!instruction && needsPlace && <p>Creation and placement are two recorded acts. If placement fails, the created record remains and you can retry its placement.</p>}
    </>}
    {error && <p role="alert" className="r2-error">{error}</p>}
    <div className="r2-actions"><button disabled={busy} onClick={cancel}>Cancel</button>{step > 1 && !created && <button disabled={busy} onClick={() => setStep(step - 1)}>Back</button>}
      {step < 3 ? <button className="r2-primary" onClick={() => { const unbased = step === 1 ? basisRefusal(k, basis) : null; if (unbased) setError(unbased); else setStep(step + 1) }}>Continue</button> : <button className="r2-primary" disabled={busy || !me} onClick={() => void write()}>{busy ? 'Recording…' : created ? 'Retry remaining acts' : establishes ? 'Create and establish' : a.standing_apt === true ? 'Record proposal' : 'Record material'}</button>}
      {created && <button disabled={busy} onClick={() => onDone(created)}>Inspect created record</button>}
    </div>
    </div>
    {leaveGuard()}
  </section>
}
