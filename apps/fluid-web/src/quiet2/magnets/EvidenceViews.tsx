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
import { useEffect, useState, useSyncExternalStore } from 'react'
import { CLIENT_HEADERS } from '../../api'
import type { RouteResult } from '../../fluid/surface/magnet/route'
import type { MagnetResource, MagnetSearchKind, SearchEntry, SearchSource } from './contract'
import Inspection, { capturedText, evidenceBounds, evidenceOrigin, retainedFiles } from './Inspection'
import { MAGNET_COLLECTION_FILTERS, goTab, inspect, place, placeKeyOf, writePlace } from './places'
import { SUPPORTING_WHY } from './perspectives'
import CollectionConfiguration from './CollectionConfiguration'
import { SearchToolbar } from './SearchView'
import { magnetName, supportsManualCollection } from './configuration'
import './design.css'
import './summary.css'
import './perspectives.css'
import './configuration.css'
import './collection.css'

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
/** When a collection was last captured, the way the approved browse line says
 *  it ("Collected today"): a day, never the raw recorded number. The Sources
 *  surface gives the clock as well (`CollectionConfiguration.lastCollected`). */
export function collectedDay(at?: number | null): string | null {
  if (typeof at !== 'number' || !Number.isFinite(at)) return null
  const d = new Date(at * 1000)
  return d.toDateString() === new Date().toDateString() ? 'today' : d.toLocaleDateString([], { month: 'short', day: 'numeric' })
}

/* -- WHO, BY NAME ------------------------------------------------------------
   The collection read states a post's author as the participant's recorded
   entry id (`route.ts` `author`), which is exactly the raw identifier the
   approved rows must not carry (owner request ent-1e82a8786c37; the mockup's
   row reads "Alex · today, 10:31 AM"). The names come from the participants
   read the conversation card already makes (`conversations/Tombstone.tsx`),
   once per page, and nothing here reads a live source. A name that is not
   known leaves the row saying what the item is, never the id. */
let people: Promise<Map<string, string>> | null = null
function readPeople(): Promise<Map<string, string>> {
  people ??= fetch('/fluid/api/participants?limit=500', { headers: CLIENT_HEADERS })
    .then((r) => (r.ok ? r.json() : { participants: [] }))
    .then((j: { participants?: { id: string; alias: string }[] }) =>
      new Map((j.participants ?? []).map((p) => [p.id, String(p.alias ?? '').replace(/^@/, '')])))
    .catch(() => { people = null; return new Map<string, string>() })
  return people
}
export function usePeople(): Map<string, string> {
  const [named, setNamed] = useState<Map<string, string>>(new Map())
  useEffect(() => {
    let live = true
    void readPeople().then((m) => { if (live) setNamed(m) })
    return () => { live = false }
  }, [])
  return named
}

/** THE CLEAN ROW'S BYLINE (approved mockup round 3, 04-browse.png): who or
 *  what it was captured from, and when -- never a raw Conversation id, source
 *  key, participant id or recorded digest, which `evidenceOrigin`
 *  (Inspection.tsx) carries for the inspection's own provenance disclosure,
 *  not for a list row. `named` is the participants read above; without it, or
 *  for an author it does not name, the row says what the item is. */
/** A recorded identity, in any of the record's own prefixed shapes. What the
 *  collection read states as a post's `author` is one of these, and no row ever
 *  shows one; a build that states a name there is shown as it is. */
const RECORDED_ID = /^(?:ent|adm|col|mag|opr|def)-[a-z0-9]{6,}$/i

