import type { Id } from '../../../api'
import type { CollectionView, Descriptor } from '../route'
import SqliteFlow, { type SqliteHeld } from './SqliteFlow'
export default function SqliteEdit({ collection, descriptor, me, onChanged, onHolding }: { collection: CollectionView; descriptor: Descriptor; me: Id|null; onChanged: ()=>void
  /** what the editor holds unrecorded, for a host that guards leaving */
  onHolding?: (held:SqliteHeld|null)=>void }) {
  return <SqliteFlow key={collection.collection} editing={collection} descriptor={descriptor} me={me} onChanged={onChanged} onHolding={onHolding} go={()=>{}}/>
}
