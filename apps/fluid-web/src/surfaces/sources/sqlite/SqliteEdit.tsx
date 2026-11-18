import type { Id } from '../../../api'
import type { CollectionView, Descriptor } from '../route'
import SqliteFlow, { type SqliteHeld } from './SqliteFlow'
export default function SqliteEdit({ collection, descriptor, me, onChanged, onHolding, onOpen }: { collection: CollectionView; descriptor: Descriptor; me: Id|null; onChanged: ()=>void
  /** what the editor holds unrecorded, for a host that guards leaving */
  onHolding?: (held:SqliteHeld|null)=>void
  /** "Open <name>" after a revise: the host shows the source's own page. The
   *  editor is drawn INSIDE that page, so only the host knows how to get
   *  there (it used to be handed nothing, and the button did nothing). */
  onOpen: ()=>void }) {
  return <SqliteFlow key={collection.collection} editing={collection} descriptor={descriptor} me={me} onChanged={onChanged} onHolding={onHolding} go={r=>{if(r.at==='collection')onOpen()}}/>
}
