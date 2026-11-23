/** The search overlay's results view.
 *
 *  H1 lands it so the overlay is a real place with its own reading position and
 *  its own return. It says plainly that there is no index yet: nothing here
 *  claims a search it did not make. H4 replaces the contents, assembles the
 *  index from each view's `SearchSource` and owns the scope sentence. */
import { useSyncExternalStore } from 'react'
import type { MagnetResource } from './contract'
import { closeOverlay } from './places'

export default function SearchView({ resource }: { resource: MagnetResource }) {
  const s = useSyncExternalStore(resource.subscribe, resource.snapshot, resource.snapshot)
  return <section aria-label="Search results">
    <div className="q2-magnet-section-title">
      <h3 id="results-title" tabIndex={-1}>Search this Magnet</h3>
      <button type="button" className="q2-magnet-link" onClick={() => closeOverlay(resource)}>← Return to {s.tab}</button>
    </div>
    <p className="q2-magnet-muted">Search: {s.query.trim() || 'all information'} · {s.searchType}</p>
    <p className="q2-magnet-muted">No index is assembled in this build, so nothing is searched yet and no result is shown. The views keep their own reading positions while this is open.</p>
  </section>
}
