import { lazy, Suspense, useEffect, useState } from 'react'
import { CLIENT_HEADERS, type Part } from '../../api'
import { ViewerBody } from '../../quiet/media/MediaLayer'
import { returnedItemOf, type HeldBytes } from '../../quiet/media/view'
import { PDF_START, type PdfState } from '../viewer/types'
import type { RouteResult } from '../../fluid/surface/magnet/route'
import type { MagnetResource } from './contract'
import { inspect, place, writePlace, placeKeyOf } from './places'
import { PERSPECTIVE_DISCLOSURE } from './perspectives'

const PdfView = lazy(() => import('../viewer/PdfView'))
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

function HeldFile({ refId }: { refId: string }) {
  const [bytes, setBytes] = useState<HeldBytes | null>(null), [error, setError] = useState('')
  const [pdf, setPdf] = useState<PdfState>(PDF_START)
  useEffect(() => {
    const ctl = new AbortController(); setBytes(null); setError(''); setPdf(PDF_START)
    void fetch(`/api/artifacts/${encodeURIComponent(refId)}?describe=1`, { headers: CLIENT_HEADERS, signal: ctl.signal, cache: 'no-store' }).then(async (r) => {
      const v = await r.json()
      if (!r.ok || v.ref !== refId || v.state !== 'held') throw new Error(v.error ?? 'These retained bytes are unavailable.')
      if (!ctl.signal.aborted) setBytes({ ...v, url: `/api/artifacts/${encodeURIComponent(refId)}` })
    }).catch((e) => { if (!ctl.signal.aborted) setError(String(e.message ?? e)) })
    return () => ctl.abort()
  }, [refId])
  if (error) return <p role="status">{error}</p>
  if (!bytes) return <p role="status">Reading retained file…</p>
  const item = returnedItemOf(bytes)
  if (!item) return <p>This file has no viewable retained bytes.</p>
  return <div className="q2-magnet-file-view">
    <p className="q2-magnet-muted">{item.name} · {item.size ?? 'Unknown'} bytes</p>
    {item.treatment === 'pdf' ? <Suspense fallback={<p>Loading PDF viewer…</p>}><PdfView url={item.url} name={item.name} state={pdf} onState={setPdf} placement="column" /></Suspense> : <ViewerBody item={item} />}
    <a className="q2-magnet-link" href={item.url} download={item.name}>Download retained file</a>
  </div>
}

export default function Inspection({ resource, refId, back, source }: { resource: MagnetResource; refId: string; back(): void; source(r: RouteResult): void }) {
  const s = resource.snapshot(), all = [...s.results, ...retainedFiles(s.results)]
  const result = all.find((r) => r.id === refId || r.version === refId || artifactOf(r) === refId)
  const artifact = result && artifactOf(result)
  const heldSource = result && (result as RouteResult & { via?: string }).via === 'held-source'
  const heldValue = heldSource ? object(result.value) : null
  const batch = refId === s.activation?.artifact.ref
  return <section className="q2-magnet-inspection" aria-label="Retained evidence inspection">
    <button type="button" className="q2-magnet-link" onClick={back}>← Back to Magnet</button>
    <h3 id="inspect-title" tabIndex={-1}>{batch ? 'Retained collection evidence' : result?.kind === 'post' ? `Collected post${result.number ? ` #${result.number}` : ''}` : 'Collected file'}</h3>
    {batch ? <><p>This is {s.batchSelection ? 'the selected historical' : 'the latest'} retained batch, recorded {s.activation?.at ? new Date(s.activation.at * 1000).toLocaleString() : ''}.</p><p className="q2-magnet-muted">{refId} · {s.activation?.artifact.digest}</p><ul className="q2-magnet-items">{s.results.map((r) => <li key={`${r.kind}:${r.id}`}><button type="button" className="q2-magnet-link" onClick={() => inspect(resource, r.id)}>{r.kind === 'post' ? `Post ${r.number ?? ''}` : object(r.value).path || 'Collected file'} · {capturedText(r).slice(0, 90) || 'Captured content unavailable'}</button></li>)}</ul></>
      : result ? <>
        <details className="q2-magnet-provenance" open={place(s).provenance} onToggle={(e) => writePlace(resource, placeKeyOf(s), { provenance: e.currentTarget.open })}><summary>Provenance</summary><p className="q2-magnet-muted">{result.id} · captured version {result.version}{result.conversation ? ` · home ${result.conversation}` : ''}</p>{heldValue ? <p>{heldValue.collection} / {heldValue.path} · {heldValue.citation} · acquired {new Date(heldValue.acquired_at * 1000).toLocaleString()}</p> : <button type="button" className="q2-magnet-link" onClick={() => source(result)}>Navigate to source Conversation →</button>}</details>
        {result.kind === 'post' ? <>
          {result.deleted ? <p>This post was deleted at collection time.</p> : capturedText(result) ? <pre className="q2-magnet-post-text">{capturedText(result)}</pre> : <p>No readable text was retained for this post. No live source content was substituted.</p>}
          {(capturedBody(result).truncated || object(result.value).truncated) && <p role="status">This is a bounded excerpt. The collector marked it as truncated.</p>}
          <ul className="q2-magnet-items">{retainedFiles([result]).map((f) => <li key={f.id}><button type="button" className="q2-magnet-link" onClick={() => inspect(resource, f.id)}>{object(f.value).title || 'Inspect attachment'}</button></li>)}</ul>
        </> : heldValue ? <><pre className="q2-magnet-post-text">{heldValue.text}</pre><p>Captured bytes {heldValue.offset}–{heldValue.end} of {heldValue.size}.</p>{heldValue.shortened && <p role="status">Shortened: {heldValue.omitted_bytes} bytes omitted. Next offset {heldValue.next_offset}; this collection does not automatically capture another page.</p>}</> : artifact ? <HeldFile refId={artifact} /> : <p>This collected object has no supported retained file to display. Its provenance is retained; no live file was substituted.</p>}
      </> : /^adm-[a-zA-Z0-9]{6,40}$/.test(refId) ? <><p>Retained artifact. This view does not qualify it as a Perspective synthesis.</p><p>{PERSPECTIVE_DISCLOSURE}</p><HeldFile refId={refId} /></> : <p>This reference is not in the selected retained batch. Nothing was substituted from the live source. Choose its original historical batch to inspect the captured version.</p>}
  </section>
}
