/** The Summary view: the first tab and the default.
 *
 *  H1 lands it so the approved default tab shows something truthful: the facts
 *  the extracted card used to keep in its `scope` block, the retained counts it
 *  actually read, and the grounded-synthesis affordance with the server's own
 *  reason for refusing it. H3 replaces the contents; the slot does not change.
 *
 *  Nothing here is synthesis. Evidence-grounded answering stays refused
 *  server-side and unavailable here, and this view never implies that an agent
 *  read the collected material. */
import { useSyncExternalStore } from 'react'
import type { MagnetResource } from './contract'
import Inspection, { retainedFiles } from './Inspection'
import type { RouteResult } from '../../fluid/surface/magnet/route'
import { closeInspect, place } from './places'
import { scopeFacts } from './EvidenceViews'

export const GROUNDED_UNAVAILABLE = 'Unavailable · the server refuses evidence-grounded synthesis because source-restricted agent access is not verified.'

export default function Summary({ resource, onPost }: { resource: MagnetResource; onPost(result: RouteResult): void }) {
  const s = useSyncExternalStore(resource.subscribe, resource.snapshot, resource.snapshot)
  const here = place(s)
  if (here.inspected) return <Inspection resource={resource} refId={here.inspected} back={() => closeInspect(resource)} source={onPost} />
  const posts = s.results.filter((r) => r.kind === 'post')
  const files = retainedFiles(s.results)
  const read = s.activation !== undefined
  return <section className="q2-magnet-summary">
    <div className="q2-magnet-section-title">
      <h3 id="summary-title" tabIndex={-1}>Summary</h3>
      <span className="q2-magnet-count">{read ? `${posts.length} posts · ${files.length} files` : 'not read yet'}</span>
    </div>
    {s.loading && <p className="q2-magnet-muted" role="status">Reading this collection…</p>}
    {!read && !s.loading && <p className="q2-magnet-muted">This collection has not been read yet. Opening never collects and never reads a live source.</p>}
    {read && !s.activation && <p className="q2-magnet-muted">No retained collection yet. Press Collect now; opening never collects automatically.</p>}
    {s.activation && <p className="q2-magnet-muted">Retained collection · <button type="button" className="q2-magnet-link" onClick={() => resource.update({ places: { ...s.places, [s.overlay ?? s.tab]: { ...here, inspected: s.activation!.artifact.ref, inspectScroll: 0, inspectOrigin: 'summary-title' } } })}>Inspect collection evidence</button></p>}
    {(s.error || (s.status && s.status !== 'ok')) && <p className="q2-magnet-read-status" role="status">{s.error || `${s.status}: ${s.reason || 'Only what could be read is shown.'}`}</p>}
    {scopeFacts(resource.saved, s)}
    <p className="q2-magnet-muted">Collected records only · not agent analysis or synthesis.</p>
    <div className="q2-magnet-grounding">
      <button type="button" className="q2-magnet-secondary" disabled aria-describedby="grounded-status">Synthesize from evidence</button>
      <span id="grounded-status" className="q2-magnet-muted">{GROUNDED_UNAVAILABLE}</span>
    </div>
  </section>
}
