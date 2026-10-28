import type { Chosen } from './chosen'

/* ------------------------------------------------------------------------ *
 * THE COMPACT INDICATOR: what the chosen thing is, and what it says.
 *
 * Not a detail panel (owner: keep Mark III's out). A heading -- its kind and
 * its Conversation, wrapping rather than cut -- then what it says in up to
 * four lines, then OPEN, which is still the way to the whole record, and ×.
 * ------------------------------------------------------------------------ */

export interface ChosenCardProps {
  chosen: Chosen
  conversation: string | null
  onOpen: () => void
  onClose: () => void
  /** given, the card can be dragged out, carrying the chosen thing (Fluid) */
  onDrag?: (e: React.DragEvent) => void
}

export default function ChosenCard({ chosen, conversation, onOpen, onClose, onDrag }: ChosenCardProps) {
  const n = chosen.node
  const kind = n.kind === 'contribution' ? 'turn' : n.kind
  return (
    <div className="space-chosen" role="status" data-reading={chosen.reading ? 'true' : undefined}
      draggable={onDrag ? true : undefined} onDragStart={onDrag}
      title={onDrag ? 'Drag into a section or the composer to use it by reference' : undefined}>
      <span className="space-chosen-kind">
        {kind}
        {n.kind !== 'conversation' && conversation && <> · {conversation}</>}
        {n.deleted && <> · deleted</>}
        {n.edited && <> · edited</>}
        {n.replaced && <> · replaced</>}
      </span>
      <span className="space-chosen-said">{chosen.said ?? (n.deleted ? 'Deleted; its words are not shown.' : n.entry)}</span>
      <span className="space-chosen-do">
        <button type="button" className="space-open" onClick={onOpen}>
          Open
        </button>
        <button type="button" className="space-tool" aria-label="Let go" onClick={onClose}>
          ×
        </button>
      </span>
    </div>
  )
}
