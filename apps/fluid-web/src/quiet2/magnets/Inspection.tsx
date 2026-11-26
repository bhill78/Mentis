/** In-card inspection of one retained item.
 *
 *  It is rendered **inline**, directly beneath the row or support that was
 *  clicked and inside the section the reader was already in -- never a separate
 *  screen (plan §5-H3-4, approved `inspection()` in `preview-script.js`). Its
 *  provenance disclosure keeps its open state in the current place, so a return
 *  finds it exactly as it was left.
 *
 *  Nothing here reads a live source. When a reference is not in the batch shown,
 *  it says so and substitutes nothing.
 *
 *  **BY WHAT IT REPRESENTS, NOT BY HOW IT IS STORED** (owner #1017
 *  `ent-599e68de0893`, plan Part 5). A collected article is prose, and it was
 *  being shown as a `<pre>` of its captured bytes -- monospaced, unwrapped,
 *  with its headline and its address run through the top of the block as two
 *  more lines of text. It is the same bytes either way; what changes is that
 *  the reader can read them. So the record's own headline is a heading, its
 *  recorded address is a link, and its material is drawn by the renderer Fluid
 *  already has for written material (`Prose`, `src/prose.tsx`) -- in `untrusted`
 *  mode for anything acquired from the web, which is text nobody in this Brain
 *  wrote: its fences are shown as their own source and no marked block or HTML
 *  preview is drawn from them. Images, video, audio and PDF keep the viewer
 *  they already had (`ViewerBody`, `PdfView`), which is the same principle
 *  applied before this part existed.
 *
 *  No renderer is edited and none is written: this file imports two that exist. */
import { lazy, Suspense, useEffect, useState, useSyncExternalStore } from 'react'
import type { ReactNode } from 'react'
import { CLIENT_HEADERS, type Part } from '../../api'
import { Prose } from '../../prose'
import { ViewerBody } from '../../quiet/media/MediaLayer'
import { returnedItemOf, type HeldBytes } from '../../quiet/media/view'
import { PDF_START, type PdfState } from '../viewer/types'
import type { RouteResult } from '../../fluid/surface/magnet/route'
import { MAGNET_TABS } from './contract'
import type { MagnetContext, MagnetPlaceKey, MagnetResource } from './contract'
import { SourceLink, heldHeader, linkHost, rowHeadline, rowLink } from './links'
import { closeInspect, inspect, place, writePlace, placeKeyOf } from './places'
import { PERSPECTIVE_DISCLOSURE } from './perspectives'
import './summary.css'

const PdfView = lazy(() => import('../viewer/PdfView'))
const when = (at?: number | null) => typeof at === 'number' && Number.isFinite(at) ? new Date(at * 1000).toLocaleString() : null
const object = (v: unknown): Record<string, any> => v && typeof v === 'object' && !Array.isArray(v) ? v as Record<string, any> : {}
export function capturedBody(r: RouteResult): Record<string, any> {
  const value = object(r.value)
  if (typeof value.body_json === 'string') try { return object(JSON.parse(value.body_json)) } catch { return {} }
  return object(value.body ?? value)
}
export function capturedText(r: RouteResult): string {
  const v = capturedBody(r)
  return typeof v.text === 'string' ? v.text : Array.isArray(v.parts) ? v.parts.filter((p: any) => p.type === 'text' && typeof p.text === 'string').map((p: any) => p.text).join('\n\n') : ''
}
export function artifactOf(r: RouteResult): string | null {
  const v = object(r.value), p = object(v.preview)
  const candidates = [r.id, v.ref, object(v.artifact).ref, p.ref, object(p.artifact).ref]
  return candidates.find((s) => typeof s === 'string' && /^adm-[a-zA-Z0-9]{6,40}$/.test(s)) ?? null
}
export function retainedFiles(rows: RouteResult[]): RouteResult[] {
  const out = new Map<string, RouteResult>()
  for (const r of rows) if (r.kind !== 'post') out.set(artifactOf(r) ?? r.id, r)
  for (const r of rows) if (r.kind === 'post') {
    const parts = capturedBody(r).parts
    if (!Array.isArray(parts)) continue
    for (const p of parts as Part[]) if ((p.type === 'image' || p.type === 'file') && p.ref && /^adm-[a-zA-Z0-9]{6,40}$/.test(p.ref)) {
      if (!out.has(p.ref)) out.set(p.ref, { ...r, kind: p.type, id: p.ref, post: r.id, value: { ref: p.ref, title: p.alt || p.ref, media_type: p.media_type } })
    }
  }
  return [...out.values()]
}

