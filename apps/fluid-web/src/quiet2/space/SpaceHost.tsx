/* THE 3D BRAIN IN A QUIET CHAT FRAME.
 *
 * The existing graph, drawn by the existing renderer (surfaces/space/), bound
 * to the session this viewer holds the id of. Nothing of the drawing, the
 * camera, the options or the reads is reimplemented here: this is a HOST --
 * a sized, container-scoped box, a visibility report, and the two things the
 * page owns (where a chosen thing is read, and what its card carries when it
 * is dragged into a composer).
 *
 * IT IS DRAWN ANEW WHENEVER THE VIEWER MOVES, and that is the point of the
 * session: the renderer is remounted, the session is not, so the eye, the
 * selection, the filters, the time and the settled read are exactly what they
 * were (addendum §1, §2). The reader of the graph's data is mounted once per
 * session elsewhere (SpaceReaders.tsx) and stays mounted while this comes and
 * goes, so moving, maximising or parking never costs a read.
 *
 * AGAINST THE AGREED CONTRACT (addendum §1, §5): the `session` prop of
 * `SpaceSurface`, and the session factory and reader themselves, are Part A's.
 * Where A's module is not wired into a build (provider.ts) this says so
 * plainly rather than drawing a graph of its own. */
import { useEffect, useRef, useState } from 'react'
import { useContext } from 'react'
import SpaceSurface from '../../surfaces/space/SpaceSurface'
import { SpaceHostContext } from './host'
import { graphVisible } from './placement'
import { NO_SESSIONS, spaceSessions } from './provider'
import { sessionById } from './registry'
import './space-host.css'

/** Whether the browser is showing this page at all. */
function useDocumentVisible(): boolean {
  const [on, setOn] = useState(() => typeof document === 'undefined' || document.visibilityState !== 'hidden')
  useEffect(() => {
    const look = () => setOn(document.visibilityState !== 'hidden')
    document.addEventListener('visibilitychange', look)
    look()
    return () => document.removeEventListener('visibilitychange', look)
  }, [])
  return on
}

export default function SpaceHost({ sessionId, placement }: { sessionId: string; placement: 'max' | 'column' }) {
  const api = useContext(SpaceHostContext)
  const session = sessionById(sessionId)
  const documentVisible = useDocumentVisible()
  /* a graph in a column behind a maximised viewer is inert; a maximised graph
     is never behind anything */
  const inertHost = placement === 'column' && !!api?.inertHost
  const visible = graphVisible({ drawn: true, inertHost, documentVisible })
  const told = useRef<boolean | null>(null)
  useEffect(() => {
    if (!session) return
    if (told.current !== visible) { told.current = visible; session.setVisible(visible) }
    /* UNMOUNTED IS NOT VISIBLE, whether this is a move, a park or the page
       going: the session is told before the canvas goes, so it checkpoints
       and pauses instead of animating into nothing. It is never disposed
       from here (addendum §1, "Disposal"). */
    return () => { told.current = false; session.setVisible(false) }
  }, [session, visible])

  if (!spaceSessions()) return <p className="q2v-wait" role="status">{NO_SESSIONS}</p>
  if (!session) return <p className="q2v-wait" role="status">This 3D Brain view was closed. Open a new one from the Brain menu.</p>
  return (
    <div className={`q2sp q2sp-${placement}`} data-space-session={sessionId}>
      <SpaceSurface
        session={session}
        onOpen={(node) => api?.onOpen(node)}
        onDragChosen={api ? (node, e) => api.onDragChosen(node, e) : undefined}
      />
    </div>
  )
}
