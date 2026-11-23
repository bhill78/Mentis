/** The evidence views (All, Posts, Files) and the inspection they route into.
 *
 *  Extracted from `Magnet.tsx` by H1 so that the frame is only a frame. H1 owns
 *  this file only until H3 replaces its contents; the shape it is plugged in by
 *  -- one component per `view` slot, reading its reading position from
 *  `places.ts` -- is the published seam and does not change. */
import { useSyncExternalStore } from 'react'
import type { RouteResult } from '../../fluid/surface/magnet/route'
import type { MagnetResource, MagnetSnapshot, SavedMagnet } from './contract'
import Inspection, { capturedText, retainedFiles } from './Inspection'
import { inspect, closeInspect, place } from './places'

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

/** The factual lines about this Magnet's configured scope. Summary renders them;
 *  they were the `scope` block inside the old card body. */
export function scopeFacts(saved: SavedMagnet, s: MagnetSnapshot) {
  const selection = saved.config?.selection
  return <div className="q2-magnet-scope">
    <p>{saved.config?.sources.length ?? 0} configured sources. Collect manually to retain one bounded batch. Showing {s.batchSelection ? 'the selected historical' : 'the latest'} batch. Selected Conversation types: {(selection?.informationTypes?.length ? selection.informationTypes : ['post', 'file', 'image']).join(', ')}.</p>
    {selection?.dates && <p>Selected dates: {selection.dates.after || 'any start'} to {selection.dates.before || 'any end'}.</p>}
    {saved.config && ['criteria', 'phrases', 'topics', 'filters'].some((k) => !!saved.config?.selection[k as keyof typeof saved.config.selection]) && <p>Criteria, phrases, topics and filters are kept with the Magnet; this source does not apply them.</p>}
    <p>Change tracking unavailable.</p>
    <p>{s.previousOpen ? 'Activity is compared with this tab’s last-open time only; there is no shared read state.' : 'No last-open baseline in this tab yet.'}</p>
  </div>
}

export interface EvidenceViewsProps {
  resource: MagnetResource
  lens: 'All' | 'Posts' | 'Files'
  onPost(result: RouteResult): void
  /** The host's workspace file opening. Reachable in the seam, not yet rendered
   *  by any control -- exactly as in the extracted card. H3 decides whether the
   *  approved design wants one. */
  onFile(result: RouteResult): void
}

export default function EvidenceViews({ resource, lens, onPost }: EvidenceViewsProps) {
  const s = useSyncExternalStore(resource.subscribe, resource.snapshot, resource.snapshot)
  const here = place(s)
  const posts = s.results.filter((r) => r.kind === 'post')
  const files = retainedFiles(s.results)
  const tally = s.summary?.summary?.posts
  const postCount = typeof tally === 'number' && Number.isFinite(tally) && tally >= 0 ? tally : null
  const partial = !!s.next || (s.status != null && s.status !== 'ok')
  const search = s.query ?? ''
  if (here.inspected) return <Inspection resource={resource} refId={here.inspected} back={() => closeInspect(resource)} source={onPost} />
  const match = (r: RouteResult) => `${resultTitle(r)} ${capturedText(r)} ${r.id}`.toLowerCase().includes(search.toLowerCase())
  const rows = (items: RouteResult[]) => {
    const visible = items.filter(match)
    return visible.length ? <ul className="q2-magnet-items">
      {visible.map((r) => <li key={`${r.kind}:${r.id}:${r.version ?? ''}`}>
        <span className="q2-magnet-attribution">{r.number ? `Post #${r.number}` : r.kind === 'post' ? 'Collected post' : 'Collected file'}{r.kind === 'attachment' ? ' · Attachment' : ''}</span>
        <button type="button" className="q2-magnet-item" onClick={() => inspect(resource, r.id, `item-${r.id}`)}>{resultTitle(r)}</button>
        {resultPreview(r) && <p className="q2-magnet-preview">{resultPreview(r)}</p>}
        {r.kind !== 'post' && (r.post || words(object(r.value).post)) && <button type="button" className="q2-magnet-link q2-magnet-at-post" onClick={() => inspect(resource, r.post ?? words(object(r.value).post), `item-${r.id}`)}>Inspect collected post</button>}
      </li>)}
    </ul> : <p className="q2-magnet-muted">No retained items match this search and content type.</p>
  }
  const empty = (what: string) => <p className="q2-magnet-muted">{s.loading ? 'Reading…' : s.error || s.reason || (!s.status ? 'This collection has not been read yet.' : partial ? `No ${what} in the page read so far. More may be available.` : `No ${what} in this collection's selected scope.`)}</p>
  if (lens === 'Posts') return <section>
    <div className="q2-magnet-section-title"><h3 id="view-title" tabIndex={-1}>Posts {postCount !== null && <span className="q2-magnet-count">{postCount}</span>}</h3></div>
    {posts.length ? rows(posts) : empty('posts')}
  </section>
  if (lens === 'Files') return <section>
    <div className="q2-magnet-section-title"><h3 id="view-title" tabIndex={-1}>Files {(files.length > 0 || s.status === 'ok' || s.status === 'partial') && <span className="q2-magnet-count">{files.length}</span>}</h3></div>
    {partial && <p className="q2-magnet-muted">This retained batch is partial.</p>}
    {files.length ? rows(files) : empty('files')}
  </section>
  return <section>
    <div className="q2-magnet-section-title"><h3 id="view-title" tabIndex={-1}>Retained information <span className="q2-magnet-count">{posts.length + files.length}</span></h3></div>
    {posts.length + files.length ? rows([...posts, ...files]) : empty('items')}
  </section>
}
