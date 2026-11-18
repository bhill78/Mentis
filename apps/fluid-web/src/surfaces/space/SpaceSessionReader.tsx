import { useEffect, useSyncExternalStore } from 'react'
import { useApi } from '../../api'
import type { SpaceRead } from './layout'
import { materialKey, spacePath, spaceSessionInside, type SpaceMaterialKey, type SpaceSession } from './session'

/* ------------------------------------------------------------------------ *
 * THE ONE READER OF A GRAPH, MOUNTED WHERE THE CANVAS IS NOT.
 *
 * `/api/space` is one read of the whole Brain. While the canvas itself was
 * the only thing reading it, moving the canvas between columns -- which
 * remounts it -- read the whole Brain again, and a maximise-and-restore read
 * it twice. So the read is mounted once, by the host, somewhere that does not
 * move, and it publishes into the session the canvas draws from.
 *
 * IT IS THE SAME READER IT ALWAYS WAS: `useApi` at the same path with the
 * same 5000ms spacing, the same shared HTTP client, the same coalescing and
 * the same at-most-one-read-out behaviour. Nothing here caches, polls or
 * keeps a second copy of the graph.
 *
 * ONE MOUNT PER MATERIAL KEY. Asking for acquired material is a different
 * read, and the inner reader is keyed by which, so an answer can never be
 * labelled with the key it did not come from -- which is what showing the
 * records read as though material were on would be. Placement, parking,
 * visibility and returning change neither the key nor the path, so none of
 * them reads anything.
 * ------------------------------------------------------------------------ */

export interface SpaceSessionReaderProps {
  session: SpaceSession
}

export default function SpaceSessionReader({ session }: SpaceSessionReaderProps) {
  const snapshot = useSyncExternalStore(session.subscribe, session.getSnapshot)
  if (snapshot.disposed) return null
  const key = materialKey(snapshot.view.material)
  return <KeyReader key={key} session={session} materialKey={key} />
}

function KeyReader({ session, materialKey: key }: { session: SpaceSession; materialKey: SpaceMaterialKey }) {
  const read = useApi<SpaceRead>(spacePath(key), { spacing: 5000 })
  const into = spaceSessionInside(session)

  useEffect(() => {
    /* A SETTLED ANSWER IS PUBLISHED UNDER ITS OWN KEY, and an error leaves
       whatever that key last settled on in place beside it. `data` is only
       ever this key's: this component is mounted for one path. */
    if (read.data) into.publish(key, { data: read.data, loading: read.loading, error: read.error })
    else into.publish(key, { loading: read.loading, error: read.error })
  }, [into, key, read.data, read.loading, read.error])

  useEffect(
    () => () => {
      /* Nothing is reading this key any more. What it settled on stays. */
      into.publish(key, { loading: false })
    },
    [into, key],
  )

  return null
}
