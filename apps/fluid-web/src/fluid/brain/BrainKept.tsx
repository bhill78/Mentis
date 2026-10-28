/* A THING FROM THE 3D BRAIN, KEPT IN A SECTION (Zones.tsx), by reference.
 *
 * The section keeps only its address, `brain:<entry>` (address.ts); this
 * draws it as the record has it now: its kind, its words, its entry id, and
 * -- asked for (◨ Open) -- the record inspector, read only, as it was over
 * the Brain; the object action row offers the rest.
 * Moved between sections as any kept card is (keep.tsx `DRAG`, with the
 * section it is kept in), and taken out with ×. Nothing here writes. */

import { lazy, Suspense, useState } from 'react'
import { qs, useApi } from '../../api'
import { DRAG } from '../workspace/keep'
import { entryOfRef } from './address'
import { ObjectActions } from '../objects/ObjectActions'
import './kept.css'

/* The inspector is loaded when somebody asks for it, not with every section. */
const EntryInspect = lazy(() => import('../../surfaces/EntryInspect'))

interface Said { entry: string; said: string | null; deleted: boolean; edited: boolean }
interface Entry { kind: string | null; missing?: boolean }

export default function BrainKept({ refs, zone, page, onRemove }: {
  refs: string[]; zone: string; page: string; onRemove: (address: string) => void
}) {
  return <>{refs.map((a) => <One key={a} address={a} zone={zone} page={page} onRemove={() => onRemove(a)} />)}</>
}

function One({ address, zone, page, onRemove }: { address: string; zone: string; page: string; onRemove: () => void }) {
  const entry = entryOfRef(address) ?? ''
  const said = useApi<Said>(`/api/space/said${qs({ entry })}`, { live: false })
  const rec = useApi<Entry>(`/api/entries/${encodeURIComponent(entry)}`, { live: false })
  const [open, setOpen] = useState(false)
  /* What the inspector shows: this entry, or one it leads to, followed in
     place with the way back to this one. */
  const [shown, setShown] = useState(entry)
  const kind = rec.data?.kind === 'contribution' ? 'turn' : rec.data?.kind ?? 'entry'
  const words = said.data?.deleted ? 'Deleted; its words are not shown.' : said.data?.said ?? (said.error ? null : 'Reading…')
  return (
    <article className="wk-obj bz-kept" data-address={address} data-entry={entry}
      draggable onDragStart={(e) => {
        e.dataTransfer.setData(DRAG, JSON.stringify({ address, kept: true, zone, page }))
        e.dataTransfer.setData('text/plain', entry)
        e.dataTransfer.effectAllowed = 'copyMove'
      }}>
      <header className="bz-kept-head">
        <span className="bz-kind">{kind}</span>
        <span className="wk-quiet">from the 3D Brain</span>
        <span className="wk-grow" />
        {/* THE ONE ACTION ROW (objects/actions.ts): Open is this card's own
            detail, the record inspector unfolded here; Peek reads it over
            the workspace without changing anything */}
        <ObjectActions compact target={{ address, kind: 'brain', title: words && !said.data?.deleted ? words.slice(0, 80) : entry, from: 'the 3D Brain', zone, page }}
          onOpen={() => setOpen(true)} />
        {open && <button type="button" className="wk-quietlink" aria-expanded={open} onClick={() => setOpen(false)}>Less</button>}
        <button type="button" className="fl-btn" aria-label="Take it out of this section" title="Take it out" onClick={onRemove}>×</button>
      </header>
      {words && <p className="bz-kept-said">{words}</p>}
      {rec.data?.missing && <p className="wk-quiet">The record has no such entry.</p>}
      <code className="bz-id" title="Its entry in the record">{entry}</code>
      {open && (
        <div className="bz-kept-read" draggable={false} onDragStart={(e) => e.stopPropagation()}>
          {shown !== entry && <button type="button" className="wk-quietlink" onClick={() => setShown(entry)}>‹ Back to {kind}</button>}
          <Suspense fallback={<p className="wk-quiet" aria-busy="true">Reading…</p>}>
            <EntryInspect key={shown} id={shown} readOnly onOpenEntry={setShown} />
          </Suspense>
        </div>
      )}
    </article>
  )
}
