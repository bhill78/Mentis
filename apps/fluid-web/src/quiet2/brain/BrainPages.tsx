/* THE BRAIN, IN THE MAIN READING AREA (Manage Brain in Quiet Chat).
 *
 * "Opened from the Brain browser, a record takes the main reading area. Back
 * returns to the browser with its filter" (DESIGN-r2.md, Navigation §3). The
 * conversation is not replaced and not re-read: it waits underneath, and its
 * reading position is put back when the reader returns (Quiet2.tsx).
 *
 * WHAT IS SHOWN HERE is a short stack: a record; another record reached from
 * it (its basis, what cites it, what replaced it), with Back to the one
 * before; and the two things the old Governance page did that are not a
 * record -- making one (the same creation form, `R2Create`) and importing an
 * archive (the same `ImportArchiveTab`). Nothing is rebuilt: those forms are
 * the ones Governance uses, hosted here, so who may establish, what is
 * proposed, and what an import stages are exactly what they were. No tab
 * row, no second column: one thing at a time, and Back. */
import { useRef } from 'react'
import { useApi, type Id } from '../../api'
import ImportArchiveTab, { type ImportHeld } from '../../fluid/governance/ImportArchiveTab'
import { authoring, useUnfinished } from '../leaving'
import { importing } from './importing'
import R2Create from '../../surfaces/governance/R2Forms'
import type { KindAuthoring } from '../../surfaces/governance/r2Model'
import { backWords, kindWords, type BrainMainState, type BrainMainView } from './logic'
import BrainRecord from './BrainRecord'
import '../../fluid/governance/governance.css'
import './brainRecord.css'

function NewRecord({ kind, basis, me, onCancel, onDone }: {
  kind: string; basis?: Id; me: Id | null; onCancel: () => void; onDone: (id: Id) => void
}) {
  const definitions = useApi<{ kinds: KindAuthoring[] }>('/api/governance/authoring')
  const convs = useApi<{ conversations: { id: Id; name: string }[] }>('/api/conversations')
  /* A RECORD BEING WRITTEN IS THE CLEAREST THING THERE IS TO LOSE: it exists
     nowhere but this page until it is recorded. The builder says whether it
     holds anything (`onUnsaved`); the page says what it is, and Quiet Chat's
     one question does the rest (`leaving.ts`). Its own Cancel says so first,
     so discarding it deliberately is never asked about twice. */
  const held = useRef(false)
  useUnfinished(() => (held.current ? authoring(`this new ${kindWords(kind).toLowerCase()}`) : null))
  const kinds = definitions.data?.kinds ?? []
  const section = kinds.find((k) => k.kind === kind)?.authoring?.section
  const offered = kinds.filter((k) => k.authoring?.section === section)
  const names = Object.fromEntries((convs.data?.conversations ?? []).map((c) => [c.id, c.name]))
  return (
    <div className="rv rv-full rv-author">
      <p className="rv-kind">New · {kindWords(kind)}</p>
      {definitions.error && <p className="q2m-faint" role="alert">Could not read what can be made: {definitions.error} <button type="button" className="rv-link" onClick={definitions.reload}>Retry</button></p>}
      {!definitions.data && !definitions.error && <p className="q2m-faint" role="status">Reading…</p>}
      {definitions.data && !offered.length && <p className="q2m-faint" role="alert">This Brain does not offer making a {kindWords(kind).toLowerCase()} here.</p>}
      {offered.length > 0 && (
        <div className="rv-host fg-create" role="group" aria-label="Create governed material">
          <R2Create key={kind + ':' + (basis ?? '')} kinds={offered} initial={kind} conversation={null} names={names} me={me} basis={basis}
            onUnsaved={(u) => { held.current = u }} onCancel={onCancel} onDone={onDone} />
        </div>
      )}
    </div>
  )
}

/* IMPORTING AN ARCHIVE is the same page Governance uses, hosted here, and it
 * holds exactly one thing nothing else has: an archive chosen and read whose
 * plan has not been staged. It says so (`onHolding`) and the one rule
 * (`importing.ts`) turns that into the question; what has already been staged
 * is on disk, read back here, and is never asked about. */
function ImportPage() {
  const held = useRef<ImportHeld | null>(null)
  useUnfinished(() => (held.current ? importing(held.current) : null))
  return <div className="rv-host rv-import"><ImportArchiveTab onHolding={(h) => { held.current = h }} /></div>
}

export default function BrainMain({ state, me, canWrite, onBack, onLeave, onReplace }: {
  state: BrainMainState
  me: Id | null
  canWrite: boolean
  /** one step back: the record before, or out to where the reader came from */
  onBack: () => void
  /** straight back to the conversation, wherever this was reached from */
  onLeave: () => void
  /** the page shown becomes this one (a record just made) */
  onReplace: (view: BrainMainView) => void
}) {
  const view = state.stack[state.stack.length - 1]
  const out = state.stack.length === 1
  return (
    <div className="q2-stream q2-brain-main" data-brain-page={view.page}>
      <div className="q2-back-bar rv-backbar">
        <button type="button" className="q2-back-btn" data-brain-back onClick={onBack}>‹ {backWords(state)}</button>
        <span className="q2-back-where">{view.page === 'record' ? 'Brain record' : view.page === 'import' ? 'Import an archive' : 'New record'}</span>
        {!(out && state.origin.from !== 'browser') && <button type="button" className="q2-link-quiet" onClick={onLeave}>Back to the conversation</button>}
      </div>
      {view.page === 'record' && <BrainRecord key={view.entry} entry={view.entry} variant="full" />}
      {view.page === 'new' && (canWrite
        ? <NewRecord kind={view.kind} basis={view.basis} me={me} onCancel={onBack} onDone={(id) => onReplace({ page: 'record', entry: id })} />
        : <div className="rv rv-full"><p className="q2m-faint" role="alert">This page is read-only: nothing can be made here.</p></div>)}
      {view.page === 'import' && (
        <div className="rv rv-full rv-author">
          <p className="rv-kind">Import an archive</p>
          {canWrite ? <ImportPage />
            : <p className="q2m-faint" role="alert">This page is read-only: nothing can be imported here.</p>}
        </div>
      )}
    </div>
  )
}
