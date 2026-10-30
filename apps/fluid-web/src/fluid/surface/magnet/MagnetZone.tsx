/* A MAGNET, DRAWN (plan adm-b848fa881c8d §3.6, §3.10; part P7, stage A).
 *
 * One body for every placement a Magnet zone is in -- a window, a docked
 * section -- drawn by its level:
 *
 *   icon      the disc: its source's initial and what is unread. A tap is
 *             Expand, a double-tap Open as workspace, a hold or right-click
 *             its actions (choices.ts holds each of these open).
 *   compact,  SurfaceChrome (the one chrome; T1/T2 are the registry's list
 *   standard, for this Magnet's target) over its tabs: the ordered
 *   expanded  intersection of what it selects and what its sources can do,
 *             with Search where a source searches (P8's, through the
 *             conversation adapter). Standard and expanded use the same
 *             list in more room in this stage.
 *
 * Everything that moves it is an ordinary surface verb on its own zone id,
 * through workspace.apply; its tab, query and scroll are view state keyed by
 * (its id, itself), so they survive docking, floating and collapsing. A zone
 * whose config is missing draws the reason and fetches nothing. */

import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import * as nav from '../../nav'
import { ago } from '../../../api'
import { usePost, useCollection } from '../../conversation/hooks'
import { excerpt } from '../../conversation/text'
import { unreadSince } from '../../focus/model'
import type { FloatingZoneHead } from '../../focus/FloatingHeader'
import { act } from '../../objects/actions'
import { store, type Hit } from '../../store'
import { useArr, workspace } from '../../workspace/place'
import type { ZoneCtl } from '../../workspace/TreeView'
import type { Rect, Zone } from '../../workspace/tree'
import { Sheet } from '../../frame/Sheet'
import { LegacySurfaceChromeBar, chromeCtx } from '../SurfaceChrome'
import { ActionMenu } from '../actions/ActionMenu'
import { registry } from '../actions/registry'
import { installProviders } from '../actions/providers'
import type { ActionTarget } from '../actions/types'
import { APART_WORD, T2_APART, pressOf } from '../chrome'
import { usePresentationClass as useClassNow, useInputMode } from '../../frame/narrow'
import { stateIn } from '../transition'
import { useViewState } from '../viewState'
import type { Level, PlacementKind } from '../types'
import type { MagnetConfig, MagnetResult } from './types'
import { MAGNET_CHOICES } from './choices'
import { BUILD_ENV, MAGNET_CONFIG_GONE, conversationOf, initialOf, magnetIdOf, notRunning, tabsOf, type TabId } from './model'
import { magnetView, useClosedHere, useRevealed } from './client'
import { adapters } from './runtime'
import { markSeen, seenAt, useMagnet, useMagnetSearch } from './useMagnet'
import type { ObjectRow } from './conversation'
import './magnet.css'

