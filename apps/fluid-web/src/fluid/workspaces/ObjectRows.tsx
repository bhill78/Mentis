/* A WORKSPACE'S OBJECTS, in their curated order: each as it was curated, with where
 * it came from. `curated` is said on every row and is never a claim about the
 * record, so nothing here says a reference is valid, current or within anybody's
 * reach. A name is only what this tab already knows of it (`known`), for reading;
 * the reference itself is always shown, and no reference is read to draw a row. */

import type { ObjectId, WorkspaceObject } from './client'

const KIND_WORD: Record<string, string> = {
  magnet: 'Magnet', conversation: 'Conversation', chat: 'Chat', file: 'File', image: 'Image',
  evidence: 'Evidence', report: 'Report', participant: 'Participant', other: 'Other',
}
export const kindWord = (kind: string) => KIND_WORD[kind] ?? kind

/** Where it came from, in the record's kind/ref terms. */
export function provenanceWords(o: Pick<WorkspaceObject, 'provenance'>): string {
  const { source, by } = o.provenance
  const from = source.kind === 'participant' ? 'chosen by' : `from ${kindWord(source.kind).toLowerCase()}`
  return `${from} ${source.ref}${by && by !== source.ref ? `, by ${by}` : ''}`
}

export interface RowActs {
  selected: ReadonlySet<ObjectId>
  toggle(oid: ObjectId): void
  move(oid: ObjectId, by: number): void
  drop(oid: ObjectId, onto: ObjectId): void
  remove(oid: ObjectId): void
  /** what opening it is called, and doing it; none where it has no way to open */
  open(o: WorkspaceObject): { label: string; run: (at: HTMLElement) => void } | null
  known(o: WorkspaceObject): string | null
  busy: boolean
}

const ROW = 'application/x-mentis-workspace-object'

export default function ObjectRows({ objects, acts }: { objects: readonly WorkspaceObject[]; acts: RowActs }) {
  return (
    <ol className="wo-rows" aria-label="what this workspace holds">
      {objects.map((o, i) => {
        const open = acts.open(o)
        const name = acts.known(o)
        return (
          <li key={o.id} className="wo-row" data-object={o.id} data-kind={o.kind} draggable
            onDragStart={(e) => { e.dataTransfer.setData(ROW, o.id); e.dataTransfer.effectAllowed = 'move' }}
            onDragOver={(e) => { if (e.dataTransfer.types.includes(ROW)) e.preventDefault() }}
            onDrop={(e) => {
              const from = e.dataTransfer.getData(ROW)
              if (!from) return
              e.preventDefault(); e.stopPropagation()
              if (from !== o.id) acts.drop(from, o.id)
            }}>
            <label className="wo-pick" title="Use this object in the request below">
              <input type="checkbox" checked={acts.selected.has(o.id)} onChange={() => acts.toggle(o.id)}
                aria-label={`select ${kindWord(o.kind)} ${name ?? o.ref} for a request`} />
            </label>
            <div className="wo-what">
              <div className="wo-line">
                <span className="wo-kind">{kindWord(o.kind)}</span>
                <b className="wo-name">{name ?? o.ref}</b>
                {o.curated && <span className="wo-curated" title="Somebody chose this reference. It says nothing of what the record now holds.">curated</span>}
              </div>
              {name && <div className="wo-ref">{o.ref}</div>}
              <div className="wo-from" data-provenance>{provenanceWords(o)}</div>
            </div>
            <div className="wo-acts">
              {open && <button className="fx-ctl" disabled={acts.busy} onClick={(e) => open.run(e.currentTarget)}>{open.label}</button>}
              <button className="fx-ctl" disabled={acts.busy || i === 0} aria-label={`move ${name ?? o.ref} up`} title="Earlier" onClick={() => acts.move(o.id, -1)}>↑</button>
              <button className="fx-ctl" disabled={acts.busy || i === objects.length - 1} aria-label={`move ${name ?? o.ref} down`} title="Later" onClick={() => acts.move(o.id, 1)}>↓</button>
              <button className="fx-ctl" disabled={acts.busy} aria-label={`remove ${name ?? o.ref} from this workspace`}
                title="Take it out of this workspace. What it refers to is not touched." onClick={() => acts.remove(o.id)}>×</button>
            </div>
          </li>
        )
      })}
    </ol>
  )
}
