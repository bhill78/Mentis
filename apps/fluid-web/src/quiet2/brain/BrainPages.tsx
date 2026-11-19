/* THE BRAIN, IN THE MAIN READING AREA (Manage Brain in Quiet Chat).
 *
 * "Opened from the Brain browser, a record takes the main reading area. Back
 * returns to the browser with its filter" (DESIGN-r2.md, Navigation §3). The
 * conversation is not replaced and not re-read: it waits underneath, and its
 * reading position is put back when the reader returns (Quiet2.tsx).
 *
 * WHAT IS SHOWN HERE is a short stack: a record; another record reached from
 * it (its basis, what cites it, what replaced it), with Back to the one
 * before; and importing an archive (the same `ImportArchiveTab` Governance
 * uses, hosted here). MAKING A RECORD IS NOT A PAGE: it is the compact
 * editor (`author/AuthorModal`), opened over whatever is here. No tab row,
 * no second column: one thing at a time, and Back. */
import { useRef } from 'react'
import type { Id } from '../../api'
import ImportArchiveTab, { type ImportHeld } from '../../fluid/governance/ImportArchiveTab'
import { useUnfinished } from '../leaving'
import { importing } from './importing'
import { backWords, heldItem, type BrainMainState } from './logic'
import BrainRecord from './BrainRecord'
import EntryInspect from '../../surfaces/EntryInspect'
import { useHeld } from '../../surfaces/DurableKind'
import { isAdmission } from '../space/routing'
import { useBrainNav } from './nav'
import '../../fluid/governance/governance.css'
import './brainRecord.css'

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

/* AN ENTRY THAT IS NOT A RECORD TO MANAGE (3D Brain, addendum §4): a topic,
 * a participant, a piece of the record's substrate, a held admission. The
 * EXISTING read-only inspector reads it -- explicitly read-only, with its own
 * body and links -- rather than a second record presentation being invented
 * for things Manage Brain does not manage. Its links are dispatched anew by
 * whoever hosts this page, so a post it points at is read as a post. */
function EntryPage({ entry }: { entry: Id }) {
  const nav = useBrainNav()
  /* EVERY LINK IS DISPATCHED BY WHAT IT IS, not by what this page is: the
     host resolves the id's own kind and chooses its reader (routing.ts). A
     host with no such dispatcher is not offered the links at all, rather than
     being given a record page for a Turn. */
  const dispatch = nav.openEntry
  /* HELD BYTES ARE OPENED, NOT JUST DESCRIBED (addendum §4's Admission row;
     review R4). The inspector already has the opener; it draws it only when
     it is given somewhere to open. This reads what the server says it holds
     -- the read the inspector makes for its own description, content-addressed
     and not live -- and offers the existing viewer for it. Bytes Mentis no
     longer holds give no item, and so no opener. */
  const about = useHeld(isAdmission(entry) ? entry : null)
  const item = heldItem(entry, about.data)
  const open = nav.openMedia
  return (
    <div className="rv rv-full rv-entry" data-entry-inspect={entry}>
      <EntryInspect readOnly id={entry}
        onOpenEntry={(id) => (dispatch ?? nav.openRecord)(id)}
        onGoToTurn={dispatch}
        onOpenParticipant={dispatch}
        onOpenMedia={open && item ? () => open(entry, item) : undefined} />
    </div>
  )
}

export default function BrainMain({ state, canWrite, onBack, onLeave }: {
  state: BrainMainState
  canWrite: boolean
  /** one step back: the record before, or out to where the reader came from */
  onBack: () => void
  /** straight back to the conversation, wherever this was reached from */
  onLeave: () => void
}) {
  const view = state.stack[state.stack.length - 1]
  const out = state.stack.length === 1
  return (
    <div className="q2-stream q2-brain-main" data-brain-page={view.page}>
      <div className="q2-back-bar rv-backbar">
        <button type="button" className="q2-back-btn" data-brain-back onClick={onBack}>‹ {backWords(state)}</button>
        <span className="q2-back-where">{view.page === 'record' ? 'Brain record' : view.page === 'import' ? 'Import an archive' : 'Entry'}</span>
        {!(out && state.origin.from !== 'browser') && <button type="button" className="q2-link-quiet" onClick={onLeave}>Back to the conversation</button>}
      </div>
      {view.page === 'record' && <BrainRecord key={view.entry} entry={view.entry} variant="full" />}
      {view.page === 'entry' && <EntryPage key={view.entry} entry={view.entry} />}
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