/** The readable name of a captured source, from `collectionRows`'s own key.
 *  `conversation:<entry>` and `file:<collection>:<path>` are the only two shapes
 *  the verifier admits, so nothing here is guessed. */
export function sourceLabel(key: string | undefined | null): string {
  if (typeof key !== 'string' || !key) return 'Captured source unstated'
  if (key.startsWith('conversation:')) return `Conversation ${key.slice('conversation:'.length)}`
  if (key.startsWith('file:')) {
    const rest = key.slice('file:'.length), cut = rest.indexOf(':')
    const collection = cut < 0 ? rest : rest.slice(0, cut), path = cut < 0 ? '' : rest.slice(cut + 1)
    return `Held file ${collection}${path ? ` / ${path}` : ''}`
  }
  return key
}
export const capturedSourceKey = (r: RouteResult): string | undefined =>
  (r as RouteResult & { capturedSourceKey?: string }).capturedSourceKey

/** Where this retained item came from, said from what was captured with it. */
export function evidenceOrigin(r: RouteResult): string {
  const held = object(r.value)
  if ((r as RouteResult & { via?: string }).via === 'held-source' && typeof held.collection === 'string') return sourceLabel(`file:${held.collection}:${held.path ?? ''}`)
  const key = capturedSourceKey(r)
  if (key) return sourceLabel(key)
  if (r.conversation) return `Conversation ${r.conversation}`
  if (r.post) return 'Attached to a collected post'
  return 'Captured source unstated'
}

/** THE ORIGIN A READER IS SHOWN, with no recorded identity in it.
 *
 *  `sourceLabel` and `evidenceOrigin` keep the exact captured key -- a
 *  Conversation entry id, a collection key -- and they stay as they are: the
 *  inspection's own provenance disclosure is where the owner asked for lineage
 *  to remain readable (request ent-1e82a8786c37). A row, an excerpt or anything
 *  else on the resting surface says what kind of thing the item came from, and
 *  for a held file its file name, and never an id ("clean Collection rows ...
 *  without raw identifiers or unnecessary technical symbols"). */
export function plainEvidenceOrigin(r: RouteResult): string {
  const held = object(r.value)
  if ((r as RouteResult & { via?: string }).via === 'held-source')
    return `Held file${typeof held.path === 'string' && held.path ? ` · ${held.path}` : ''}`
  if (r.kind === 'post') return 'Collected post'
  if (r.post) return 'Attached to a collected post'
  if (r.conversation) return 'Collected from a Conversation'
  return 'Captured source unstated'
}

/** The capture bounds, derived -- never a claim the collector did not record. */
export function evidenceBounds(r: RouteResult): string {
  const v = object(r.value)
  if ((r as RouteResult & { via?: string }).via === 'held-source' && typeof v.end === 'number')
    return `Captured bytes ${v.offset ?? 0}–${v.end} of ${v.size}${v.shortened ? ` · shortened, ${v.omitted_bytes} bytes omitted` : ' · the whole held file'}`
  if (r.kind !== 'post') return `Captured attachment bytes of ${artifactOf(r) ?? r.id}`
  if (capturedBody(r).truncated || v.truncated) return 'Bounded excerpt · the collector marked this post truncated'
  return 'The whole post, as it was collected'
}

/** Discuss this record: the one explicit action that attaches a reference to
 *  the composer and clears suppression (`hybrid.js:51`). It carries the
 *  **reference only** -- captured content never enters the attached context, and
 *  `contract.ts` keeps only `ref`, `kind` and `label` in device storage.
 *
 *  H2 owns the composer; the contract fields it reads (`context`,
 *  `contextSuppressed`) are H1's, so this writes them and nothing else. If H2
 *  exports its own forced-context action, this becomes its one caller.
 *
 *  THE LABEL LEADS WITH THE ROW'S OWN WORDS WHERE IT HAS THEM. A collected web
 *  row's headline and site are read back out of its own verified bytes
 *  (`links.tsx` `rowHeadline`, `linkHost`), exactly as the row itself already
 *  leads with them -- never the held-file key underneath. The reference
 *  attached is still `r.id`: only what the chip says changes. */
