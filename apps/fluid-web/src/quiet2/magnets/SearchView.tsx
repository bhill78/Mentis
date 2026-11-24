/** H4: the search overlay -- the results list, the opened result, and the
 *  results header that says exactly what was searched (§5-H4).
 *
 *  Results replace the reading body in H1's `view` slot; they are never stacked
 *  under another view. Inspecting a result keeps the query, the filter, the list
 *  position and the disclosure state, and the result is read inside the card:
 *  the overlay has two states -- the list, and the one opened result -- which is
 *  what the frame's Escape ordering already assumes (`searchTarget` is cleared
 *  before the overlay is).
 *
 *  This view never writes `returnRoute`: a search begun while in the Conversation
 *  must not overwrite the route H2 saved there (§5-H4-7). Its own return is
 *  `returnFromSearch`, which closes the overlay through H1's `closeOverlay` --
 *  that restores the tab the search was begun from, because opening the overlay
 *  never changed `tab` -- and keeps a copy of what was open so that resuming the
 *  retained query comes back to the same result.
 *
 *  Behaviour is the approved design's (`hybrid.js` `index`/`results`/`backSearch`
 *  and the search box handlers), with the plan's additions: the `Batches` filter
 *  entry, and the derived scope header of §5-H4-9.
 */
import { useEffect, useId, useMemo, useRef, useSyncExternalStore } from 'react'
import type { ReactNode } from 'react'
import { MAGNET_SEARCH_TYPES } from './contract'
import type { MagnetResource, MagnetSearchTarget, MagnetSearchType, SearchEntry } from './contract'
import { closeOverlay, openOverlay, placeAt, remember } from './places'
import { createSearchIndex, filterEntries, scopeSentences, targetEntry } from './search'
import type { MagnetSearchSource, SearchClock, SearchIndex } from './search'
import './search.css'

/** How much of an entry's indexed text a result row shows (`hybrid.js:70`). */
const PREVIEW = 130

/** What the reader had open when they left the search, kept by H4 for its own
 *  resume (§5-H4-6).
 *
 *  It is deliberately not left in the snapshot. Leaving the overlay goes through
 *  H1's shared `closeOverlay`, which clears `searchTarget`, and the frame's
 *  Escape ordering depends on a target never outliving its overlay
 *  (`Magnet.tsx:164` clears the target before it closes anything). So H4 keeps a
 *  **copy** of the target against the resource -- never a live reference to
 *  state (§5-H4-7) -- and `resumeSearch` puts it back. Typing and `×` forget it,
 *  exactly as they reset the target itself. */
const resumable = new WeakMap<MagnetResource, MagnetSearchTarget>()
const keepForResume = (resource: MagnetResource, target: MagnetSearchTarget | null) => {
  if (target) resumable.set(resource, { ...target })
  else resumable.delete(resource)
}

const sameTarget = (a: MagnetSearchTarget, b: MagnetSearchTarget) =>
  a.kind === b.kind && a.item === b.item && a.lens === b.lens && a.message === b.message

/** What the opened target is read from (review B1).
 *
 *  A clicked entry is remembered with the target it opened, and counts only for
 *  that same target: after an intervening search the remembered click is another
 *  result's, and after this view is mounted again there is nothing remembered at
 *  all. Everything else is resolved from the index by identity, and an identity
 *  the index cannot answer gives `null` -- the view then says so rather than
 *  reading out another result's text under this target. */
export function resultFor(
  remembered: { target: MagnetSearchTarget; entry: SearchEntry } | null,
  target: MagnetSearchTarget,
  entries: readonly SearchEntry[],
): SearchEntry | null {
  if (remembered && sameTarget(remembered.target, target)) return remembered.entry
  return targetEntry(entries, target)
}

// ------------------------------------------------------- the search box

/** Typing: the overlay opens, and the target, the inspection and the list
 *  position reset. The query itself is kept, so it can be resumed. */
export function typeSearch(resource: MagnetResource, query: string) {
  remember(resource)
  keepForResume(resource, null)
  const s = resource.snapshot()
  resource.update({
    query, overlay: 'search', searchTarget: null, searchListScroll: 0,
    places: { ...s.places, search: { ...placeAt(s, 'search'), scroll: 0, inspected: null, inspectScroll: 0, inspectOrigin: null, provenance: false } },
  })
}

/** Resume by the retained query: after returning to a tab the query stays in
 *  the box, and clicking it or pressing Enter re-enters the search with the
 *  previous query, filter and target (§5-H4-6). The target is the one the
 *  Return kept, written back as a copy; with nothing kept, the search resumes on
 *  its list and whatever target the snapshot already carries is left alone. */
export function resumeSearch(resource: MagnetResource) {
  const s = resource.snapshot()
  if (!s.query || s.overlay === 'search') return
  remember(resource)
  const again = resumable.get(resource)
  resource.update(again ? { overlay: 'search', searchTarget: { ...again } } : { overlay: 'search' })
}

