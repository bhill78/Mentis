/* WHERE THE GRAPH'S DATA IS READ FROM, for as long as a graph is open.
 *
 * ONE READER PER LIVE SESSION, keyed only by the session's id, mounted in a
 * stable owner that is neither a column nor the maximised layer -- so it is
 * not unmounted when the canvas moves between columns, is maximised, is
 * parked, or is not drawn at all (addendum §1, "Reader strategy is CHOSEN").
 * It draws nothing.
 *
 * The reader itself is Part A's (`SpaceSessionReader`), using the EXISTING
 * `useApi` with its existing 5000ms advance spacing, the existing HTTP client
 * and the existing `/api/space` paths. Quiet Chat neither reads the graph nor
 * supplies it a read: it only says, by keeping this mounted, how long the
 * reading lasts. */
import { useSyncExternalStore } from 'react'
import { spaceSessions } from './provider'
import { liveSessions, sessionsVersion, subscribeSessions } from './registry'

export default function SpaceReaders() {
  useSyncExternalStore(subscribeSessions, sessionsVersion, sessionsVersion)
  const mod = spaceSessions()
  if (!mod) return null
  const Reader = mod.SpaceSessionReader
  return (
    <div className="q2-space-readers" hidden aria-hidden="true">
      {liveSessions().map((s) => <Reader key={s.id} session={s} />)}
    </div>
  )
}
