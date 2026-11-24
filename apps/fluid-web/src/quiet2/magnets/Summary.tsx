/** The Summary view: the first tab and the default.
 *
 *  **Retained collection only** (plan §5-H3-1, B5). Every line here is derived
 *  from `resource.snapshot()` -- the immutable batch `state.ts` has already read
 *  and `collectionRows` has already verified -- and from the saved definition.
 *  This view issues no request of its own, and in particular never calls
 *  `GET /fluid/api/magnets/<id>/read` in any mode: that route reads the Magnet's
 *  sources *live*, which this surface exists not to do (`state.ts:1`).
 *
 *  **Nothing here is synthesis.** Every sentence is a fact about the collection
 *  -- counts, configured sources, capture bounds, times, states -- and no
 *  sentence characterises, summarises or interprets what the material says.
 *  Evidence-grounded answering stays refused server-side and the affordance is
 *  rendered disabled, carrying the refusal's own reason. */
import { useSyncExternalStore } from 'react'
import type { MagnetResource, MagnetSnapshot, SavedMagnet, SearchEntry, SearchSource } from './contract'
import type { MagnetSource } from '../../fluid/surface/magnet/types'
import Inspection, { retainedFiles, sourceLabel } from './Inspection'
import type { RouteResult } from '../../fluid/surface/magnet/route'
import { goTab, inspect, place } from './places'
import { resultTitle } from './EvidenceViews'
import { PERSPECTIVE_BLOCK_REASON } from './perspectives'
import './summary.css'

/** The reason comes from the gate itself, not from a sentence written here:
 *  `PERSPECTIVE_BLOCK_REASON` is the client's statement of the server's
 *  `grounded_answers: false` refusal (`perspectives.py` GROUNDED_ANSWERS_ENABLED,
 *  DISCLOSURE). See the Turn's discrepancy note: the server's own
 *  `grounded_answers`/`disclosure` fields are not kept in H5's `InquirySnapshot`,
 *  and Summary may not make a request to read them. */
export const GROUNDED_UNAVAILABLE = `Unavailable · ${PERSPECTIVE_BLOCK_REASON}`

const when = (at?: number | null) => typeof at === 'number' && Number.isFinite(at) ? new Date(at * 1000).toLocaleString() : null

/** How many retained items in the batch shown were captured from each key. */
export function capturedCounts(s: MagnetSnapshot): Map<string, number> {
  const counts = new Map<string, number>()
  for (const r of s.results) {
    const key = (r as RouteResult & { capturedSourceKey?: string }).capturedSourceKey
    if (typeof key === 'string' && key) counts.set(key, (counts.get(key) ?? 0) + 1)
  }
  return counts
}

/** A configured source's captured key, in `collectionRows`'s own vocabulary.
 *  Only Conversation and held-file sources can be captured by this candidate
 *  (`read.ts unsupportedMagnet`), so any other kind has no key and no items. */
export function configuredKey(source: MagnetSource): string | null {
  if (source.kind === 'conversation') return `conversation:${source.conversation}`
  if (source.kind === 'file') return `file:${source.collection}:${source.path ?? ''}`
  return null
}

/** The factual lines, in the order §5-H3-1 names them. Returned as sentences so
 *  that `summarySource` searches exactly what the reader can see. */
export function summaryFacts(saved: SavedMagnet, s: MagnetSnapshot): string[] {
  const posts = s.results.filter((r) => r.kind === 'post').length
  const files = retainedFiles(s.results).length
  const sources = saved.config?.sources ?? []
  const selection = saved.config?.selection
  const counts = capturedCounts(s)
  const read = s.activation !== undefined
  const lines: string[] = []
  if (!read) lines.push('This collection has not been read yet. Opening never collects and never reads a live source.')
  else if (!s.activation) lines.push('No retained collection yet. Press Collect now; opening never collects automatically.')
  else lines.push(`${posts} retained posts and ${files} retained files in the batch shown.`)
  lines.push(`${sources.length} configured ${sources.length === 1 ? 'source' : 'sources'}: ${sources.map((source) => {
    const key = configuredKey(source)
    if (!key) return `a ${source.kind} source, which this candidate does not capture`
    const got = counts.get(key)
    return `${sourceLabel(key)} (${got ? `${got} retained ${got === 1 ? 'item' : 'items'}` : 'no retained item in this batch'})`
  }).join('; ') || 'none readable'}.`)
  for (const key of counts.keys()) {
    if (!sources.some((source) => configuredKey(source) === key))
      lines.push(`This batch also holds ${counts.get(key)} items captured from ${sourceLabel(key)}, which the current configuration no longer names. The captured copy is unchanged.`)
  }
  const collected = when(s.activation?.at)
  if (collected) lines.push(`Collected ${collected} · recorded batch state ${s.activation?.state ?? 'unstated'}.`)
  if (s.status) lines.push(s.status === 'ok' ? 'Every captured source reported its whole selected scope.'
    : `This retained batch is ${s.status}${s.reason ? `. Stated by its captured sources: ${s.reason}` : '. No reason was stated.'}`)
  if (s.error) lines.push(s.error)
  lines.push(`Showing ${s.batchSelection ? 'the selected historical' : 'the latest'} batch.`)
  lines.push(`Selected Conversation types: ${(selection?.informationTypes?.length ? selection.informationTypes : ['post', 'file', 'image']).join(', ')}.`)
  if (selection?.dates) lines.push(`Selected dates: ${selection.dates.after || 'any start'} to ${selection.dates.before || 'any end'}.`)
  if (saved.config && ['criteria', 'phrases', 'topics', 'filters'].some((k) => !!saved.config?.selection[k as keyof typeof saved.config.selection]))
    lines.push('Criteria, phrases, topics and filters are kept with the Magnet; this source does not apply them.')
  lines.push('Change tracking unavailable.')
  lines.push(s.previousOpen ? 'Activity is compared with this tab’s last-open time only; there is no shared read state.' : 'No last-open baseline in this tab yet.')
  return lines
}