export function MagnetZone({ z, ctl, page, floating }: { z: Zone; r: Rect; ctl: ZoneCtl; page: string; first: boolean; floating?: FloatingZoneHead }) {
  installProviders()
  const arr = useArr()
  const closed = useClosedHere()
  const cls = useClassNow()
  const input = useInputMode()
  const id = magnetIdOf(z) ?? z.id
  const config = arr.magnets?.[id]
  const surfaceCtx = workspace.surfaceCtx({ page })
  const s = stateIn(surfaceCtx, z.id)
  const level: Level = s ? (s.level.override ?? s.level.auto) : 'standard'
  const at: PlacementKind = s?.placement.kind === 'dock' || s?.placement.kind === 'float' || s?.placement.kind === 'stack' || s?.placement.kind === 'sheet'
    ? s.placement.kind : floating ? 'float' : 'dock'
  const ctx = useMemo(() => chromeCtx(cls, input), [cls, input])
  const target: ActionTarget = useMemo(() => ({
    resource: { address: 'magnet:' + id, kind: 'magnet' },
    ...(s ? { surface: { id: z.id, state: s, caps: surfaceCtx.caps(z.id) } } : {}),
  }), [id, z.id, arr, cls, page, closed])
  const revealed = useRevealed(z.id)
  const title = config ? store.conversations.get(conversationOf(config) ?? '')?.name ?? z.name ?? 'Magnet' : z.name ?? 'Magnet'
  const dragFrom = floating?.props?.onPointerDown
  const grip = dragFrom ? { onPointerDown: (e: React.PointerEvent) => dragFrom(e as React.PointerEvent<HTMLDivElement>) }
    : ctl.drag ? { onPointerDown: (e: React.PointerEvent) => ctl.drag!(e as React.PointerEvent<HTMLElement>) } : undefined

  if (s && !s.open) {
    return <section className="mg-zone mg-closed" aria-label={`${title} magnet, closed here`}>
      <span>{title} is closed on this device.</span>
      <button type="button" className="fl-btn" onClick={() => void registry.run('reopen', target, ctx)}>Reopen</button>
    </section>
  }
  if (level === 'icon') {
    return <section className={'mg-zone mg-at-icon' + (revealed ? ' mg-revealed' : '')} data-magnet={id} aria-label={`${title} magnet`}>
      {config ? <Disc id={id} config={config} title={title} target={target} ctx={ctx} />
        : <button type="button" className="mg-disc mg-disc-missing" title={MAGNET_CONFIG_GONE}
          onClick={() => void registry.run('expand', target, ctx).catch(() => {})}>?</button>}
    </section>
  }
  return <section className={'mg-zone mg-pane' + (revealed ? ' mg-revealed' : '')} data-magnet={id} data-level={level} aria-label={`${title} magnet`}>
    <div className="mg-chrome">
      <LegacySurfaceChromeBar target={target} placement={at} level={level} grip={grip}
        title={<span className="mg-title"><span className="mg-mini" aria-hidden="true">{initialOf(title)}</span>{title}</span>} />
    </div>
    {config ? <Pane id={id} config={config} level={level} /> : <Missing />}
  </section>
}

/* -- the disc ------------------------------------------------------------------ */