/** ← Return to {tab}: H4's own return. The overlay closes through H1's shared
 *  helper -- which is what puts the reader back on the tab the search was begun
 *  from -- and what was open is kept for the resume above, so returning and then
 *  resuming comes back to the result that was being read rather than to the bare
 *  list (§5-H4-6, review B2). */
export function returnFromSearch(resource: MagnetResource) {
  keepForResume(resource, resource.snapshot().searchTarget)
  closeOverlay(resource)
}

/** × clears the query, the target and the overlay. */
export function clearSearch(resource: MagnetResource) {
  keepForResume(resource, null)
  const s = resource.snapshot()
  resource.update({
    query: '', searchTarget: null, overlay: null, searchListScroll: 0,
    places: { ...s.places, search: { ...placeAt(s, 'search'), scroll: 0, inspected: null, inspectScroll: 0, inspectOrigin: null, provenance: false } },
  })
}

/** H4's search line for H1's `searchToolbar` slot. The frame renders its own
 *  when none is supplied, and that one has neither the resume nor the reset
 *  above, so this is the one the card should be given. */
export function SearchToolbar({ resource }: { resource: MagnetResource }) {
  const s = useSyncExternalStore(resource.subscribe, resource.snapshot, resource.snapshot)
  return <label className="q2-magnet-search">
    <span className="q2-sr-only">Search all Magnet information</span>
    <input type="search" value={s.query} placeholder="Search this Magnet…" autoComplete="off"
      onChange={(e) => typeSearch(resource, e.target.value)}
      onClick={() => resumeSearch(resource)}
      onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); resumeSearch(resource) } }} />
    {s.query && <button type="button" className="q2-magnet-icon" aria-label="Clear search" onClick={() => clearSearch(resource)}>×</button>}
  </label>
}

// ------------------------------------------------- navigating the results

/** The content-type filter. Changing it returns the list to the top. */
export function setSearchType(resource: MagnetResource, searchType: MagnetSearchType) {
  const s = resource.snapshot()
  resource.update({ searchType, searchTarget: null, searchListScroll: 0,
    places: { ...s.places, search: { ...placeAt(s, 'search'), scroll: 0 } } })
}

/** Open one result, keeping the list position to come back to.
 *
 *  The entry's own `open()` is the owning view's navigation -- it is what knows
 *  whether this result is a retained item to inspect, a Perspective to select or
 *  a batch to choose. The target is then derived from what `open()` actually
 *  did, so nothing about the result is invented here. A `Batches` entry selects
 *  its batch and leaves the reader on the list, because the selection is what
 *  changes what the index holds (§5-H4-8).
 *
 *  It answers the target it wrote, or `null` where opening the result was not a
 *  result to read (a batch selection, a Settings result, a source that navigated
 *  out of the overlay). The caller remembers the clicked entry against exactly
 *  that target, so a later render can tell whether what it remembers is what the
 *  snapshot is now asking for. */
export function openResult(resource: MagnetResource, entry: SearchEntry): MagnetSearchTarget | null {
  remember(resource)
  const before = resource.snapshot()
  const here = placeAt(before, 'search')
  if (entry.kind === 'Batches') {
    resource.update({ searchListScroll: here.scroll })
    try { entry.open() } catch { /* The source reports its own failure; the list stays. */ }
    return null
  }
  resource.update({
    searchListScroll: here.scroll,
    places: { ...before.places, search: { ...here, scroll: 0, inspected: null, inspectScroll: 0, inspectOrigin: null, provenance: false } },
  })
  try { entry.open() } catch { /* The source reports its own failure; the list stays. */ }
  const after = resource.snapshot()
  if (entry.kind === 'Settings') {
    if (after.overlay === 'search') openOverlay(resource, 'settings')
    return null
  }
  // If the source navigated out of the overlay, that is where it wanted to go.
  if (after.overlay !== 'search') return null
  const inspected = placeAt(after, 'search').inspected
  const target: MagnetSearchTarget = {
    kind: entry.kind,
    ...(inspected ? { item: inspected } : {}),
    ...(entry.kind === 'Perspectives' && after.lens ? { lens: after.lens } : {}),
  }
  resource.update({ searchTarget: target })
  return target
}

/** ← Back to results: the list, its filter and its position, exactly as left. */
export function backToResults(resource: MagnetResource) {
  const s = resource.snapshot()
  resource.update({
    searchTarget: null,
    places: { ...s.places, search: { ...placeAt(s, 'search'), inspected: null, inspectScroll: 0, inspectOrigin: null, provenance: false, scroll: s.searchListScroll } },
  })
}

// ------------------------------------------------------------- the view

export interface SearchViewProps {
  resource: MagnetResource
  /** §4's six sources. Tests inject fakes; nothing substitutes a real source. */
  sources?: readonly MagnetSearchSource[]
  /** An index already driven by its caller (tests, or a shared one). */
  index?: SearchIndex
  clock?: SearchClock
  /** The owning view for an opened result. `Host.tsx` renders this view with the
   *  resource alone, so without one the overlay reads the result from the index
   *  it already holds, rather than rendering a view it was not given. */
  detail?(target: MagnetSearchTarget, entry: SearchEntry | null): ReactNode
}

