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
import { inspect, place, placeKeyOf, writePlace } from './places'
import { SUPPORTING_WHY } from './perspectives'
import CollectionConfiguration from './CollectionConfiguration'
import { magnetName } from './configuration'
import './summary.css'
import './perspectives.css'
import './configuration.css'

const words = (v: unknown) => typeof v === 'string' ? v : ''
const object = (v: unknown): Record<string, unknown> => v && typeof v === 'object' ? v as Record<string, unknown> : {}
const isHeldSource = (r: RouteResult) => (r as RouteResult & { via?: string }).via === 'held-source'
/** A moment the way a clean row says it: "today, 3:12 PM" or "Nov 18" --
 *  never the raw recorded number. */
function rowWhen(at?: number | null): string | null {
  if (typeof at !== 'number' || !Number.isFinite(at)) return null
  const d = new Date(at * 1000), now = new Date()
  return d.toDateString() === now.toDateString()
    ? `today, ${d.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })}`
    : d.toLocaleDateString([], { month: 'short', day: 'numeric' })
}
/** THE CLEAN ROW'S BYLINE (approved mockup round 3, 04-browse.png): who or
 *  what it was captured from, and when -- never a raw Conversation id, source
 *  key or recorded digest, which `evidenceOrigin` (Inspection.tsx) carries for
 *  the inspection's own provenance disclosure, not for a list row. */
export function rowByline(r: RouteResult): string {
  const when = rowWhen(r.at)
  if (isHeldSource(r)) return ['Held file', when].filter(Boolean).join(' · ')
  if (r.kind === 'post') return [r.author, when].filter(Boolean).join(' · ') || 'Collected post'
  return [r.post ? 'From the collected post' : 'Collected file', when].filter(Boolean).join(' · ')
}

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
      <p className="q2-magnet-supporting-head"><strong>{resultTitle(r)}</strong><small className="q2-magnet-muted"> · {rowByline(r)}</small></p>
      {resultPreview(r) && <p className="q2-magnet-quote">“{resultPreview(r)}”</p>}
      <button type="button" className="q2-magnet-link" onClick={() => onOpen(r.id)}>Open this item</button>
    </li>)}</ul>
      : <p className="q2-magnet-muted">{s.activation ? 'Nothing is collected here to explore this question against yet.'
        : 'This Magnet has collected nothing yet. Choose sources in Settings, then collect.'}</p>}
    <div className="q2-magnet-why">
      <h5>Why these?</h5>
      <p className="q2-magnet-muted">{SUPPORTING_WHY}</p>
    </div>
  </section>
}

/** Fails closed: with no `canWrite` supplied, the embedded Sources panel
 *  offers no save a caller did not actually authorise. */
const NO_WRITE = () => false

export interface EvidenceViewsProps {
  resource: MagnetResource
  lens: 'All' | 'Posts' | 'Files'
  onPost(result: RouteResult): void
  /** The host's workspace file opening. Reachable in the seam, not rendered as a
   *  control: the approved card inspects a retained file in place. */
  onFile(result: RouteResult): void
  /** Whether the saved location named may actually be written to -- the same
   *  `writes.arrangement` Host gives Settings' own copy of this panel
   *  (`capabilities.ts`). Omitted, it fails closed (`NO_WRITE`): the server's
   *  own save route still authorises independently, so this is the client
   *  affordance only, never the only gate. */
  canWrite?(key: string): boolean
}

export default function EvidenceViews({ resource, lens, onPost, canWrite }: EvidenceViewsProps) {
  const s = useSyncExternalStore(resource.subscribe, resource.snapshot, resource.snapshot)
  const here = place(s)
  const posts = s.results.filter((r) => r.kind === 'post')
  const files = retainedFiles(s.results)
  const partial = !!s.next || (s.status != null && s.status !== 'ok')
  const read = s.activation !== undefined
  const items = lens === 'Posts' ? posts : lens === 'Files' ? files : [...posts, ...files]
  /** One row, with its inspection inline directly beneath it. Clean (approved
   *  mockup round 3, 04-browse.png): a title a reader recognises, its captured
   *  excerpt, and who or when it was captured, never a raw id, a recorded
   *  digest or a type glyph. */
  const rows = () => <ul className="q2-magnet-items">
    {items.map((r) => <li key={`${r.kind}:${r.id}:${r.version ?? ''}`}>
      <button type="button" id={`item-${r.id}`} className="q2-magnet-evidence-row" aria-expanded={here.inspected === r.id}
        onClick={() => inspect(resource, r.id, `item-${r.id}`)}>
        <span className="q2-magnet-row-text">
          <strong>{resultTitle(r)}</strong>
          {resultPreview(r) && <p className="q2-magnet-preview">{resultPreview(r)}</p>}
          <small className="q2-magnet-muted">{rowByline(r)}</small>
        </span>
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
  // SOURCE MANAGEMENT, INTEGRATED INTO COLLECTION (approved mockup round 3,
  // 03-sources.png / 04-browse.png): the unified `All` place toggles between
  // the collected items above and its own Sources, reusing B's panel exactly
  // as Settings does -- the staged draft lives in `panelDrafts`, keyed by
  // Brain and Magnet rather than by which copy of the panel is on screen, so
  // editing here and editing in Settings is the same unsaved edit. This needs
  // no seam into Host or the frame: `resource` already carries what it saves
  // through (`saved.config`, `saved.id`).
  //
  // The disclosure is the place's own (`contract.ts` `MagnetPlace.sources`),
  // not local state: the shell's own "Sources" entry (`Magnet.tsx`,
  // `showSourcesInline`) writes the same flag, so the two are one entry, not
  // a second implementation of source management.
  const config = resource.saved.config
  const showSources = here.sources
  const integrated = lens === 'All' && !!config
  const mayWriteArrangement = canWrite ?? NO_WRITE
  return <section>
    {integrated && <p className="q2-magnet-collection-toggle">
      {showSources
        ? <button type="button" className="q2-magnet-link" onClick={() => writePlace(resource, placeKeyOf(s), { sources: false })}>Collected items{read ? ` · ${items.length}` : ''} →</button>
        : <button type="button" className="q2-magnet-link" onClick={() => writePlace(resource, placeKeyOf(s), { sources: true })}>Sources{config!.sources.length ? ` · ${config!.sources.length}` : ''}</button>}
    </p>}
    {integrated && showSources ? <CollectionConfiguration magnet={resource.saved.id} config={config!} brainKey={resource.brainKey} inCollection
        canWrite={mayWriteArrangement} onSaved={(next) => {
          resource.saved.config = next; resource.saved.name = magnetName(next, resource.saved.name); resource.saved.reason = undefined
          resource.update({ title: resource.saved.name }); void resource.read()
        }} /> : <>
      <p id="view-title" className="q2-magnet-view-meta" tabIndex={-1}>
        {read ? `${items.length} collected ${items.length === 1 ? 'item' : 'items'}` : 'Not read yet'}
        {partial && read && !!s.activation && ' · this collection is partial.'}
      </p>
      {elsewhere && <Inspection resource={resource} refId={here.inspected!} source={onPost} />}
      {items.length ? rows() : empty(lens === 'Posts' ? 'posts' : lens === 'Files' ? 'files' : 'items')}
    </>}
  </section>
}
