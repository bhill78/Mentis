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
import SearchView, { SearchToolbar, backToResults } from './SearchView'
import Inspection, { withInspections } from './Inspection'
import { inspect, setOpen } from './places'
import { magnetWriteGate, useMagnetWrites } from './capabilities'
import MiniConversation from './MiniConversation'
import ComposerBar from './ComposerBar'
import { NO_OWN_CONVERSATION_HERE } from './conversation'
import { magnetName } from './configuration'
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
      /* WHICH WRITE THE CARD IS ASKING ABOUT -- `magnetWriteGate`. With an own
         Conversation the question is whether that one may be written into; with
         none, whether one may be made here, because the first send makes it.
         The collection is not part of either question. */
      const { mayWrite, why: noWriteWhy } = magnetWriteGate(writes, own, NO_OWN_CONVERSATION_HERE)
      const toSource = () => { const s = r.saved.config?.sources[0]; if (s?.kind === 'conversation') p.conversationTo(r, s.conversation) }
      const toOwn = () => { const c = r.saved.config?.conversation; if (c) p.conversationTo(r, c); else { r.update({ tab: 'Conversation', overlay: null }); setOpen(r, true) } }
      const evidence = (ref: string) => inspect(r, ref)
      // Components are supplied into the frame's slots; nothing edits the frame.
      // `withInspections` is what makes a citation in any tab -- Conversation and
      // Perspectives included -- render its evidence inside this card.
      return <div className="q2-magnet-canvas" key={v.id} hidden={max} data-magnet-resource={r.id}>
        <Magnet resource={r} canCollect={!READ_ONLY && writes.arrangement('home')} onExpand={() => p.expand(r)} onCollapse={() => p.collapse(r)}
          searchToolbar={<SearchToolbar resource={r} />}
          // H2's persistent composer, in the frame's footer slot: the card is
          // written in from wherever the owner is, and the frame keeps it off
          // settings. It writes through the same store the Conversation view
          // reads, so `canWrite` is the one the view is given.
          footerComposer={<ComposerBar resource={r} canWrite={mayWrite} cannotWriteBecause={noWriteWhy} />}
          views={withInspections(r, {
            Summary: <Summary resource={r} onPost={(result) => p.post(r, result)} />,
            // `canWrite` is the same `writes.arrangement` Settings' own copy of
            // this panel is given below -- one authority seam, not a second,
            // permissive one for the embedded Sources view.
            All: <EvidenceViews resource={r} lens="All" onPost={(result) => p.post(r, result)} onFile={(result) => p.file(r, result)} canWrite={writes.arrangement} />,
            Posts: <EvidenceViews resource={r} lens="Posts" onPost={(result) => p.post(r, result)} onFile={(result) => p.file(r, result)} canWrite={writes.arrangement} />,
            Files: <EvidenceViews resource={r} lens="Files" onPost={(result) => p.post(r, result)} onFile={(result) => p.file(r, result)} canWrite={writes.arrangement} />,
            Perspectives: <Perspectives resource={r} canWrite={mayWrite} onEvidence={evidence} />,
            // No external navigation is handed to the Conversation view (owner
            // §3): `toOwn` is Settings' one explicit contextual action, below,
            // and the view itself draws no way out of the card.
            Conversation: <MiniConversation resource={r} canWrite={mayWrite} onEvidence={evidence} />,
            // A retained post or file opened from the results is read in H3's own
            // inspection, inside the overlay, with the list kept behind it. Any
            // other kind is declined here and read from the index: the owning
            // views for those navigate out of the overlay themselves.
            search: <SearchView resource={r}
              detail={(target) => (target.kind === 'Posts' || target.kind === 'Files') && target.item
                ? <Inspection resource={r} refId={target.item} source={(result) => p.post(r, result)} back={() => backToResults(r)} />
                : null} />,
            // B's configuration panel goes in C's `identity` slot, not the
            // `collectionConfiguration` one: B made it open on the Magnet's own
            // name and then its sources, so it is the identity-and-sources
            // panel, and `identity` is the slot C renders first with no heading
            // of its own. Left in the other slot it would sit under C's
            // fallback name recital -- a read-only "Name" above B's editable
            // one, which is the duplicated heading and identity information the
            // request's §4 asks to be rid of.
            //
            // `onSaved` also carries the name onto the open card. The catalogue
            // is already right everywhere it is read, but the header of a card
            // that is already open is the frame's title, so a rename needs it.
            settings: <SettingsView resource={r} hasOwnConversation={hasOwn} canReset
              identity={r.saved.config && <CollectionConfiguration magnet={r.saved.id} config={r.saved.config} brainKey={r.brainKey} canWrite={writes.arrangement} onSaved={(config) => { r.saved.config = config; r.saved.name = magnetName(config, r.saved.name); r.saved.reason = undefined; r.update({ title: r.saved.name }); void r.read() }} />}
              onReset={() => r.update({ x: 12, y: 12 })} onRemove={() => p.close(r)}
              onSource={toSource} onConversation={toOwn} onOrigin={() => p.origin(r)} />,
          }, (result) => p.post(r, result))} />
      </div>
    })}
    <Management open={chooser} brainKey={p.brainKey} conversation={p.conversation} canCreate={writes.arrangement} fixture={writes.fixture}
      onOpen={open} onClose={() => { setChooser(false); requestAnimationFrame(focusMagnetManagement) }} />
  </>
}
