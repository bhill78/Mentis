/* A CONVERSATION'S INSTRUCTIONS, read from its header.
 *
 * What applies in this conversation now, what has been proposed for it, and
 * what used to apply. Writing a new one opens the same compact editor every
 * other Brain record is written in, with this conversation already chosen,
 * and it records a PROPOSAL: nothing is put in effect from here. (This box
 * used to hold its own form, which established whatever was typed at once.)
 *
 * An instruction listed here opens as its record, where it can be read in
 * full, revised, and established by the owner. */
import { useApi, type Id } from '../../../api'
import {
  instructionGroups, instructionsPath,
  type ConversationInstructionRow, type ConversationInstructionsRead,
} from '../../../fluid/conversation/instructionsModel'

function Rows({ rows, empty, onOpen }: { rows: ConversationInstructionRow[]; empty: string; onOpen: (id: Id) => void }) {
  if (!rows.length) return <p className="ba-none">{empty}</p>
  return <ul className="ba-ci-list">{rows.map((row) => <li key={row.entry}>
    <button type="button" className="ba-ci-row" onClick={() => onOpen(row.entry)} title="Open this instruction">
      <span>{row.text || 'Instruction with no words'}</span>
      <small>{row.written_by ?? 'Unattributed'}</small>
    </button>
  </li>)}</ul>
}

export default function InstructionsPanel({ conversation, name, canWrite, onNew, onOpen }: {
  conversation: Id; name: string; canWrite: boolean
  onNew: () => void
  onOpen: (id: Id) => void
}) {
  const got = useApi<ConversationInstructionsRead>(instructionsPath(conversation))
  const groups = instructionGroups(got.data)
  return (
    <div className="ba-ci" data-instructions={conversation}>
      <header><h2>Instructions</h2><p>For this conversation · {name || 'Unnamed'}</p></header>
      {canWrite && <button type="button" className="ba-btn" data-new-instruction autoFocus onClick={onNew}>New instruction…</button>}
      {canWrite && <p className="ba-hint">A new instruction is recorded as a proposal. It applies once you establish it.</p>}
      {got.error && <p className="ba-err" role="alert">Could not read instructions: {got.error}</p>}
      {!got.data && !got.error && <p className="ba-none" aria-busy="true">Reading this conversation’s instructions…</p>}
      {got.data && <>
        <section aria-label="In effect here"><h3>In effect here <span>{groups.current.length}</span></h3>
          <Rows rows={groups.current} empty="No instruction is in effect in this conversation." onOpen={onOpen} /></section>
        <details open={groups.pending.length > 0}><summary>Proposed, not in effect <span>{groups.pending.length}</span></summary>
          <Rows rows={groups.pending} empty="Nothing is proposed for this conversation." onOpen={onOpen} /></details>
        <details><summary>History <span>{groups.history.length}</span></summary>
          <Rows rows={groups.history} empty="Nothing has ended or been replaced." onOpen={onOpen} /></details>
      </>}
    </div>
  )
}
