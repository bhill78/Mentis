/** The collection views -- the unified collection and its type filters
 *  (Everything, Posts, Files) -- and the record viewing they route into.
 *
 *  The reader meets these as one secondary place with filters, not as a tab per
 *  source type (owner request ent-3191baeb33d2 §1); `lens` is the filter, and
 *  `places.ts` keeps the navigation model. A future source type is another
 *  filter here, never another primary tab.
 *
 *  Each list shows **every** retained item of its kind in the batch now shown.
 *  It is not filtered by the search box: `query` is the universal search's
 *  query, the search is an overlay with its own place and its own results view,
 *  and a tab list that quietly hid rows matching nothing would make the card
 *  claim a collection smaller than the one it holds (plan §4, §5-H4-1/3). The
 *  old in-tab substring filter over the already-fetched batch is gone with it.
 *
 *  Nothing here reads a live source: the rows are `resource.snapshot().results`,
 *  the batch `state.ts` read and `collectionRows` verified. */
import { useSyncExternalStore } from 'react'
import type { RouteResult } from '../../fluid/surface/magnet/route'
import type { MagnetResource, MagnetSearchKind, SearchEntry, SearchSource } from './contract'
import Inspection, { capturedText, evidenceBounds, evidenceOrigin, retainedFiles } from './Inspection'
import { inspect, place } from './places'
import { SUPPORTING_WHY } from './perspectives'
import './summary.css'
import './perspectives.css'

const words = (v: unknown) => typeof v === 'string' ? v : ''
const object = (v: unknown): Record<string, unknown> => v && typeof v === 'object' ? v as Record<string, unknown> : {}