function Disc({ id, config, title, target, ctx }: { id: string; config: MagnetConfig; title: string; target: ActionTarget; ctx: ReturnType<typeof chromeCtx> }) {
  const conversation = conversationOf(config)
  const coll = useCollection('conversation:' + (conversation ?? ''))
  useEffect(() => { if (conversation && !store.collections.has('conversation:' + conversation)) void store.loadConversation(conversation).catch(() => {}) }, [conversation])
  useEffect(() => { if (conversation && !store.conversations.has(conversation)) void store.loadConversations([conversation]).catch(() => {}) }, [conversation])
  const since = seenAt(id as `mag-${string}`)
  const unread = coll ? unreadSince(coll.items.flatMap((p) => store.posts.get(p.id) ?? []), since) : 0
  const [menu, setMenu] = useState<HTMLElement | null>(null)
  const el = useRef<HTMLButtonElement | null>(null)
  const click = useRef<ReturnType<typeof setTimeout> | null>(null)
  const run = (verb: 'expand' | 'openAsWorkspace') => void registry.run(verb, target, ctx).catch((e: Error) => nav.toast({ text: e.message }))
  const tap = () => {
    if (click.current) return
    click.current = setTimeout(() => { click.current = null; run(MAGNET_CHOICES.discTap === 'expand' ? 'expand' : 'openAsWorkspace') }, 230)
  }
  const doubleTap = () => {
    if (click.current) { clearTimeout(click.current); click.current = null }
    if (MAGNET_CHOICES.discDoubleTap === 'openAsWorkspace') run('openAsWorkspace')
  }
  /* a hold opens its actions, as on every surface (chrome.ts pressOf) */
  const held = useRef(false)
  const down = (e: React.PointerEvent) => {
    held.current = false
    const p = pressOf('body', e.pointerType, { x: e.clientX, y: e.clientY }, { menu: () => { held.current = true; setMenu(el.current) }, drag: () => {} })
    if (!p.pending) return
    const move = (m: PointerEvent) => p.move(m.clientX, m.clientY)
    const up = () => { p.up(); window.removeEventListener('pointermove', move); window.removeEventListener('pointerup', up); window.removeEventListener('pointercancel', up) }
    window.addEventListener('pointermove', move); window.addEventListener('pointerup', up); window.addEventListener('pointercancel', up)
  }
  const says = `${title}${unread ? ` · ${unread} new` : ''}. ${MAGNET_CHOICES.discTap === 'expand' ? 'Tap to open it out' : 'Tap to open'}; double-tap opens the conversation; hold or right-click for its actions.`
  return <>
    <button ref={el} type="button" className="mg-disc" data-renderer={config.presentation.renderer} title={says} aria-label={says}
      onPointerDown={down}
      onClick={() => { if (held.current) { held.current = false; return } tap() }}
      onDoubleClick={doubleTap}
      onContextMenu={(e) => { e.preventDefault(); setMenu(e.currentTarget) }}>
      <span className="mg-initial">{initialOf(title)}</span>
      {unread > 0 && <span className="mg-unread" aria-hidden="true">{unread > 99 ? '99+' : unread}</span>}
    </button>
    {menu && <Sheet anchor={menu} onClose={() => setMenu(null)} label={`${title}: actions`} className="sc-pop">
      <ActionMenu target={target} ctx={ctx} label={`${title}: actions`} onDone={() => setMenu(null)} apart={T2_APART} apartWord={APART_WORD} />
    </Sheet>}
  </>
}

/* -- the pane: tabs, results, search ------------------------------------------- */

function Pane({ id, config, level }: { id: string; config: MagnetConfig; level: Level }) {
  const live = useMagnet(config)
  const tabs = tabsOf(config, BUILD_ENV, adapters)
  const view = magnetView(id)
  const [tab, setTab] = useViewState<TabId>(view, 'tab', tabs[0]?.id ?? 'post')
  const [q, setQ] = useViewState<string>(view, 'q', '')
  const shown = tabs.find((t) => t.id === tab) ? tab : tabs[0]?.id
  /* opened past its disc: what is here now is seen */
  useEffect(() => { markSeen(id as `mag-${string}`) }, [id, level, live.results.length])
  /* scroll, per tab, kept with the Magnet */
  const body = useRef<HTMLDivElement | null>(null)
  const [scroll, setScroll] = useViewState<Record<string, number>>(view, 'scroll', {})
  useLayoutEffect(() => {
    const el = body.current
    if (el && shown) el.scrollTop = scroll[shown] ?? 0
  }, [shown, live.loading])
  const frame = useRef(0)
  const onScroll = () => {
    cancelAnimationFrame(frame.current)
    frame.current = requestAnimationFrame(() => { const el = body.current; if (el && shown) setScroll((s) => ({ ...s, [shown]: el.scrollTop })) })
  }
  const off = notRunning(config, BUILD_ENV, adapters)
  const conversation = conversationOf(config)
  return <>
    <div className="mg-tabs" role="tablist" aria-label="What it shows">
      {tabs.map((t) => {
        const why = t.availability.state === 'disabled' ? t.availability.reason.message : undefined
        return <button key={t.id} type="button" role="tab" className={'mg-tab' + (t.id === shown ? ' on' : '')} aria-selected={t.id === shown}
          aria-disabled={why ? true : undefined} title={why ?? t.label} onClick={() => { if (!why) setTab(t.id) }}>
          {t.label}</button>
      })}
    </div>
    {shown === 'search' && <div className="mg-search">
      <input type="search" value={q} placeholder={`Search in ${store.conversations.get(conversation ?? '')?.name ?? 'this magnet'}`} aria-label="Search in this magnet"
        onChange={(e) => setQ(e.target.value)} autoFocus />
    </div>}
    <div className="mg-body" ref={body} onScroll={onScroll}>
      {live.error ? <p className="mg-quiet">{live.error}</p>
        : shown === 'search' ? <SearchResults config={config} q={q} />
        : <Results results={live.results.filter((r) => r.kind === shown)} loading={live.loading} tab={shown ?? 'post'} />}
    </div>
    {off.length > 0 && <ul className="mg-off" aria-label="Kept but not running here">
      {off.map((o, i) => <li key={i} title={o.reason.message}><b>{o.facet}</b> {o.reason.message}</li>)}
    </ul>}
  </>
}

