import Bounded from './Bounded'
import { useState } from 'react'
import { post, useApi, when, type Id, type DisputeRead } from '../../api'
import EntryInspect from '../EntryInspect'
import { editEntry, deleteEntry, EDIT_WORDS } from '../Versions'
import { readProposal, supersede } from '../standing'
import ActDialog, { type ActName, type ActItem } from './ActDialogs'
import { fieldText, fieldValue, formOf, LIST_INPUTS, type KindAuthoring } from './r2Model'
import { ActivitiesInput, ActivityWarnings, EntrySelect } from './R2Inputs'

interface Entry {
  id: Id; kind: string; fields: string[]; body: Record<string, unknown>;
  stands: boolean; author_alias: string | null;
  at: number | null;
  established_by: Id[]; superseded_by: Id[]; standing_apt: boolean | null;
  governance_actions: Record<string, boolean | string | null> & { placements?: Placement[]; carries?: Carried[] }
}

/** Material placed ON this record -- for a Persona, the Disciplines it carries. */
interface Carried { entry: Id; kind: string | null; name: string; stands: boolean }

/** Where the material is placed now, as the entry read reports it. */
interface Placement { where: Id; name: string | null; whole_brain: boolean; persona?: boolean; reason: string | null; at: number | null }

/** The Whole Brain is a destination the owner chooses, never a default. */
const WHOLE_BRAIN = 'whole-brain'

/** What "Cited by" can say today: prose citations are not listed (an existing
 *  limitation), and where the reader can look instead. */
export const CITED_BY = 'Citations across prose cannot be listed here yet. Recorded relations and delivery history are available above. Search Mentis can find mentions of this record.'


export interface RecordActsProps {
  id: Id; conversation: Id | null; me: Id | null;
  kinds: KindAuthoring[]; names: Record<string, string>;
  initialEdit?: boolean;
  onInspect: (id: Id) => void; onPreview: () => void; onChanged: () => void;
  /** run the acts' dialogs in place (Fluid's Stage) rather than over a veil */
  inline?: boolean
  /** ONE PRIMARY ACT AND DISPUTE IN THE ROW (Fluid): where both Establish and
   *  a new version are offered, and for a persona's Preview, the rest move
   *  under More. Absent, the row is exactly R2Record's. */
  oneRow?: boolean
}

/** THE RECORD'S ACTS, AS PIECES. Everything R2Record offers on a governed
 *  record -- its reads, its action row and More, its inline forms, the act
 *  dialog -- returned as the nodes R2Record draws, so another surface (Fluid)
 *  can arrange the same controls without a second path to the same routes. */
