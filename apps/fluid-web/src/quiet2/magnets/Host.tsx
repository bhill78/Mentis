import { useEffect, useRef, useState, useSyncExternalStore } from 'react'
import { CLIENT_HEADERS } from '../../api'
import { closeViewer, moveViewer, returnViewer, openViewer, useViewerLayout } from '../viewer/viewers'
import { nextResourceId, registerResource, resourceById, resourcesOfBrain, sessionsVersion, subscribeSessions } from '../space/registry'
import { createMagnetResource } from './read'
import type { MagnetGet, SavedMagnet } from './contract'
import type { MagnetOrigin, QuietMagnetResource } from './navigation'
import type { RouteResult } from '../../fluid/surface/magnet/route'
import Magnet from './Magnet'
import Management from './Management'
import { useMagnetWrites } from './capabilities'

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
  const writes = useMagnetWrites(p.brainKey)
  const origin = useRef<MagnetOrigin | null>(null)
  const requested = useRef(0)
  useEffect(() => {
    setChooser(false)
  }, [p.brainKey])
  useEffect(() => {
    if (!p.signal || p.signal === requested.current) return
    requested.current = p.signal
    origin.current = p.capture()
    setChooser(true)
  }, [p.signal, p.brainKey, p.conversation])
  const open = (saved: SavedMagnet) => {
    if (!p.brainKey || !saved.config || saved.reason) return
    const existing = resourcesOfBrain<QuietMagnetResource>('magnet', p.brainKey).find((r) => r.saved.id === saved.id)
    if (existing) {
      const v = [...viewers.values()].find((v) => v.content.kind === 'magnet' && v.content.resourceId === existing.id)
      if (v) { if (v.place === 'parked') returnViewer(v.id, 'canvas', null); else moveViewer(v.id, 'canvas') }
      existing.update({ pinned: true })
      setChooser(false)
      requestAnimationFrame(() => document.querySelector<HTMLElement>(`[data-magnet-resource="${existing.id}"] button`)?.focus())
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
      return <div className="q2-magnet-canvas" key={v.id} hidden={max} data-magnet-resource={r.id}>
        <Magnet resource={r} onExpand={() => p.expand(r)} onCollapse={() => p.collapse(r)} onClose={() => p.close(r)} onOrigin={() => p.origin(r)}
          onPost={(result) => p.post(r, result)} onFile={(result) => p.file(r, result)}
          onSource={() => { const s = r.saved.config?.sources[0]; if (s?.kind === 'conversation') p.conversationTo(r, s.conversation) }}
          onConversation={() => { const c = r.saved.config?.conversation; if (c) p.conversationTo(r, c); else p.notice('Magnet conversation is unavailable; this preview does not create or repair it.') }} />
      </div>
    })}
    <Management open={chooser} brainKey={p.brainKey} conversation={p.conversation} canCreate={writes.arrangement} fixture={writes.fixture}
      onOpen={open} onClose={() => { setChooser(false); requestAnimationFrame(() => document.querySelector<HTMLElement>('[data-open-magnet]')?.focus()) }} />
  </>
}