export function discussEvidence(resource: MagnetResource, r: RouteResult) {
  const kind: MagnetContext['kind'] = r.kind === 'post' || r.kind === 'file' || r.kind === 'image' || r.kind === 'attachment' ? r.kind : 'file'
  const headline = rowHeadline(r)
  const site = headline ? linkHost(rowLink(r)) : null
  const label = headline ? `${headline}${site ? ` · ${site}` : ''}`
    : `${r.kind === 'post' ? 'Collected post' : 'Collected file'} · ${evidenceOrigin(r)}`
  resource.update({ context: { ref: r.id, kind, label }, contextSuppressed: false })
}

/** THE CAPTURED WORDS OF ONE RECORD, PRESENTED AS WHAT THEY ARE.
 *
 *  Where a record recorded a header of its own -- its headline, a blank line,
 *  its permalink (`mentis/sources/webpages.py::_page_body`,
 *  `mentis/sources/feeds.py::_entry_body`, read back by `links.tsx::heldHeader`
 *  out of the row's already-verified bytes) -- that header is drawn as a
 *  heading and a link, and what is under it is drawn as prose. Where it
 *  recorded none, the whole captured text is the prose.
 *
 *  `acquired` says whether these words came from outside this Brain. They go
 *  to `Prose` as `untrusted` when they did, so a fence in an acquired page is
 *  shown as its own source and nothing is drawn from it.
 *
 *  A record whose captured text holds no prose at all -- a feed entry that
 *  recorded a headline and an address and nothing else -- says that, rather
 *  than drawing an empty column where its words would be. */
export const NOTHING_BUT_A_HEADER = 'This record captured its headline and its address and no further words. Nothing was fetched to fill it in.'
export function CapturedWords({ text, acquired, scope }: { text: string; acquired: boolean; scope: string }) {
  // `heldHeader` is `links.tsx`'s own reader of those recorded bytes, used here
  // on the captured text directly rather than on a row: this component is given
  // the text, and a header is a property of the text.
  const header = heldHeader(text)
  const body = header.body.trim()
  return <div>
    {!!header.headline && <h4 className="mgd-h3">{header.headline}</h4>}
    {!!header.link && <SourceLink url={header.link} />}
    {body
      ? <div className="q2-prose"><Prose src={body} scope={scope} untrusted={acquired} /></div>
      : <p className="mgd-subtle">{header.link ? NOTHING_BUT_A_HEADER : 'No readable text was collected for this record. No live source content was substituted.'}</p>}
  </div>
}

function HeldFile({ refId }: { refId: string }) {
  const [bytes, setBytes] = useState<HeldBytes | null>(null), [error, setError] = useState('')
  const [pdf, setPdf] = useState<PdfState>(PDF_START)
  useEffect(() => {
    const ctl = new AbortController(); setBytes(null); setError(''); setPdf(PDF_START)
    void fetch(`/api/artifacts/${encodeURIComponent(refId)}?describe=1`, { headers: CLIENT_HEADERS, signal: ctl.signal, cache: 'no-store' }).then(async (r) => {
      const v = await r.json()
      if (!r.ok || v.ref !== refId || v.state !== 'held') throw new Error(v.error ?? 'The collected copy of this file is unavailable.')
      if (!ctl.signal.aborted) setBytes({ ...v, url: `/api/artifacts/${encodeURIComponent(refId)}` })
    }).catch((e) => { if (!ctl.signal.aborted) setError(String(e.message ?? e)) })
    return () => ctl.abort()
  }, [refId])
  if (error) return <p className="mgd-subtle" role="status">{error}</p>
  if (!bytes) return <p className="mgd-subtle" role="status">Reading the file…</p>
  const item = returnedItemOf(bytes)
  if (!item) return <p className="mgd-p">There is nothing in this file this card can show.</p>
  return <div className="q2-magnet-file-view">
    <p className="mgd-subtle">{item.name} · {item.size ?? 'Unknown'} bytes</p>
    {item.treatment === 'pdf' ? <Suspense fallback={<p className="mgd-subtle">Loading PDF viewer…</p>}><PdfView url={item.url} name={item.name} state={pdf} onState={setPdf} placement="column" /></Suspense> : <ViewerBody item={item} />}
    <a className="mgd-link mgd-small" href={item.url} download={item.name}>Download this file</a>
  </div>
}