export function resultTitle(r: RouteResult): string {
  const v = object(r.value)
  return words(v.title) || words(v.name) || words(v.path) || (r.kind === 'post' ? `Post${r.number ? ` #${r.number}` : ''}` : `${r.kind === 'image' ? 'Image' : 'File'} from a collected post`)
}
export function resultPreview(r: RouteResult): string {
  const v = object(r.value), p = object(v.preview)
  return (capturedText(r) || words(v.text) || words(v.preview) || words(p.text)).replace(/\s+/g, ' ').slice(0, 180)
}
export const isCollectedFile = (r: RouteResult) => ['file', 'attachment', 'image'].includes(r.kind)

/** The retained items of the batch shown, posts first, as the lists order them. */
export function retainedItems(resource: MagnetResource): { posts: RouteResult[]; files: RouteResult[] } {
  const s = resource.snapshot()
  return { posts: s.results.filter((r) => r.kind === 'post'), files: retainedFiles(s.results) }
}

/** Every item of the batch now shown -- not a slice and not the first page. One
 *  `collection` read returns the whole immutable batch (`collection.py:69-87`
 *  has no cursor), so this source is already complete and owes no `complete()`
 *  (§4). */
export function evidenceSource(resource: MagnetResource): SearchSource {
  return {
    entries(): SearchEntry[] {
      const { posts, files } = retainedItems(resource)
      return [...posts, ...files].map((r) => ({
        key: `evidence:${r.kind}:${r.id}`,
        kind: (r.kind === 'post' ? 'Posts' : 'Files') as MagnetSearchKind,
        title: resultTitle(r),
        text: [evidenceOrigin(r), capturedText(r), r.id, r.version ?? '', evidenceBounds(r)].join(' '),
        open: () => inspect(resource, r.id, `item-${r.id}`),
      }))
    },
  }
}

/** SUPPORTING ITEMS, OPENED ON REQUEST (approved mockup round 3, 06-future-support).
 *
 *  Perspectives asks for this when the reader presses "Explore supporting
 *  items". It is the same collected material the lists above hold, shown
 *  against a question instead of against a filter, and it occupies the working
 *  area only while it is open.
 *
 *  It is not an answer's chosen support, and never pretends to be: nothing read
 *  these items to answer anything, which is what `SUPPORTING_WHY` says beneath
 *  them. Opening one goes through the caller's own evidence opening, so the
 *  item is read in the card's one inspection with its one way back. */
export function SupportingItems({ resource, question, onOpen }: {
  resource: MagnetResource
  /** The question these are offered against, in its own saved words. */
  question: string
  onOpen(ref: string): void
}) {
  const s = useSyncExternalStore(resource.subscribe, resource.snapshot, resource.snapshot)
  const { posts, files } = retainedItems(resource)
  const items = [...posts, ...files]
  return <section className="q2-magnet-supporting" aria-label="Supporting items">
    <h4>Supporting items</h4>
    {question && <p className="q2-magnet-muted">For “{question}”</p>}
    {items.length ? <ul className="q2-magnet-items">{items.map((r) => <li key={`${r.kind}:${r.id}`}>
      <p className="q2-magnet-supporting-head"><strong>{resultTitle(r)}</strong><small className="q2-magnet-muted"> · {evidenceOrigin(r)}</small></p>
      {resultPreview(r) && <p className="q2-magnet-quote">“{resultPreview(r)}”</p>}
      <button type="button" className="q2-magnet-link" onClick={() => onOpen(r.id)}>Open item ↗</button>
    </li>)}</ul>
      : <p className="q2-magnet-muted">{s.activation ? 'Nothing is collected here to explore this question against yet.'
        : 'This Magnet has collected nothing yet. Choose sources in Settings, then collect.'}</p>}
    <div className="q2-magnet-why">
      <h5>Why these?</h5>
      <p className="q2-magnet-muted">{SUPPORTING_WHY}</p>
    </div>
  </section>
}

export interface EvidenceViewsProps {
  resource: MagnetResource
  lens: 'All' | 'Posts' | 'Files'
  onPost(result: RouteResult): void
  /** The host's workspace file opening. Reachable in the seam, not rendered as a
   *  control: the approved card inspects a retained file in place. */
  onFile(result: RouteResult): void
}

export default function EvidenceViews({ resource, lens, onPost }: EvidenceViewsProps) {
  const s = useSyncExternalStore(resource.subscribe, resource.snapshot, resource.snapshot)
  const here = place(s)
  const posts = s.results.filter((r) => r.kind === 'post')
  const files = retainedFiles(s.results)
  const partial = !!s.next || (s.status != null && s.status !== 'ok')
  const read = s.activation !== undefined
  const items = lens === 'Posts' ? posts : lens === 'Files' ? files : [...posts, ...files]
  /** One row, with its inspection inline directly beneath it. */
  const rows = () => <ul className="q2-magnet-items">
    {items.map((r) => <li key={`${r.kind}:${r.id}:${r.version ?? ''}`}>
      <button type="button" id={`item-${r.id}`} className="q2-magnet-evidence-row" aria-expanded={here.inspected === r.id}
        onClick={() => inspect(resource, r.id, `item-${r.id}`)}>
        <span className="q2-magnet-type-icon" aria-hidden="true">{r.kind === 'post' ? '¶' : '▤'}</span>
        <span className="q2-magnet-row-text">
          <strong>{resultTitle(r)}</strong><small className="q2-magnet-muted"> · {evidenceOrigin(r)}</small>
          {resultPreview(r) && <p className="q2-magnet-preview">{resultPreview(r)}</p>}
        </span>
        <span aria-hidden="true">↗</span>
      </button>
      {here.inspected === r.id && <Inspection resource={resource} refId={r.id} source={onPost} />}
      {r.kind !== 'post' && (r.post || words(object(r.value).post)) && here.inspected !== r.id &&
        <button type="button" className="q2-magnet-link q2-magnet-at-post" onClick={() => inspect(resource, r.post ?? words(object(r.value).post), `item-${r.id}`)}>View the collected post</button>}
    </li>)}
  </ul>
  const empty = (what: string) => <p className="q2-magnet-muted">{s.loading ? 'Reading…'
    : s.error || s.reason || (!read ? 'This collection has not been read yet. Opening never collects and never reads a live source.'
      : !s.activation ? 'No collected information yet. Conversation is still available.'
        : partial ? `No ${what} collected so far. More may be available.` : `No ${what} in what this Magnet collects.`)}</p>
  /** An inspection reached from elsewhere (a search result, the host) for an
   *  item this list does not hold still has to be readable. */
  const elsewhere = here.inspected && !items.some((r) => r.id === here.inspected)
  return <section>
    <p id="view-title" className="q2-magnet-view-meta" tabIndex={-1}>
      {read ? `${items.length} collected ${items.length === 1 ? 'item' : 'items'}` : 'Not read yet'}
      {partial && read && !!s.activation && ' · this collection is partial.'}
    </p>
    {elsewhere && <Inspection resource={resource} refId={here.inspected!} source={onPost} />}
    {items.length ? rows() : empty(lens === 'Posts' ? 'posts' : lens === 'Files' ? 'files' : 'items')}
  </section>
}
