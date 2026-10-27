import type { Id } from '../../../api'
import type { CollectionView, Descriptor } from '../route'
import SqliteFlow from './SqliteFlow'
export default function SqliteEdit({ collection, descriptor, me, onChanged }: { collection: CollectionView; descriptor: Descriptor; me: Id|null; onChanged: ()=>void }) {
  return <SqliteFlow key={collection.collection} editing={collection} descriptor={descriptor} me={me} onChanged={onChanged} go={()=>{}}/>
}