/** A view slot that shows the inspection its place holds, in place of the view.
 *
 *  Any view may offer a citation control -- a reference in a Conversation post,
 *  an immutable Perspective revision, an item in an evidence list -- and all of
 *  them call `inspect()`, which writes the reference into the place. This is
 *  where that reference becomes the rendered evidence and its one Back control,
 *  inside the card the reader asked from. */
export function WithInspection({ resource, source, children }: { resource: MagnetResource; source(r: RouteResult): void; children: ReactNode }) {
  const s = useSyncExternalStore(resource.subscribe, resource.snapshot, resource.snapshot)
  const here = place(s)
  if (!here.inspected) return <>{children}</>
  return <Inspection resource={resource} refId={here.inspected} back={() => closeInspect(resource)} source={source} />
}

/** Compose the view slots so EVERY tab shows its place's inspection, rather than
 *  each view remembering to render one. A citation anywhere therefore reaches
 *  the same inspection and the same Back; a view that renders its own (Summary,
 *  EvidenceViews) still works when mounted on its own. The frame is untouched:
 *  it still renders only `views[placeKey]`. `search` and `settings` are left
 *  alone -- neither is a place a reference is inspected from. */
export function withInspections(resource: MagnetResource, views: Partial<Record<MagnetPlaceKey, ReactNode>>, source: (r: RouteResult) => void) {
  const out = { ...views }
  for (const tab of MAGNET_TABS) {
    if (views[tab] === undefined) continue
    out[tab] = <WithInspection resource={resource} source={source}>{views[tab]}</WithInspection>
  }
  return out
}

export interface InspectionProps {
  resource: MagnetResource
  refId: string
  /** The host's navigation to the source Conversation of a retained item. */
  source(r: RouteResult): void
  /** Closing returns to the row this was opened from; the spine knows where. */
  back?(): void
}