export function rowByline(r: RouteResult, named?: Map<string, string>): string {
  const when = rowWhen(r.at)
  if (isHeldSource(r)) return ['Held file', when].filter(Boolean).join(' · ')
  // The participants read states aliases with their leading @; a byline is a
  // name, not a mention, and a caller that hands over an unstripped map gets
  // the same clean row. Failing a name, the stated author is used only when it
  // is not itself a recorded id -- so a row says a person where one is known,
  // and what the item is otherwise, and an id in neither case.
  const stated = r.author && !RECORDED_ID.test(r.author) ? r.author : undefined
  const who = ((r.author ? named?.get(r.author) : undefined) ?? stated)?.replace(/^@/, '')
  if (r.kind === 'post') return [who || 'Collected post', when].filter(Boolean).join(' · ')
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
  const named = usePeople()
  const { posts, files } = retainedItems(resource)
  const items = [...posts, ...files]
  return <section className="q2-magnet-supporting" aria-label="Supporting items">
    <h4>Supporting items</h4>
    {question && <p className="q2-magnet-muted">For “{question}”</p>}
    {items.length ? <ul className="q2-magnet-items">{items.map((r) => <li key={`${r.kind}:${r.id}`}>
      <p className="q2-magnet-supporting-head"><strong>{resultTitle(r)}</strong><small className="q2-magnet-muted"> · {rowByline(r, named)}</small></p>
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
  const named = usePeople()
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
  const rows = () => <ul className="q2-magnet-items q2-magnet-collected-items">
    {items.map((r) => <li key={`${r.kind}:${r.id}:${r.version ?? ''}`} className="mgd-item">
      <button type="button" id={`item-${r.id}`} className="q2-magnet-evidence-row" aria-expanded={here.inspected === r.id}
        onClick={() => inspect(resource, r.id, `item-${r.id}`)}>
        <span className="q2-magnet-row-text">
          <b>{resultTitle(r)}</b>
          {resultPreview(r) && <p className="q2-magnet-preview">{resultPreview(r)}</p>}
          <small className="mgd-subtle">{rowByline(r, named)}</small>
        </span>
      </button>
      {here.inspected === r.id && <Inspection resource={resource} refId={r.id} source={onPost} />}
      {r.kind !== 'post' && (r.post || words(object(r.value).post)) && here.inspected !== r.id &&
        <button type="button" className="q2-magnet-link q2-magnet-at-post" onClick={() => inspect(resource, r.post ?? words(object(r.value).post), `item-${r.id}`)}>View the collected post</button>}
    </li>)}
  </ul>
  const empty = (what: string) => <p className="mgd-p mgd-muted">{s.loading ? 'Reading…'
    : s.error || s.reason || (!read ? 'This collection has not been read yet. Opening never collects and never reads a live source.'
      : !s.activation ? 'No collected information yet. Conversation is still available.'
        : partial ? `No ${what} collected so far. More may be available.` : `No ${what} in what this Magnet collects.`)}</p>
  /** An inspection reached from elsewhere (a search result, the host) for an
   *  item this list does not hold still has to be readable. */
  const elsewhere = here.inspected && !items.some((r) => r.id === here.inspected)
  // SOURCE MANAGEMENT, INTEGRATED INTO COLLECTION (approved mockup round 3,
  // 03-sources.png / 04-browse.png): the unified `All` place shows either the
  // collected items or its own Sources, reusing B's panel exactly as Settings
  // does -- the staged draft lives in `panelDrafts`, keyed by Brain and Magnet
  // rather than by which copy of the panel is on screen, so editing here and
  // editing in Settings is the same unsaved edit. This needs no seam into Host
  // or the frame: `resource` already carries what it saves through
  // (`saved.config`, `saved.id`).
  //
  // The disclosure is the place's own (`contract.ts` `MagnetPlace.sources`),
  // not local state: the shell's own "Sources" entry (`Magnet.tsx`,
  // `showSourcesInline`) writes the same flag, so the two are one entry, not
  // a second implementation of source management.
  const config = resource.saved.config
  const showSources = lens === 'All' && !!config && here.sources
  const mayWriteArrangement = canWrite ?? NO_WRITE
  if (showSources) return <CollectionConfiguration magnet={resource.saved.id} config={config!} brainKey={resource.brainKey}
    inCollection resource={resource} canWrite={mayWriteArrangement}
    onBrowse={() => writePlace(resource, placeKeyOf(s), { sources: false })}
    onSaved={(next) => {
      resource.saved.config = next; resource.saved.name = magnetName(next, resource.saved.name); resource.saved.reason = undefined
      resource.update({ title: resource.saved.name }); void resource.read()
    }} />
  // COLLECTED ITEMS, to the approved design (04-browse.png): the place's own
  // heading block with the counterpart link on its row, the search and the
  // type filters under it, the rows, and one closing line. The frame no longer
  // draws the filter row or a search box (plan seam 1): the controls are the
  // same ones, drawn where the design puts them. Nothing is said twice.
  const collectable = !!config && supportsManualCollection(config)
  const mayCollect = mayWriteArrangement('home') && collectable && !s.collecting
  const collectedOn = collectedDay(s.activation?.at)
  return <section className="q2-magnet-collected">
    <div className="mgd-row mgd-spread q2-magnet-place-head">
      <div className="mgd-grow">
        <div className="mgd-eyebrow">Collection</div>
        <h2 id="view-title" className="mgd-h2" tabIndex={-1}>Collected items{read && <span className="mgd-subtle"> {items.length}</span>}</h2>
      </div>
      {!!config && <button type="button" className="mgd-link mgd-small q2-magnet-place-link"
        onClick={() => { goTab(resource, 'All'); writePlace(resource, 'All', { sources: true }) }}>Sources · {config.sources.length} →</button>}
    </div>
    <SearchToolbar resource={resource} placeholder="Search collected items" />
    {/* SEAM: `04-browse.png` shows four pills -- All / Posts / Files / Images.
        Three exist: the lens state has `MAGNET_COLLECTION_TABS`, and the place
        keys behind them are `contract.ts`'s `MAGNET_TABS`. Both are shared,
        carrier-owned files this part does not change, so the fourth is not
        drawn here rather than drawn with nothing behind it. Images are in the
        collection and are listed under `Files` and `All`, as they were. */}
    <div className="mgd-row q2-magnet-type-pills" role="group" aria-label="Show in the collection">
      {/* Which filter is showing is this view's own identity -- Host mounts the
          one instance that matches the tab -- so the pill follows `lens` rather
          than re-deriving it from the snapshot. The filters themselves, and
          what pressing one does, are `places.ts`'s and unchanged. */}
      {MAGNET_COLLECTION_FILTERS.map((f) => <button type="button" key={f.tab} className={`mgd-pill${lens === f.tab ? ' mgd-active' : ''}`}
        aria-pressed={lens === f.tab} onClick={() => goTab(resource, f.tab)}>{f.tab}</button>)}
    </div>
    {partial && read && !!s.activation && <p className="mgd-subtle q2-magnet-partial">This collection is partial.</p>}
    {elsewhere && <Inspection resource={resource} refId={here.inspected!} source={onPost} />}
    {items.length ? rows() : empty(lens === 'Posts' ? 'posts' : lens === 'Files' ? 'files' : 'items')}
    {/* The one closing line the design gives this surface: when it was
        collected, and the way to collect again. The same `resource.collect()`
        the header used to offer (plan seam 3), under the same capability the
        panel's own save is gated by -- never an offer of a write that would
        then be refused. */}
    {!!config && <p className="mgd-subtle q2-magnet-collected-line">
      {collectedOn ? `Collected ${collectedOn}` : 'Not collected yet'} · <button type="button" className="mgd-link mgd-small"
        disabled={!mayCollect} title={collectable ? undefined : 'Manual collection is not configured'}
        onClick={() => void resource.collect?.()}>{s.collecting ? 'Collecting…' : 'Collect now'}</button>
    </p>}
  </section>
}