export function useRecordActs({ id, conversation, me, kinds, names, initialEdit = false,
  onInspect, onPreview, onChanged, inline = false, oneRow = false }: RecordActsProps) {
  const entry = useApi<Entry>(`/api/entries/${id}`)
  const challenges = useApi<{ disputes: DisputeRead[] }>(`/api/governance/disputes?entry=${id}`)
  const convs = useApi<{ conversations: { id: Id; name: string }[] }>('/api/conversations')
  const choices = { ...names, ...Object.fromEntries((convs.data?.conversations ?? []).map(c => [c.id, c.name])) }
  const [open, setOpen] = useState<'edit' | 'place' | 'unplace' | 'delete' | 'replace' | null>(initialEdit ? 'edit' : null)
  const [ending, setEnding] = useState<Placement | null>(null)
  const [dialog, setDialog] = useState<ActName | null>(null)
  const [approval, setApproval] = useState<Awaited<ReturnType<typeof readProposal>> | null>(null)
  const [dispute, setDispute] = useState<DisputeRead | null>(null)
  const [values, setValues] = useState<Record<string, string>>({})
  const [reason, setReason] = useState('')
  const [where, setWhere] = useState(conversation ?? '')
  const [replacement, setReplacement] = useState('')
  const successor = useApi<Entry>(open === 'replace' && /^ent-[a-f0-9]{12}$/.test(replacement.trim()) ? `/api/entries/${replacement.trim()}` : null)
  const [immediate, setImmediate] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [said, setSaid] = useState<string | null>(null)
  const [proposed, setProposed] = useState<Id | null>(null)
  const d = entry.data
  const changed = () => { entry.reload(); challenges.reload(); onChanged() }
  const approve = async (proposal: Id) => {
    try { setApproval(await readProposal(proposal)); setDialog('establish') }
    catch (e) { setError((e as Error).message) }
  }
  const run = async (fn: () => Promise<void>) => {
    if (busy) return
    setBusy(true); setError(null)
    try { await fn(); changed() } catch (e) { setError((e as Error).message) }
    finally { setBusy(false) }
  }
  const prepare = (action: typeof open) => { setOpen(action); setReason(''); setError(null) }
  const a = d?.governance_actions ?? {}
  const editWords = EDIT_WORDS[String(a.edit_mode ?? 'edited')] ?? EDIT_WORDS.edited
  const item: ActItem | null = d ? { entry: id, kind: d.kind, text: d.fields.map(f => String(d.body[f] ?? '')).filter(Boolean).join('\n\n'),
    stands: d.stands, author_alias: d.author_alias,
    standing: d.stands ? 'stands' : d.superseded_by.length ? 'ended' : 'candidate' } : null
  // WHAT THE KIND DECLARES ABOUT ITSELF: its form (list inputs are edited one
  // item per line and stored as lists) and whether a Persona may hold it.
  const declared = kinds.find(k => k.kind === d?.kind)
  const form = formOf(declared?.form) ?? {}
  const listed = (f: string) => LIST_INPUTS.has(form[f]?.input ?? '')
  const inputOf = (f: string) => form[f]?.input
  const fields = d?.fields.filter(f => listed(f) || inputOf(f) === 'activities' || typeof (d.body[f] ?? '') === 'string') ?? []
  const was = (f: string) => fieldText(d?.body[f], inputOf(f))
  const personas = useApi<{ personas: { persona: Id; name: string }[] }>(declared?.authoring?.persona_placeable ? '/api/personas' : null)
  const personaNames: Record<string, string> = Object.fromEntries((personas.data?.personas ?? []).map(p => [p.persona, p.name]))
  const live = ['edit', 'establish', 'dispute', 'delete', 'place'].some(x => a[x] === true)
  const placements = d?.governance_actions.placements ?? []
  const placeName = (p: Placement) => p.whole_brain ? 'the Whole Brain'
    : p.persona ? `Persona ${p.name ?? personaNames[p.where] ?? p.where}` : (p.name ?? choices[p.where] ?? personaNames[p.where] ?? p.where)
  const carries = d?.governance_actions.carries ?? []
  const persona = !!d && kinds.find(k => k.kind === d.kind)?.authoring?.door === 'persona' && d.stands
  return {
    entry, d, actions: (d && me && live && <div className="r2-record-actions">
      <div className="r2-actions">
        {a.edit === true && !(oneRow && a.establish === true) && <button className="r2-primary" onClick={() => prepare('edit')}>{a.edit_mode === 'proposed' ? 'Propose new version…' : 'Revise…'}</button>}
        {a.establish === true && <button className="r2-primary" onClick={() => void approve(id)}>Establish…</button>}
        {a.dispute === true && <button onClick={() => { setDialog('dispute'); setApproval(null) }}>Dispute…</button>}
        {!oneRow && persona && <button onClick={onPreview}>Preview</button>}
      </div>
      <details className="r2-more"><summary>More</summary>
        {oneRow && a.edit === true && a.establish === true && <button onClick={() => prepare('edit')}>{a.edit_mode === 'proposed' ? 'Propose new version…' : 'Revise…'} <small>Writes a new version beside this one.</small></button>}
        {oneRow && persona && <button onClick={onPreview}>Preview <small>What a run started as this persona would receive. Writes nothing.</small></button>}
        {a.supersede === true && <button onClick={() => prepare('replace')}>Replace with another… <small>Ends this with an established successor.</small></button>}
        {a.place === true && <button onClick={() => prepare('place')}>Place… <small>In a Conversation, or on the Whole Brain. Adds a placement.</small></button>}
        {a.unplace === true && placements.map(p => <button key={p.where} onClick={() => { prepare('unplace'); setEnding(p) }}>End placement in {placeName(p)}… <small>Stops its reach there; history stays.</small></button>)}
        {a.set_aside === true && <Bounded items={(challenges.data?.disputes ?? []).filter(x => x.open)} label="Open challenges">{x => <button key={x.link} onClick={() => { setDispute(x); setDialog('set-aside'); setApproval(null) }}>Set aside… <small>{x.reason ?? 'Open dispute'}</small></button>}</Bounded>}
        {a.delete === true && <button onClick={() => prepare('delete')}>Delete… <small>Ends this record; history stays.</small></button>}
      </details>
    </div>),
    meta: (d && <p className="r2-meta">Recorded by {d.author_alias ?? 'an unattributed author'}{d.at ? ` · ${when(d.at)}` : ''}</p>),
    error: (error && <p className="r2-error" role="alert">{error}</p>),
    said: (said && <p role="status" className="r2-effect">{said}</p>),
    placements: (d && placements.length > 0 && <p className="r2-meta" aria-label="Placements">Placed: {placements.map(p => p.whole_brain
      ? 'Whole Brain (every Conversation, now and later, and Brain-scope work)' : p.persona ? `carried by ${placeName(p)}` : placeName(p)).join(' · ')}</p>),
    warnings: (d && Object.values(form).some(f => f.input === 'activities') && <ActivityWarnings id={id} />),
    carries: (d && carries.length > 0 && <p className="r2-meta" aria-label="Carries">{d.kind === 'persona' ? 'Disciplines it carries' : 'Carries'}: {carries.map(c =>
      `${c.name || c.entry}${c.kind && c.kind !== 'discipline' ? ` (${c.kind})` : ''}${c.stands ? '' : ' (not established; carries nothing yet)'}`).join(' · ')}</p>),
    proposed: (proposed && <div className="r2-effect">New version proposed. The current one keeps standing.
      <div className="r2-actions"><button onClick={() => onInspect(proposed)}>Inspect proposal</button><button onClick={() => void approve(proposed)}>Establish proposal…</button></div></div>),
    form: (open && d && <section className="r2-inline-form" role="group" aria-label={open}>
      <h3>{open === 'edit' ? editWords.go : open === 'place' ? 'Place this material' : open === 'unplace' ? `End placement in ${ending ? placeName(ending) : ''}` : open === 'replace' ? 'Replace with another' : 'Delete this material'}</h3>
      {open === 'edit' && <>{fields.map(f => {
        const input = inputOf(f)
        const set = (v: string) => setValues({ ...values, [f]: v })
        if (input === 'activities') return <ActivitiesInput key={f} field={`New ${f}`} label={form[f]?.label ?? f} value={values[f] ?? was(f)} onChange={set} />
        if (input === 'participant' || input === 'persona') return <EntrySelect key={f} input={input} field={`New ${f}`} label={form[f]?.label ?? f} value={values[f] ?? was(f)} onChange={set} />
        return <label key={f}>{form[f]?.label ?? f}<textarea aria-label={`New ${f}`} value={values[f] ?? was(f)} onChange={e => set(e.target.value)} />{listed(f) && <small>One per line.</small>}</label>
      })}
        <p className="r2-effect">{editWords.note}</p>
        {a.edit_mode === 'proposed' && <label className="r2-check"><input type="checkbox" checked={immediate} onChange={e => setImmediate(e.target.checked)} />Propose, then open Establish with a reason</label>}
      </>}
      {open === 'place' && <><label>Where it applies<select aria-label="Place conversation" value={where} onChange={e => setWhere(e.target.value)}><option value="">Choose where it applies</option>
        <option value={WHOLE_BRAIN} disabled={a.place_whole_brain !== true}>Whole Brain: every Conversation and Brain-scope work</option>
        {Object.entries(choices).map(([id, name]) => <option key={id} value={id}>{name}</option>)}
        {Object.keys(personaNames).length > 0 && <optgroup label="Personas">{Object.entries(personaNames).map(([id, name]) => <option key={id} value={id}>Persona: {name}</option>)}</optgroup>}</select></label>
        {where === WHOLE_BRAIN
          ? <p className="r2-effect">It will apply to whoever acts in every Conversation, including ones opened later, and to work at Brain scope. Only established material whose Kind directs work can go here. A later established replacement keeps the placement; a proposal does not reach anyone until it is established.</p>
          : personaNames[where]
            ? <p className="r2-effect">The Persona will carry it: it reaches whoever operates as {personaNames[where]}, in any Conversation, and nobody else. You can end it later with End placement; nothing is erased.</p>
            : <p className="r2-effect">This adds a placement. You can end it later with End placement; nothing is erased. Placing a proposal does not establish it.</p>}
        {a.place_whole_brain !== true && a.whole_brain_why_not && <p className="r2-dim">Whole Brain is not available: {String(a.whole_brain_why_not)}.</p>}</>}
      {open === 'unplace' && ending && <p className="r2-effect">{ending.whole_brain
        ? 'It stops applying everywhere it reached only through the Whole Brain. Placements in individual Conversations stay. The ended placement remains in the history.'
        : ending.persona ? 'That Persona stops carrying it. Other placements stay. The ended placement remains in the history.'
        : 'It stops applying in this Conversation. Other placements stay. The ended placement remains in the history.'}</p>}
      {open === 'replace' && <><label>Existing successor reference<input aria-label="Successor reference" value={replacement} onChange={e => setReplacement(e.target.value)} /></label>
        {successor.loading && <p>Reading successor…</p>}{successor.data && <p className="r2-prose">{successor.data.fields.map(f => String(successor.data!.body[f] ?? '')).join('\n')} · {successor.data.stands ? 'In force' : 'Not established'}</p>}
        <p className="r2-effect">The successor must already stand, be the same Kind, and cover every existing placement. These are checked before the replacement is recorded.</p></>}
      {open === 'delete' && <p className="r2-effect">Nothing is erased. This ends its use and keeps its history. There is no undelete.</p>}
      <label>{open === 'place' || open === 'unplace' || open === 'replace' ? 'Reason (required)' : 'Reason (optional)'}<textarea aria-label="Record reason" value={reason} onChange={e => setReason(e.target.value)} /></label>
      <div className="r2-actions"><button disabled={busy} onClick={() => prepare(null)}>Cancel</button><button className="r2-primary" disabled={busy} onClick={() => void run(async () => {
        if ((open === 'place' || open === 'unplace' || open === 'replace') && !reason.trim()) throw new Error('Say why first.')
        if (open === 'edit') {
          const body = Object.fromEntries(fields.filter(f => (values[f] ?? was(f)) !== was(f)).map(f => [f, fieldValue(values[f], form[f]?.input)]))
          if (!Object.keys(body).length) throw new Error('Change the text first.')
          const r = await editEntry(id, me, { body, because: reason.trim() })
          setSaid(r.says); setOpen(null)
          if (r.mode === 'proposed') { setProposed(r.version); if (immediate) await approve(r.version) }
          else onInspect(r.version)
        } else if (open === 'place') {
          if (!where) throw new Error('Choose where it applies.')
          if (where === WHOLE_BRAIN) {
            const r = await post<{ already?: boolean }>(`/api/entries/${id}/place`, { attributed_to: me, whole_brain: true, because: reason.trim() })
            setSaid(r.already ? 'Already placed on the Whole Brain; nothing was recorded.' : 'Placed on the Whole Brain.')
          } else {
            await post(`/api/entries/${id}/place`, { attributed_to: me, where, because: reason.trim() }); setSaid(personaNames[where] ? `Placed on the persona ${personaNames[where]}.` : `Placed in ${choices[where]}.`)
          }
          setOpen(null)
        } else if (open === 'unplace') {
          if (!ending) throw new Error('Choose a placement to end.')
          await post(`/api/entries/${id}/unplace`, ending.whole_brain
            ? { attributed_to: me, whole_brain: true, because: reason.trim() }
            : { attributed_to: me, where: ending.where, because: reason.trim() })
          setSaid(`Placement in ${placeName(ending)} ended.`); setEnding(null); setOpen(null)
        } else if (open === 'replace') {
          if (!replacement.trim()) throw new Error('Name an existing successor.')
          await supersede(id, replacement.trim(), me, reason.trim()); setSaid('Replaced; this record is now read-only.'); setOpen(null)
        } else {
          await deleteEntry(id, me, reason.trim()); setSaid('Deleted; history is kept.'); setOpen(null)
        }
      })}>{busy ? 'Recording…' : open === 'edit' ? (a.edit_mode === 'proposed' ? 'Record proposal' : editWords.go) : open === 'place' ? 'Record placement' : open === 'unplace' ? 'End placement' : open === 'replace' ? 'Replace now' : 'Delete material'}</button></div>
    </section>),
    /* In place (Fluid), another act can be chosen while one is open, so each
       act, challenge and successor gets a fresh form. Classic's dialog is
       modal and keeps its own lifetime: no key there. */
    dialog: (dialog && item && <ActDialog key={inline ? `${dialog}:${dispute?.link ?? ""}:${approval?.successor.entry ?? ""}` : undefined} inline={inline} act={dialog} item={approval?.successor ?? item} ends={approval?.ends}
      dispute={dispute} me={me} onCancel={() => { setDialog(null); setApproval(null) }} onDone={outcome => {
        setDialog(null); setApproval(null); setSaid(outcome.said); changed()
        if (outcome.entry && outcome.entry !== id) onInspect(outcome.entry)
      }} />),
    /** which inline form or act is open, so a host can make room for it */
    acting: (open && d ? open : null) ?? (dialog && item ? dialog : null),
  }
}

export default function R2Record({ conversationName, onGoToTurn, ...props }: RecordActsProps & {
  conversationName?: string | null
  onGoToTurn?: (id: Id) => void
}) {
  const { id, conversation, onInspect } = props
  const r = useRecordActs(props)
  return <div className="r2-record">
    {r.meta}
    {r.error}
    {r.said}
    {r.actions}
    {r.placements}
    {r.warnings}
    {r.carries}
    {r.proposed}
    {r.form}
    <EntryInspect id={id} readOnly governance conversation={conversation} conversationName={conversationName}
      onOpenEntry={onInspect} onGoToTurn={onGoToTurn} />
    <details className="r2-fold"><summary>Cited by</summary><p className="r2-dim">{CITED_BY}</p></details>
    {r.dialog}
  </div>
}