function Results({ results, loading, tab }: { results: MagnetResult[]; loading: boolean; tab: TabId }) {
  if (!results.length) return <p className="mg-quiet">{loading ? 'Reading…' : tab === 'post' ? 'No posts yet.' : `No ${tab === 'image' ? 'images' : 'files'} here.`}</p>
  return <ul className="mg-list">
    {results.map((r) => r.kind === 'post'
      ? <PostRow key={r.id} id={r.id} conversation={(r.source as { conversation?: string }).conversation ?? null} />
      : <ObjectItem key={r.id} row={r.value as ObjectRow} kind={r.kind} />)}
  </ul>
}

/** A post, read-only; selecting it reads it in its own conversation's place. */
function PostRow({ id, conversation }: { id: string; conversation: string | null }) {
  const p = usePost(id)
  if (!p) return null
  const home = conversation ?? p.home
  return <li>
    <button type="button" className="mg-row" title="Read it in its conversation"
      onClick={() => { if (home) nav.read(home, p.id, p.number ?? null) }}>
      <span className="mg-meta">{p.number != null ? `#${p.number} · ` : ''}{p.author_name} · {ago(p.at)}</span>
      <span className="mg-text">{p.deleted ? 'Deleted' : excerpt(p, 220)}</span>
    </button>
  </li>
}

function ObjectItem({ row, kind }: { row: ObjectRow; kind: string }) {
  const target = { address: row.address, title: row.title ?? row.kind, kind: row.kind, from: `from #${row.number ?? '?'}` }
  return <li>
    <button type="button" className="mg-row" data-kind={kind} title={`Open ${row.title ?? row.kind}`}
      onClick={(e) => act.open({ ...target, anchor: e.currentTarget })}>
      <span className="mg-meta">{kind === 'image' ? '▧' : '▤'} from #{row.number ?? '?'}</span>
      <span className="mg-text">{row.title ?? row.kind}</span>
    </button>
  </li>
}

function SearchResults({ config, q }: { config: MagnetConfig; q: string }) {
  const got = useMagnetSearch(config, q)
  if (!q.trim()) return <p className="mg-quiet">Search only this conversation.</p>
  if (got.error) return <p className="mg-quiet">{got.error}</p>
  if (!got.results.length) return <p className="mg-quiet">{got.searching ? 'Searching…' : 'Nothing found here.'}</p>
  return <ul className="mg-list">
    {got.results.map((r) => {
      const h = r.value as Hit
      const home = (r.source as { conversation?: string }).conversation
      return <li key={r.id}>
        <button type="button" className="mg-row" title="Read it in its conversation" onClick={() => { if (home) nav.read(home, h.post, h.number ?? null) }}>
          <span className="mg-meta">{h.number != null ? `#${h.number} · ` : ''}{ago(h.at)}</span>
          <span className="mg-text">{h.snippet}</span>
        </button>
      </li>
    })}
  </ul>
}

function Missing() {
  return <div className="mg-body"><p className="mg-quiet"><b>Magnet configuration unavailable.</b> {MAGNET_CONFIG_GONE} Nothing is read for it; Remove from workspace is in its actions.</p></div>
}
