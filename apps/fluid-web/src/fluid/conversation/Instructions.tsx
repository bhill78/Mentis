import { useState, type FormEvent } from 'react'
import { post, useApi, type Id } from '../../api'
import { store } from '../store'
import {
  establishInstructionBody,
  instructionGroups,
  instructionsPath,
  type ConversationInstructionRow,
  type ConversationInstructionsRead,
} from './instructionsModel'

function InstructionList({ rows, empty }: { rows: ConversationInstructionRow[]; empty: string }) {
  if (!rows.length) return <p className="ci-empty">{empty}</p>
  return <ul className="ci-list">{rows.map((row) => <li key={row.entry}>
    <p>{row.text || 'Instruction with no display text'}</p>
    <small>{row.written_by ?? row.attributed_to ?? 'Unattributed'} · {row.entry}</small>
  </li>)}</ul>
}

/** Conversation-local authoring and status, deliberately narrower than the
 * Brain-wide Governance workspace. */
export default function ConversationInstructions({ conversation, name }: { conversation: Id; name: string }) {
  const got = useApi<ConversationInstructionsRead>(instructionsPath(conversation))
  const groups = instructionGroups(got.data)
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [created, setCreated] = useState<Id | null>(null)
  const me = store.me
  const submit = async (event: FormEvent) => {
    event.preventDefault()
    const instruction = text.trim()
    setError(null)
    setCreated(null)
    if (!instruction) return setError('Write the instruction first.')
    if (!me) return setError('An attributed owner is needed to establish an instruction.')
    setBusy(true)
    try {
      const result = await post<{ entry: Id }>(`/api/conversations/${encodeURIComponent(conversation)}/instructions`, establishInstructionBody(instruction, me))
      setText('')
      setCreated(result.entry)
      got.reload()
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }
  return <div className="ci-surface">
    <header className="ci-head">
      <div><h2>Instructions</h2><p>For this conversation · {name || conversation}</p></div>
    </header>
    <p className="ci-scope">These instructions apply to everyone working in this conversation. They are separate from rules that govern the whole Brain.</p>
    <form className="ci-compose" onSubmit={(event) => void submit(event)}>
      <label htmlFor="conversation-instruction-text">Add an instruction for this conversation</label>
      <textarea id="conversation-instruction-text" value={text} rows={3} autoFocus
        placeholder="What should everyone working here be told?" onChange={(event) => setText(event.target.value)} />
      <div className="ci-compose-foot">
        <small>This will be established immediately as a current instruction.</small>
        <button type="submit" disabled={busy || !me}>{busy ? 'Establishing…' : 'Establish instruction'}</button>
      </div>
    </form>
    {created && <p className="ci-success" role="status">Instruction established for this conversation.</p>}
    {error && <p className="ci-error" role="alert">{error}</p>}
    {got.error && <p className="ci-error" role="alert">Could not read instructions: {got.error}</p>}
    {!got.data && !got.error && <p className="ci-empty" aria-busy="true">Reading this conversation’s instructions…</p>}
    {got.data && <>
      <section className="ci-group" aria-labelledby="ci-current"><h3 id="ci-current">Current in this conversation <span>{groups.current.length}</span></h3>
        <InstructionList rows={groups.current} empty="No current conversation instructions." />
      </section>
      <details className="ci-group"><summary>Proposed or recorded, not current <span>{groups.pending.length}</span></summary>
        <p className="ci-note">These do not govern work unless the owner establishes them.</p>
        <InstructionList rows={groups.pending} empty="No proposals for this conversation." />
      </details>
      <details className="ci-group"><summary>History <span>{groups.history.length}</span></summary>
        <p className="ci-note">Ended and replaced instructions remain in the record.</p>
        <InstructionList rows={groups.history} empty="No ended or replaced instructions." />
      </details>
    </>}
  </div>
}
