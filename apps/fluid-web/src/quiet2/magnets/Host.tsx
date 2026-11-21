import { useEffect, useRef, useState, useSyncExternalStore } from 'react'
import { CLIENT_HEADERS } from '../../api'
import { closeViewer, openViewer, useViewerLayout } from '../viewer/viewers'
import { nextResourceId, registerResource, resourceById, resourcesOfBrain, sessionsVersion, subscribeSessions } from '../space/registry'
import { createMagnetResource, discoverMagnets } from './read'
import type { MagnetGet, SavedMagnet } from './contract'
import type { MagnetOrigin, QuietMagnetResource } from './navigation'
import type { RouteResult } from '../../fluid/surface/magnet/route'
import Magnet from './Magnet'

const get: MagnetGet = async (path, signal) => {
  const r = await fetch(path, { headers: CLIENT_HEADERS, signal, cache: 'no-store' })
  return { status: r.status, body: await r.json().catch(() => null) }
}
export const findMagnet = (id: string) => resourceById<QuietMagnetResource>('magnet', id)
export interface MagnetHostProps {
  brainKey: string | null; conversation: string | null; signal: number;
  capture(): MagnetOrigin; notice(words: string): void;
  expand(r: QuietMagnetResource): void; collapse(r: QuietMagnetResource): void;
  close(r: QuietMagnetResource): void; origin(r: QuietMagnetResource): void;
  conversationTo(r: QuietMagnetResource, conversation: string): void;
  post(r: QuietMagnetResource, result: RouteResult): void;
  file(r: QuietMagnetResource, result: RouteResult): void;
}
export default function MagnetHost(p: MagnetHostProps) {
  useSyncExternalStore(subscribeSessions, sessionsVersion)
  const viewers = useViewerLayout()
  const [chooser, setChooser] = useState(false)
  const [rows, setRows] = useState<SavedMagnet[]>([])
  const [words, setWords] = useState('')
  const request = useRef<AbortController | null>(null)
  const origin = useRef<MagnetOrigin | null>(null)
  const requested = useRef(0)
  const identity = useRef(p.brainKey); identity.current = p.brainKey
  const stage = [...viewers.values()].find((v) => v.place === 'max' && v.content.kind === 'magnet')?.id
  useEffect(() => {
    if (!stage) return
    requestAnimationFrame(() => document.querySelector<HTMLElement>('.q2-magnet-stage button')?.focus())
  }, [stage])
  useEffect(() => {
    request.current?.abort(); setChooser(false); setRows([])
    return () => request.current?.abort()
  }, [p.brainKey, p.conversation])
  useEffect(() => {
    if (!p.signal || p.signal === requested.current) return
    requested.current = p.signal
    origin.current = p.capture()
    setChooser(true); setRows([])
    if (!p.brainKey || !p.conversation) { setWords('A resolved Brain and a current conversation are required.'); return }
    const key = p.brainKey, control = new AbortController()
    request.current?.abort(); request.current = control; setWords('Reading this conversation’s saved Magnets…')
    void discoverMagnets(p.conversation, get, control.signal).then((found) => {
      if (control.signal.aborted || identity.current !== key) return
      setRows(found); setWords(found.length ? 'Saved in this conversation. Opening and moving are local to this tab.' : 'No saved Magnet placements in this conversation.')
    }).catch((e: Error) => { if (!control.signal.aborted && identity.current === key) setWords(e.message) })
    return () => control.abort()
  }, [p.signal, p.brainKey, p.conversation])
  const open = (saved: SavedMagnet) => {
    if (!p.brainKey || !saved.config || saved.reason) return
    const existing = resourcesOfBrain<QuietMagnetResource>('magnet', p.brainKey).find((r) => r.saved.id === saved.id)
    if (existing) {
      setChooser(false)
      document.querySelector<HTMLElement>(`[data-magnet-resource="${existing.id}"] button`)?.focus()
      return
    }
    const captured = origin.current ?? p.capture()
    const r = registerResource('magnet', Object.assign(createMagnetResource({ id: nextResourceId(), brainKey: p.brainKey, saved, get }), { origin: captured }))
    const n = resourcesOfBrain('magnet', p.brainKey).length
    r.update({ x: 24 + (n - 1) * 112, y: 24 })
    openViewer({ kind: 'magnet', resourceId: r.id, magnetId: saved.id, brainKey: r.brainKey }, { kind: 'brain', brainKey: r.brainKey }, 'canvas')
    setChooser(false)
  }
  return <>
    {p.brainKey && [...viewers.values()].filter((v) => v.content.kind === 'magnet' && v.content.brainKey === p.brainKey && (v.place === 'canvas' || v.place === 'max')).map((v) => {
      if (v.content.kind !== 'magnet') return null
      const r = findMagnet(v.content.resourceId)
      if (!r) { queueMicrotask(() => closeViewer(v.id)); return null }
      const max = [...viewers.values()].some((o) => o.place === 'max' && o.id !== v.id)
      return <div className={v.place === 'max' ? 'q2-magnet-stage' : 'q2-magnet-canvas'} key={v.id} hidden={max} data-magnet-resource={r.id}
        role={v.place === 'max' ? 'dialog' : undefined} aria-modal={v.place === 'max' ? true : undefined} aria-label={v.place === 'max' ? 'Magnet details' : undefined}
        onKeyDown={(e) => {
          if (v.place !== 'max' || e.key !== 'Tab') return
          const controls = [...e.currentTarget.querySelectorAll<HTMLElement>('button:not(:disabled), a[href], summary, [tabindex="0"]')].filter((el) => el.getClientRects().length)
          const first = controls[0], last = controls.at(-1)
          if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last?.focus() }
          else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first?.focus() }
        }}>
        <Magnet resource={r} onExpand={() => p.expand(r)} onCollapse={() => p.collapse(r)} onClose={() => p.close(r)} onOrigin={() => p.origin(r)}
          onPost={(result) => p.post(r, result)} onFile={(result) => p.file(r, result)}
          onSource={() => { const s = r.saved.config?.sources[0]; if (s?.kind === 'conversation') p.conversationTo(r, s.conversation) }}
          onConversation={() => { const c = r.saved.config?.conversation; if (c) p.conversationTo(r, c); else p.notice('Magnet conversation is unavailable; this preview does not create or repair it.') }} />
      </div>
    })}
    {chooser && <div className="q2-choose-veil" onKeyDown={(e) => { if (e.key === 'Escape') { request.current?.abort(); setChooser(false) } }}>
      <div className="q2-choose" role="dialog" aria-modal="true" aria-label="Open existing Magnet">
        <h2>Open existing Magnet</h2><p role="status">{words}</p>
        {rows.map((r) => <button key={r.id} className="q2-choose-opt" disabled={!!r.reason || !r.config} onClick={() => open(r)}><span>{r.name}</span><span className="q2v-menu-sub">{r.reason ?? r.id}</span></button>)}
        <button autoFocus className="q2-link-quiet" onClick={() => { request.current?.abort(); setChooser(false) }}>Close</button>
      </div>
    </div>}
  </>
}