/** The Summary's own facts. Already complete: they are derived from the batch in
 *  hand, so this source owes no `complete()` (§4). */
export function summarySource(resource: MagnetResource): SearchSource {
  return {
    entries(): SearchEntry[] {
      const s = resource.snapshot()
      return [{ key: 'summary', kind: 'Summary', title: 'Collection overview',
        text: summaryFacts(resource.saved, s).join(' '), open: () => goTab(resource, 'Summary') }]
    },
  }
}

export default function Summary({ resource, onPost }: { resource: MagnetResource; onPost(result: RouteResult): void }) {
  const s = useSyncExternalStore(resource.subscribe, resource.snapshot, resource.snapshot)
  const here = place(s)
  const posts = s.results.filter((r) => r.kind === 'post')
  const files = retainedFiles(s.results)
  const read = s.activation !== undefined
  const items = [...posts, ...files]
  const batch = s.activation?.artifact.ref
  // Real retained items, offered as the Summary's supports.
  const supports = items.slice(0, 6)
  return <section className="q2-magnet-summary" id="q2-magnet-summary">
    <div className="q2-magnet-section-title">
      <h3 id="summary-title" tabIndex={-1}>Summary</h3>
      <span className="q2-magnet-count">{read ? `${posts.length} posts · ${files.length} files` : 'not read yet'}</span>
    </div>
    {s.loading && <p className="q2-magnet-muted" role="status">Reading this collection…</p>}
    {read && !s.activation
      ? <div className="q2-magnet-collection-empty">
          <p>No collected information yet. Conversation is still available.</p>
          <p className="q2-magnet-muted">Choose sources in settings, or press Collect now. Opening never collects.</p>
        </div>
      : <>
        <span className="q2-magnet-eyebrow">Collection overview · facts only</span>
        <div className="q2-magnet-facts">{summaryFacts(resource.saved, s).map((line, i) => <p key={i}>{line}</p>)}</div>
        {(items.length > 0 || batch) && <div className="q2-magnet-support">
          {batch && <button type="button" className="q2-magnet-link" id={`support-${batch}`} aria-expanded={here.inspected === batch}
            onClick={() => inspect(resource, batch, `support-${batch}`)}>Inspect collection evidence ↗</button>}
          {supports.map((r) => <button type="button" key={`${r.kind}:${r.id}`} className="q2-magnet-link" id={`support-${r.id}`} aria-expanded={here.inspected === r.id}
            onClick={() => inspect(resource, r.id, `support-${r.id}`)}>Inspect {resultTitle(r)} ↗</button>)}
          {items.length > supports.length && <span className="q2-magnet-muted">{items.length - supports.length} more retained items are listed under All.</span>}
        </div>}
      </>}
    {/* Inline, inside the Summary section: never a separate screen. */}
    {here.inspected && <Inspection resource={resource} refId={here.inspected} source={onPost} />}
    <p className="q2-magnet-dependency">Sample records · not agent analysis or synthesis.</p>
    <div className="q2-magnet-grounding">
      <button type="button" className="q2-magnet-secondary" disabled aria-describedby="grounded-status">Synthesize from evidence</button>
      <span id="grounded-status" className="q2-magnet-muted">{GROUNDED_UNAVAILABLE}</span>
    </div>
  </section>
}
