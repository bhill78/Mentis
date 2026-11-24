/** Mounted harness for the H1/H4 frame scroll seam (review adm-012e854e39e3, B3).
 *
 *  What is under test is the frame: whether a saved reading position written by
 *  the view that navigates reaches `.q2-magnet-view`, the card's one scroll
 *  container. The search results and the search line here stand in for H4's,
 *  which this branch does not contain; they navigate only through H1's own place
 *  helpers and write exactly the state H4's `typeSearch`, `setSearchType`,
 *  `openResult` and `backToResults` write, so a pass is about the frame applying
 *  those writes and never about this stand-in's own correctness.
 *
 *  The resource is held in memory with nothing behind it: no fetch, no device
 *  storage, no Brain. */
import { useSyncExternalStore } from 'react'
import { createRoot } from 'react-dom/client'
import Magnet from '../src/quiet2/magnets/Magnet'
import { MAGNET_SEARCH_TYPES } from '../src/quiet2/magnets/contract'
import type { MagnetResource, MagnetSearchKind, MagnetSearchType, MagnetSnapshot } from '../src/quiet2/magnets/contract'
import { closeOverlay, emptyPlaces, placeAt, remember } from '../src/quiet2/magnets/places'
import '../src/quiet2/magnets/host.css'

let current: MagnetSnapshot = {
  title: 'Frame scroll seam', loading: false, results: [], x: 32, y: 48, open: true, wide: false,
  tab: 'Summary', overlay: 'search', places: emptyPlaces(), query: 'match', searchType: 'All',
  searchTarget: null, searchListScroll: 0, lens: null, returnRoute: null, settingsReturn: null,
  context: null, contextSuppressed: false, activation: null,
}
const heard = new Set<() => void>()
const resource: MagnetResource = {
  id: 'seam', brainKey: 'fixture', saved: { id: 'mag-seam', name: 'Frame scroll seam' },
  snapshot: () => current, subscribe: (fn) => { heard.add(fn); return () => { heard.delete(fn) } },
  update: (change) => { current = { ...current, ...change }; for (const fn of [...heard]) fn() },
  read: async () => {}, cancel: () => {}, dispose: () => {},
}

const rows: { key: string; kind: MagnetSearchKind; title: string; text: string }[] = [
  { key: 'Summary', kind: 'Summary', title: 'Summary match', text: 'Summary captured text match. ' },
  ...Array.from({ length: 40 }, (_, i) => ({ key: `Row-${i}`, kind: 'Posts' as const, title: `Row-${i} match`, text: `Row ${i} captured text match. ` })),
]

/** H4's writes, as H4 writes them, through H1's helpers. */
const typeSearch = (query: string) => {
  remember(resource)
  const s = resource.snapshot()
  resource.update({ query, overlay: 'search', searchTarget: null, searchListScroll: 0,
    places: { ...s.places, search: { ...placeAt(s, 'search'), scroll: 0, inspected: null, inspectScroll: 0, inspectOrigin: null, provenance: false } } })
}
const setSearchType = (searchType: MagnetSearchType) => {
  const s = resource.snapshot()
  resource.update({ searchType, searchTarget: null, searchListScroll: 0,
    places: { ...s.places, search: { ...placeAt(s, 'search'), scroll: 0 } } })
}
const openResult = (row: typeof rows[number]) => {
  remember(resource)
  const s = resource.snapshot()
  const here = placeAt(s, 'search')
  resource.update({ searchListScroll: here.scroll, places: { ...s.places, search: { ...here, scroll: 0 } } })
  resource.update({ searchTarget: { kind: row.kind, item: row.key } })
}
const backToResults = () => {
  const s = resource.snapshot()
  resource.update({ searchTarget: null,
    places: { ...s.places, search: { ...placeAt(s, 'search'), scroll: s.searchListScroll } } })
}

function SearchLine() {
  const s = useSyncExternalStore(resource.subscribe, resource.snapshot)
  return <label className="q2-magnet-search">
    <span className="q2-sr-only">Search all Magnet information</span>
    <input type="search" value={s.query} placeholder="Search this Magnet…" autoComplete="off"
      onChange={(e) => typeSearch(e.target.value)} />
  </label>
}

function Results() {
  const s = useSyncExternalStore(resource.subscribe, resource.snapshot)
  const query = s.query.trim().toLowerCase()
  const matches = rows.filter((row) => (s.searchType === 'All' || row.kind === s.searchType)
    && (!query || `${row.title} ${row.text}`.toLowerCase().includes(query)))
  const back = <button type="button" className="q2-magnet-link" onClick={() => closeOverlay(resource)}>← Return to {s.tab}</button>
  if (s.searchTarget) {
    const shown = rows.find((row) => row.key === s.searchTarget!.item)
    return <section aria-label="Search results">
      <div className="q2-magnet-section-title">
        <button type="button" className="q2-magnet-link" onClick={backToResults}>← Back to results</button>
        {back}
      </div>
      <h3 id="result-title" tabIndex={-1}>{shown?.title ?? 'result'}</h3>
      <p className="q2-magnet-result-text">{(shown?.text ?? '').repeat(80)}</p>
    </section>
  }
  return <section aria-label="Search results">
    <div className="q2-magnet-section-title">
      <h3 id="results-title" tabIndex={-1}>Search this Magnet</h3>
      {back}
    </div>
    <div className="q2-magnet-result-toolbar">
      <label htmlFor="seam-type">Content type</label>
      <select id="seam-type" value={s.searchType} onChange={(e) => setSearchType(e.target.value as MagnetSearchType)}>
        {MAGNET_SEARCH_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
      </select>
    </div>
    <ul className="q2-magnet-items">
      {matches.map((row) => <li key={row.key}>
        <span className="q2-magnet-attribution">{row.kind}</span>
        <button type="button" className="q2-magnet-item" onClick={() => openResult(row)}>{row.title}</button>
        <p className="q2-magnet-preview">{row.text.repeat(3)}</p>
      </li>)}
    </ul>
  </section>
}

const body = (words: string) => <div>{Array.from({ length: 30 }, (_, i) => <p key={i}>{words} paragraph {i + 1}.</p>)}</div>

Object.assign(window, { seam: { snapshot: () => resource.snapshot() } })
createRoot(document.getElementById('root')!).render(<div className="q2 q2-arr-one">
  <div className="q2-magnet-canvas" style={{ height: '100vh', position: 'relative' }}>
    <Magnet resource={resource} onExpand={() => {}} onCollapse={() => {}} searchToolbar={<SearchLine />}
      views={{
        Summary: body('Summary'), All: body('All'), Posts: body('Posts'), Files: body('Files'),
        Perspectives: body('Perspectives'), Conversation: body('Conversation'), search: <Results />,
      }} />
  </div>
</div>)
