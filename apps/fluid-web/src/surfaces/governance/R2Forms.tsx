import { useEffect, useState } from 'react'
import { post, useApi, type Id } from '../../api'
import { fieldValue, formOf, type FieldForm, type KindAuthoring } from './r2Model'
import { ActivitiesInput, activitiesSaid, EntrySelect } from './R2Inputs'

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

/** Material written through the generic door that standing applies to starts
 *  proposed: writing it confers nothing, and establishing is a choice. */
const startsProposed = (k?: KindAuthoring) => k?.authoring?.door === 'entry' && k.authoring.standing_apt === true

export default function R2Create({ kinds, initial, conversation, names, me, onCancel, onDone }: {
  kinds: KindAuthoring[]; initial: string; conversation: Id | null;
  names: Record<string, string>; me: Id | null; onCancel: () => void; onDone: (id: Id) => void
}) {
  const [kind, setKind] = useState(initial)
  const k = kinds.find(k => k.kind === kind)
  const [fields, setFields] = useState<Record<string, string>>({})
  const [where, setWhere] = useState(conversation ?? '')
  const [reach, setReach] = useState<Reach>('named')
  const [proposed, setProposed] = useState(startsProposed(kinds.find(x => x.kind === initial)))
  const [basis, setBasis] = useState('')
  const [basisReason, setBasisReason] = useState('')
  const [context, setContext] = useState('')
  const [derived, setDerived] = useState(false)
  const [approved, setApproved] = useState(false)
  const [citationPending, setCitationPending] = useState(false)
  const [reason, setReason] = useState('')
  const [falsifier, setFalsifier] = useState('')
  const [step, setStep] = useState(1)
  const [created, setCreated] = useState<Id | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  useEffect(() => {
    const escape = (e: KeyboardEvent) => { if (e.key === 'Escape' && !busy) { e.preventDefault(); onCancel() } }
    window.addEventListener('keydown', escape)
    return () => window.removeEventListener('keydown', escape)
  }, [busy, onCancel])
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
  const offersBasis = a.basis === true
  const sourceIds = [...new Set(basis.split(/[\s,]+/).filter(Boolean))]
  const establishes = a.standing_apt === true && !proposed
  const onPersona = !instruction && a.persona_placeable === true && reach === 'persona'
  const needsPlace = instruction || (a.placeable && reach === 'placed') || onPersona
  const destination = onPersona ? personaNames[where] : choices[where]
  const labelOf = (f: string) => form[f]?.label ?? (f === 'text' && KNOWN_LABEL[kind] && !declaredForm ? KNOWN_LABEL[kind] : f)
  const shown = (f: string) => {
    if (form[f]?.input === 'activities') return activitiesSaid(fields[f] ?? '')
    const v = fieldValue(fields[f] ?? '', form[f]?.input)
    return Array.isArray(v) ? v.join(', ') : v
  }
  const write = async () => {
    setError(null)
    if (!me) return setError('An attributed owner is needed.')
    if (created && citationPending && !derived && !sourceIds.length) return setError('Name a held supporting reference to finish the pending citation, or inspect the created proposal.')
    if (sourceIds.length && !basisReason.trim()) return setError('Say how the supporting material leads to this conclusion.')
    if (needsPlace && !where) return setError(onPersona ? 'Choose a persona.' : 'Choose a conversation.')
    if (!instruction && needsPlace && !reason.trim()) return setError('Say why this belongs there.')
    if (establishes && a.expects_falsifier && !falsifier.trim()) return setError('This Kind requires a falsifier.')
    setBusy(true)
    let id = created
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
            ...body, attributed_to: me, propose: !establishes,
          })
          id = r.persona
        } else {
          // EACH FIELD AS ITS FORM DECLARES IT: a list input is stored as a list.
          const body = Object.fromEntries(k.fields.map(f => [f, fieldValue(fields[f] ?? '', form[f]?.input)]))
          const r = await post<{ entry: Id }>('/api/entries', {
            kind, body, attributed_to: me, establish: sourceIds.length ? false : establishes, falsifier,
            links: context.trim() ? [{ relation: 'in-context', to: context.trim() }] : [],
          })
          id = r.entry
        }
        setCreated(id)
        setCitationPending(sourceIds.length > 0)
      }
      if (sourceIds.length && !derived) {
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
  return <section className="r2-form" role="dialog" aria-label={`Create ${kind}`}>
    <div className="r2-panel-head"><span className="r2-tag">{created ? 'Created; finish remaining acts' : `Step ${step} of 3`}</span>
      <button onClick={onCancel} disabled={busy} aria-label="Close creation">×</button></div>
    <h2>{a.door === 'persona' ? 'Create persona' : instruction ? 'Add instruction' : `Record ${kind}`}</h2>
    <p className="r2-dim">{k.meaning}</p>
    {step === 1 && <>
      {kinds.length > 1 && <label>Kind<select aria-label="Kind" value={kind} onChange={e => { setKind(e.target.value); setFields({}); setReach('named'); setWhere(conversation ?? ''); setProposed(startsProposed(kinds.find(x => x.kind === e.target.value))); setBasis(''); setContext(''); setBasisReason(''); setDerived(false) }}>{kinds.map(x => <option key={x.kind}>{x.kind}</option>)}</select></label>}
      {k.fields.map(field)}
      {offersBasis && <>
        {KNOWN_EFFECT[kind] && !declaredForm && <p className="r2-effect">{KNOWN_EFFECT[kind]}</p>}
        {kind === 'decision' && !declaredForm && <label>Question context reference (optional)<input aria-label="Question context reference" value={context} onChange={e => setContext(e.target.value)} /><small>Records context only; it does not claim to answer an ask.</small></label>}
        <label>{kind === 'lesson' && !declaredForm ? 'Supporting findings or outcomes' : 'Supporting material'} references (optional)<textarea aria-label="Supporting references" value={basis} onChange={e => setBasis(e.target.value)} rows={2} /><small>Held entry ids, separated by spaces or commas. Records what this was concluded from.</small></label>
        {sourceIds.length > 0 && <label>How this basis supports the conclusion<textarea aria-label="Derivation reason" value={basisReason} onChange={e => setBasisReason(e.target.value)} /></label>}
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
    {step === 3 && <><h3>Review before recording</h3>{k.fields.map(f => <div key={f}><span className="r2-tag">{form[f]?.label ?? f}</span><p className="r2-prose">{shown(f) || 'Not supplied'}</p></div>)}
      {created && citationPending && !derived && <><label>Correct supporting references<textarea aria-label="Correct supporting references" value={basis} onChange={e => setBasis(e.target.value)} /></label><label>Derivation reason<textarea aria-label="Correct derivation reason" value={basisReason} onChange={e => setBasisReason(e.target.value)} /></label></>}
      {context.trim() && <p>Question context: {context.trim()} · does not answer an ask.</p>}
      {!!sourceIds.length && <p>Concluded from {sourceIds.length} held references: {sourceIds.join(', ')}. {basisReason} Creation, citation and any establishment are separate acts; an incomplete citation leaves a proposal.</p>}
      <p className="r2-effect">{establishes ? sourceIds.length ? 'Established after citing the basis.' : 'Established on creation.' : a.standing_apt === true ? 'Proposed; governs nothing until established.' : 'Recorded without conferring standing; this Kind does not declare that standing applies.'} {needsPlace ? (onPersona ? `Placed on the persona ${destination ?? 'selected'}.` : `Placed in ${destination ?? 'the selected conversation'}.${a.placement_directs_work ? '' : ' Placement does not deliver this Kind; it still reaches only runs that name it.'}`) : a.door === 'persona' ? 'Applies when selected as a persona.' : 'Reaches only runs that name it.'}</p>
      {!instruction && needsPlace && <p>Creation and placement are two recorded acts. If placement fails, the created record remains and you can retry its placement.</p>}
    </>}
    {error && <p role="alert" className="r2-error">{error}</p>}
    <div className="r2-actions"><button disabled={busy} onClick={onCancel}>Cancel</button>{step > 1 && !created && <button disabled={busy} onClick={() => setStep(step - 1)}>Back</button>}
      {step < 3 ? <button className="r2-primary" onClick={() => setStep(step + 1)}>Continue</button> : <button className="r2-primary" disabled={busy || !me} onClick={() => void write()}>{busy ? 'Recording…' : created ? 'Retry remaining acts' : establishes ? 'Create and establish' : a.standing_apt === true ? 'Record proposal' : 'Record material'}</button>}
      {created && <button disabled={busy} onClick={() => onDone(created)}>Inspect created record</button>}
    </div>
  </section>
}
