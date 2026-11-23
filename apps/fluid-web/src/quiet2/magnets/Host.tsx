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
import CollectionConfiguration from './CollectionConfiguration'
import Perspectives from './InquiryPanel'
import EvidenceViews from './EvidenceViews'
import Summary from './Summary'
import SettingsView from './SettingsView'
import SearchView from './SearchView'
import { inspect, setOpen } from './places'
import { useMagnetWrites } from './capabilities'
import MiniConversation from './MiniConversation'
import { listMagnets } from './managementApi'
import { loadWorking, openedMagnets, saveOpenedMagnets } from './workingState'
import { confirmBrain } from '../../brainBinding'
import { READ_ONLY } from '../live'

const get: MagnetGet = async (path, signal) => {
  const r = await fetch(path, { headers: CLIENT_HEADERS, signal, cache: 'no-store' })
  return { status: r.status, body: await r.json().catch(() => null) }
}
export const findMagnet = (id: string) => resourceById<QuietMagnetResource>('magnet', id)
export const focusMagnetManagement = () => [...document.querySelectorAll<HTMLElement>('[data-open-magnet]')].find((el) => el.getClientRects().length)?.focus({ preventScroll: true })
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
  const previousBrain = useRef(p.brainKey)
  const restored = useRef<string | null>(null)
  const restoring = useRef(false)
  const current = useRef(p); current.current = p
  useEffect(() => {
    const previous = previousBrain.current
    previousBrain.current = p.brainKey
    if (previous && previous !== p.brainKey) setChooser(false)
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
      existing.saved.config = saved.config
      existing.saved.name = saved.name
      existing.saved.reason = saved.reason
      const v = [...viewers.values()].find((v) => v.content.kind === 'magnet' && v.content.resourceId === existing.id)
      if (v) { if (v.place === 'parked') returnViewer(v.id, 'canvas', null); else moveViewer(v.id, 'canvas') }
      existing.update({ title: saved.name })
      setOpen(existing, true)
      void existing.read()
      setChooser(false)
      requestAnimationFrame(() => document.querySelector<HTMLElement>(`[data-magnet-resource="${existing.id}"] button`)?.focus({ preventScroll: true }))
      return
    }
    const captured = origin.current ?? p.capture()
    const r = registerResource('magnet', Object.assign(createMagnetResource({ id: nextResourceId(), brainKey: p.brainKey, saved, get }), { origin: captured }))
    const n = resourcesOfBrain('magnet', p.brainKey).length
    // Resource state has already recovered this Magnet's device placement.
    if (!Object.keys(loadWorking(p.brainKey, saved.id)).length) r.update({ x: 24 + (n - 1) * 112, y: 24 })
    openViewer({ kind: 'magnet', resourceId: r.id, magnetId: saved.id, brainKey: r.brainKey }, { kind: 'brain', brainKey: r.brainKey }, 'canvas')
    setChooser(false)
  }
  useEffect(() => {
    if (!p.brainKey || restored.current === p.brainKey) return
    const key = p.brainKey, ctl = new AbortController()
    restoring.current = true
    void (async () => {
      if (await confirmBrain() !== true || ctl.signal.aborted || current.current.brainKey !== key) return
      const ids = openedMagnets(key)
      if (ids.length) {
        const rows = await listMagnets(ctl.signal)
        if (ctl.signal.aborted || current.current.brainKey !== key) return
        for (const id of ids) { const saved = rows.find((r) => r.id === id); if (saved && !saved.reason) open(saved) }
      }
      restored.current = key
    })().catch(() => { /* A failed restore never substitutes a different Magnet. Management can retry. */ }).finally(() => { if (!ctl.signal.aborted) restoring.current = false })
    return () => ctl.abort()
  }, [p.brainKey])
  useEffect(() => {
    if (!p.brainKey || restoring.current || restored.current !== p.brainKey) return
    saveOpenedMagnets(p.brainKey, resourcesOfBrain<QuietMagnetResource>('magnet', p.brainKey).map((r) => r.saved.id))
  }, [p.brainKey, viewers.size, sessionsVersion()])
  return <>
    {writes.fixture && <p className="q2-magnet-fixture-scope" role="status">Disposable fixture · main Conversation read-only · mini messages and Magnet creation enabled</p>}
    {p.brainKey && [...viewers.values()].filter((v) => v.content.kind === 'magnet' && v.content.brainKey === p.brainKey && (v.place === 'canvas' || v.place === 'max')).map((v) => {
      if (v.content.kind !== 'magnet') return null
      const r = findMagnet(v.content.resourceId)
      if (!r) { queueMicrotask(() => closeViewer(v.id)); return null }
      const max = [...viewers.values()].some((o) => o.place === 'max' && o.id !== v.id)
      const own = r.saved.config?.conversation
      const hasOwn = typeof own === 'string' && /^ent-[a-z0-9]{6,40}$/i.test(own)
      const toSource = () => { const s = r.saved.config?.sources[0]; if (s?.kind === 'conversation') p.conversationTo(r, s.conversation) }
      const toOwn = () => { const c = r.saved.config?.conversation; if (c) p.conversationTo(r, c); else { r.update({ tab: 'Conversation', overlay: null }); setOpen(r, true) } }
      const evidence = (ref: string) => inspect(r, ref)
      // Components are supplied into the frame's slots; nothing edits the frame.
      return <div className="q2-magnet-canvas" key={v.id} hidden={max} data-magnet-resource={r.id}>
        <Magnet resource={r} canCollect={!READ_ONLY && writes.arrangement('home')} onExpand={() => p.expand(r)} onCollapse={() => p.collapse(r)}
          views={{
            Summary: <Summary resource={r} onPost={(result) => p.post(r, result)} />,
            All: <EvidenceViews resource={r} lens="All" onPost={(result) => p.post(r, result)} onFile={(result) => p.file(r, result)} />,
            Posts: <EvidenceViews resource={r} lens="Posts" onPost={(result) => p.post(r, result)} onFile={(result) => p.file(r, result)} />,
            Files: <EvidenceViews resource={r} lens="Files" onPost={(result) => p.post(r, result)} onFile={(result) => p.file(r, result)} />,
            Perspectives: <Perspectives resource={r} canWrite={writes.conversation(r.saved.config?.conversation)} onEvidence={evidence} />,
            Conversation: <MiniConversation resource={r} canWrite={writes.conversation(r.saved.config?.conversation)} onEvidence={evidence} onFull={toOwn} />,
            search: <SearchView resource={r} />,
            settings: <SettingsView resource={r} hasOwnConversation={hasOwn} canReset
              collectionConfiguration={r.saved.config && <CollectionConfiguration magnet={r.saved.id} config={r.saved.config} brainKey={r.brainKey} canWrite={writes.arrangement} onSaved={(config) => { r.saved.config = config; r.saved.reason = undefined; r.update({}); void r.read() }} />}
              onReset={() => r.update({ x: 12, y: 12 })} onRemove={() => p.close(r)}
              onSource={toSource} onConversation={toOwn} onOrigin={() => p.origin(r)} />,
          }} />
      </div>
    })}
    <Management open={chooser} brainKey={p.brainKey} conversation={p.conversation} canCreate={writes.arrangement} fixture={writes.fixture}
      onOpen={open} onClose={() => { setChooser(false); requestAnimationFrame(focusMagnetManagement) }} />
  </>
}