export default function Inspection({ resource, refId, source, back }: InspectionProps) {
  const s = resource.snapshot(), all = [...s.results, ...retainedFiles(s.results)]
  const result = all.find((r) => r.id === refId || r.version === refId || artifactOf(r) === refId)
  const artifact = result && artifactOf(result)
  const heldSource = result && (result as RouteResult & { via?: string }).via === 'held-source'
  const heldValue = heldSource ? object(result.value) : null
  const batch = refId === s.activation?.artifact.ref
  const close = back ?? (() => closeInspect(resource))
  const captured = result?.at ?? s.activation?.at
  /* THE RECORD OPENED INSIDE THE CARD, in the approved design's language. It is
     the `mgd-answer` block -- the gold left rule the mockups give a reply or a
     detail opened out of a list -- with its own heading row, the captured words,
     and provenance behind the same `▾` disclosure the other surfaces use. Every
     control is the one that was here: closing, each listed record, the source
     Conversation, Discuss this record. */
  return <article className="q2-magnet-inline-evidence q2-magnet-inspection" aria-labelledby="inspect-title">
    <div className="mgd-row mgd-spread">
      <h3 id="inspect-title" className="mgd-h3 mgd-grow" tabIndex={-1}>{batch ? 'Collected information' : result ? result.kind === 'post' ? `Collected post${result.number ? ` #${result.number}` : ''}` : 'Collected file' : 'Not in this collection'}</h3>
      <button type="button" className="q2-magnet-icon" aria-label="Close this record" title="Close this record" onClick={close}>×</button>
    </div>
    {/* WHERE IT CAME FROM, WITHOUT A STORAGE IDENTITY ON THE RESTING SURFACE.
        This said `evidenceOrigin`, which keeps the exact captured key by
        design -- so the line under the heading read "Collected file · Held file
        col-astronomy / space-missions/aaa111111111", the collection key and
        object key the owner asked to be rid of, directly above the record's own
        headline. For a row that recorded an address the site is what a reader
        recognises; otherwise `plainEvidenceOrigin`, which is the clean one this
        file already exports for resting surfaces. The exact key is unchanged
        and one press away, under "Where this came from". */}
    {result && !batch && <p className="mgd-subtle">Collected {result.kind === 'post' ? 'post' : 'file'} · {linkHost(rowLink(result)) ?? plainEvidenceOrigin(result)}</p>}
    {batch ? <><p className="mgd-p">This is {s.batchSelection ? 'the collection as it was' : 'what this Magnet has collected'}, recorded {when(s.activation?.at)}.</p>
      <p className="mgd-subtle">{refId} · {s.activation?.artifact.digest}</p>
      {/* EACH ROW BY ITS OWN WORDS. This list led with the raw storage object
          key for every held row (`value.path`:
          "space-missions-and-astronomy-what-launch/a733ec1ec5e51a4b"), which is
          where the record is stored and not what it is. Its own recorded
          headline is what it is; the key is still in the provenance disclosure
          of the record itself. */}
      {s.results.map((r) => <div className="mgd-item" key={`${r.kind}:${r.id}`}><button type="button" className="mgd-link mgd-small" onClick={() => inspect(resource, r.id)}>{rowHeadline(r) || (r.kind === 'post' ? `Post ${r.number ?? ''}` : 'Collected file')} · {heldHeader(capturedText(r)).body.replace(/\s+/g, ' ').trim().slice(0, 90) || 'Captured content unavailable'}</button></div>)}</>
      : result ? <>
        {result.kind === 'post' ? <>
          {/* A COLLECTED POST IS WRITTEN MATERIAL, so it is drawn as prose by
              the same renderer that draws a post everywhere else in Fluid --
              not as a monospaced byte block. Written in this Brain, so it is
              trusted text, exactly as `quiet2/Post.tsx` treats it. */}
          {result.deleted ? <p className="mgd-p">This post was deleted at collection time.</p> : capturedText(result) ? <CapturedWords text={capturedText(result)} acquired={false} scope={`magnet-record:${result.id}`} /> : <p className="mgd-p">No readable text was collected for this post. No live source content was substituted.</p>}
          {(capturedBody(result).truncated || object(result.value).truncated) && <p className="mgd-subtle" role="status">This is a bounded excerpt. The collector marked it as truncated.</p>}
          {retainedFiles([result]).map((f) => <div className="mgd-item" key={f.id}><button type="button" className="mgd-link mgd-small" onClick={() => inspect(resource, f.id)}>{object(f.value).title || 'View the attachment'}</button></div>)}
        </> : heldValue ? <>{/* ACQUIRED MATERIAL: its recorded headline and
              address are drawn as a heading and a link, its words as prose,
              and because nobody in this Brain wrote them they go to `Prose`
              as untrusted -- no marked block and no HTML preview from a page
              Mentis fetched. */}
          <CapturedWords text={typeof heldValue.text === 'string' ? heldValue.text : ''} acquired scope={`magnet-record:${result.id}`} />
          {heldValue.shortened && <p className="mgd-subtle" role="status">Shortened: {heldValue.omitted_bytes} bytes omitted. Next offset {heldValue.next_offset}; this collection does not automatically capture another page.</p>}</>
          : artifact ? <HeldFile refId={artifact} /> : <p className="mgd-p">This collected record has no file this card can show. Where it came from is kept; no live file was substituted.</p>}
        <details className="q2-magnet-provenance q2-magnet-disclosure" open={place(s).provenance} onToggle={(e) => writePlace(resource, placeKeyOf(s), { provenance: e.currentTarget.open })}>
          <summary><span className="mgd-link mgd-small">Where this came from ▾</span></summary>
          <dl>
            <dt>Origin</dt><dd>{evidenceOrigin(result)}</dd>
            <dt>Version</dt><dd>{result.version ?? result.id}</dd>
            <dt>Captured</dt><dd>{when(captured) ?? 'Capture time unstated'}</dd>
            <dt>Bounds</dt><dd>{evidenceBounds(result)}</dd>
          </dl>
          {heldValue ? <p className="mgd-subtle">{heldValue.collection} / {heldValue.path} · {heldValue.citation} · acquired {when(heldValue.acquired_at)}</p>
            : <button type="button" className="mgd-link mgd-small" onClick={() => source(result)}>Source Conversation →</button>}
          <p className="mgd-subtle">The captured copy only. No live source was opened to show this.</p>
        </details>
        <button type="button" className="mgd-link mgd-small" id="discuss-evidence" onClick={() => discussEvidence(resource, result)}>Discuss this record</button>
      </>
      : /^adm-[a-zA-Z0-9]{6,40}$/.test(refId) ? <><p className="mgd-p">A collected file. This view does not qualify it as a Perspective synthesis.</p><p className="mgd-subtle">{PERSPECTIVE_DISCLOSURE}</p><HeldFile refId={refId} /></>
        : <p className="mgd-p">This record is not in the collection shown. Nothing was substituted from the live source. Choose the collection it was in, under Collection history, to read the copy that was captured.</p>}
  </article>
}