export default function SearchView({ resource, sources, index, clock, detail }: SearchViewProps) {
  const s = useSyncExternalStore(resource.subscribe, resource.snapshot, resource.snapshot)
  const own = useMemo(() => index ?? createSearchIndex({ resource, sources, clock }), [index, resource, sources, clock])
  const state = useSyncExternalStore(own.subscribe, own.snapshot, own.snapshot)
  const opened = useRef<{ target: MagnetSearchTarget; entry: SearchEntry } | null>(null)
  const typeId = useId()
  // Mounting this view *is* the overlay opening: the frame renders the place it
  // is showing, so the query-independent sources complete once per opening.
  useEffect(() => { own.opened(resource.snapshot().query) }, [own, resource])
  useEffect(() => { own.setQuery(s.query ?? '') }, [own, s.query])
  useEffect(() => () => { if (!index) own.dispose() }, [own, index])

  const query = s.query ?? ''
  const type = s.searchType ?? 'All'
  const matches = useMemo(() => filterEntries(state.entries, query, type), [state.entries, query, type])
  const sentences = useMemo(() => scopeSentences(state.reports), [state.reports])
  const returnToTab = <button type="button" className="q2-magnet-link q2-magnet-close-search" onClick={() => returnFromSearch(resource)}>← Return to {s.tab}</button>
  const asked = <p className="q2-magnet-muted q2-magnet-search-asked">Search: {query.trim() || 'all information'} · {type}</p>

  if (s.searchTarget) {
    // Which entry this target denotes (review B1): the remembered click only
    // when it is this same target's, and otherwise the index resolved by
    // identity -- never whatever was clicked most recently.
    const shown = resultFor(opened.current, s.searchTarget, state.entries)
    // The owning view when the host has one for this target, and the index's own
    // reading when it has not: `detail` declines by returning nothing, so a kind
    // whose owner has not landed is still read honestly rather than not at all.
    const given = detail?.(s.searchTarget, shown) ?? null
    return <section className="q2-magnet-results" aria-label="Search results">
      <div className="q2-magnet-section-title">
        <button type="button" className="q2-magnet-link q2-magnet-back-search" onClick={() => backToResults(resource)}>← Back to results</button>
        {returnToTab}
      </div>
      {asked}
      {given
        ?? <div className="q2-magnet-result-read">
            <h3 id="result-title" tabIndex={-1}>{shown ? shown.title : `${s.searchTarget.kind} result`}</h3>
            <p className="q2-magnet-attribution">{s.searchTarget.kind}{s.searchTarget.item ? ` · ${s.searchTarget.item}` : ''}</p>
            {shown?.text
              ? <p className="q2-magnet-result-text">{shown.text}</p>
              : <p className="q2-magnet-muted">The index does not hold this result under an identity it can be read back by, so none of its text is shown here rather than another result’s.</p>}
            <p className="q2-magnet-muted">Shown from the search index. Return to the results, or return to {s.tab} to read it in its own view.</p>
          </div>}
    </section>
  }

  return <section className="q2-magnet-results" aria-label="Search results">
    <div className="q2-magnet-section-title">
      <h3 id="results-title" tabIndex={-1}>Search this Magnet</h3>
      {returnToTab}
    </div>
    <div className="q2-magnet-result-toolbar">
      <label htmlFor={typeId}>Content type</label>
      <select id={typeId} value={type} onChange={(e) => setSearchType(resource, e.target.value as MagnetSearchType)}>
        {MAGNET_SEARCH_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
      </select>
      <span className="q2-magnet-muted q2-magnet-result-count" role="status">{matches.length} {matches.length === 1 ? 'result' : 'results'}</span>
    </div>
    <div className="q2-magnet-search-scope">
      <h4>What was searched</h4>
      {sentences.map((line, n) => <p key={`${n}:${line}`} className="q2-magnet-muted">{line}</p>)}
    </div>
    {matches.length
      ? <ul className="q2-magnet-items q2-magnet-result-list">
          {matches.map((e) => <li key={e.key}>
            <span className="q2-magnet-attribution">{e.kind}</span>
            <button type="button" className="q2-magnet-item q2-magnet-result" onClick={() => {
              opened.current = null
              const target = openResult(resource, e)
              if (target) opened.current = { target, entry: e }
            }}>{e.title}</button>
            {e.text && <p className="q2-magnet-preview">{e.text.slice(0, PREVIEW)}</p>}
          </li>)}
        </ul>
      : <div className="q2-magnet-empty">
          <p>No matches. Try another phrase or content type.</p>
          {query.trim() && <button type="button" className="q2-magnet-link" onClick={() => typeSearch(resource, '')}>Clear the phrase and show everything in the index</button>}
          {type !== 'All' && <button type="button" className="q2-magnet-link" onClick={() => setSearchType(resource, 'All')}>Search every content type</button>}
        </div>}
  </section>
}
