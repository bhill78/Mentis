/* A MAGNET, DRAWN (plan adm-b848fa881c8d §3.6, §3.10; part P7, stage A;
 * magnet polish, owner Turn #1592).
 *
 * One frame (SurfaceChrome, on one target: this Magnet's) for every placement
 * a Magnet zone is in -- a window, a docked section -- its body drawn by its
 * level (surface composition package 4, plan ent-2d8422d49d7c):
 *
 *   icon      a HIDDEN frame whose body is the disc (bodyIsControl). The disc
 *             is meant to be seen on any background: an opaque face with its
 *             initial, a halo in the canvas's colour, its source's badge, its
 *             status badge, its unread count, its name beneath it, and its
 *             orbit (Orbit.tsx): what it holds and how it is. A tap is
 *             Expand, a double-tap Open as workspace (choices.ts holds each of
 *             these open); a hold or right-click is the frame's, and opens its
 *             one T2, as does its ⋯ (revealed on hover or focus, a trigger on
 *             touch). A press that MOVES is a move of its window, and only
 *             that (drag.ts moveFloatFrom). A mouse resting on it shows its
 *             quick summary card (Summary.tsx), as Peek does from T2.
 *   compact,  a full frame (T1/T2 are the registry's list for this Magnet's
 *   standard, target) around its tabs: the ordered intersection of what it
 *   expanded  selects and what its sources can do, with Search where a
 *             source searches (P8's, through the conversation adapter); then
 *             its Summary and its configuration (Editor.tsx). Its items are
 *             drawn as its renderer asks: a list, cards or a gallery.
 *   compact,  opened from its disc in a window: the SLIDE-OUT (owner Turn
 *   a window  #1617): the disc stays where it was, drawn beside the frame,
 *             and the same frame opens out of its centre as an opaque panel,
 *             headed by its title and what was new, its summary's lead above
 *             the same tabs. × (or the disc, or Esc) folds it back; its
 *             corner and its size control resize it, within bounds, as its
 *             window (choices.ts slide).
 *
 * Everything that moves it is an ordinary surface verb on its own zone id,
 * through workspace.apply; its tab, query, scroll and panel are view state
 * keyed by (its id, itself), so they survive docking, floating and
 * collapsing. A zone whose config is missing draws the reason and fetches
 * nothing. */

import { useEffect, useLayoutEffect, useMemo, useRef } from 'react'
import * as nav from '../../nav'
import { ago } from '../../../api'
import { usePost, useCollection } from '../../conversation/hooks'
import { excerpt } from '../../conversation/text'
import { lookOf, unreadSince } from '../../focus/model'
import type { FloatingZoneHead } from '../../focus/FloatingHeader'
import { act } from '../../objects/actions'
import { store, type Hit } from '../../store'
import { useArr, workspace } from '../../workspace/place'
import type { ZoneCtl } from '../../workspace/TreeView'
import type { Rect, Zone } from '../../workspace/tree'
import { SurfaceChrome, chromeCtx, swallowNextClick, t2Opener } from '../SurfaceChrome'
import { LookSheet } from '../LookSheet'
import { registry } from '../actions/registry'
import { installProviders } from '../actions/providers'
import type { ActionCtx, ActionTarget } from '../actions/types'
import { usePresentationClass as useClassNow, useInputMode } from '../../frame/narrow'
import { stateIn } from '../transition'
import { useViewState } from '../viewState'
import type { Level, PlacementKind } from '../types'
import type { MagnetConfig, MagnetId, MagnetResult } from './types'
import { MAGNET_CHOICES } from './choices'
import {
  BUILD_ENV, MAGNET_CONFIG_GONE, SOURCE_WORD, conversationOf, glyphOf, holdingOf, holdingWords, initialOf, magnetIdOf, magnetStatus,
  magnetLook, notRunning, slideEnlarged, tabsOf, type TabId,
} from './model'
import { closePeek, magnetView, openPeek, useClosedHere, usePeeked, useRevealed } from './client'
import { adapters } from './runtime'
import { markSeen, seenAt, useMagnet, useMagnetSearch } from './useMagnet'
import { pictureOf, type ObjectRow } from './conversation'
import { Icon, stateIcon } from './icons'
import { Orbit } from './Orbit'
import { SummaryBody, SummaryCard, SummaryLead } from './Summary'
import { Editor } from './Editor'
import './magnet.css'

type Panel = 'results' | 'summary' | 'configure'

export function MagnetZone({ z, r, ctl, page, floating }: { z: Zone; r: Rect; ctl: ZoneCtl; page: string; first: boolean; floating?: FloatingZoneHead }) {
  installProviders()
  const arr = useArr()
  const closed = useClosedHere()
  const cls = useClassNow()
  const input = useInputMode()
  const id = magnetIdOf(z) ?? (z.id as MagnetId)
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
  const peeked = usePeeked(id)
  const title = config ? store.conversations.get(conversationOf(config) ?? '')?.name ?? z.name ?? 'Magnet' : z.name ?? 'Magnet'
  const dragFrom = floating?.props?.onPointerDown
  const grip = dragFrom ? { onPointerDown: (e: React.PointerEvent) => dragFrom(e as React.PointerEvent<HTMLDivElement>) }
    : ctl.drag ? { onPointerDown: (e: React.PointerEvent) => ctl.drag!(e as React.PointerEvent<HTMLElement>) } : undefined
  /* OPENED FROM ITS DISC IN A WINDOW (compact): the slide-out (owner Turn
     #1617) -- the disc where it was, and out of its centre the same one
     frame as an opaque panel, sized by its window and resizable within
     bounds. Docked, in the stack or a sheet, and at standard or expanded, it
     is the pane in its frame, as before. */
  const slide = !!config && level === 'compact' && at === 'float'
  const opened = useOpenedAt(id, slide)
  /* ITS LOOK (amendment ent-56d18f7b54a5): the shared Appearance, not a
     Magnet's own setting -- its own kept in its zone's options as a thread
     window keeps its (focus/model.ts lookOf, setThreadLook), the slide-out
     opaque until it has one (magnetLook). Look in its actions (⚙, right-click
     or hold) opens the same Look column a section's and a window's ⚙ does. */
  const own = lookOf(z)
  const appearance = magnetLook(own, arr.appearance, slide)
  const [lookOpen, setLookOpen] = useViewState<boolean>(magnetView(id), 'look', false)
  const zoneEl = useRef<HTMLElement | null>(null)

  if (s && !s.open) {
    return <section className="mg-zone mg-closed" aria-label={`${title} magnet, closed here`}>
      <span>{title} is closed on this device.</span>
      <button type="button" className="fl-btn" onClick={() => void registry.run('reopen', target, ctx)}>Reopen</button>
    </section>
  }
  /* ONE FRAME at every level, on the one target: the icon is a hidden frame
     whose body is the disc (its own button, so a hold or right-click on it is
     the frame's T2, and only that); compact, standard and expanded a full
     frame whose body is the pane. Same element in both, so a level change
     moves the frame, never swaps it for another chrome. */
  const icon = level === 'icon'
  /* the disc moves freely only as a window; in a section or the stack it is placed by those */
  const move = at === 'float' ? floating?.move : undefined
  const body = icon
    ? config ? <Disc id={id} config={config} title={title} target={target} ctx={ctx} move={move} raise={floating?.raise} />
      : <button type="button" className="mg-disc mg-disc-missing" title={MAGNET_CONFIG_GONE} aria-label={`${title}: ${MAGNET_CONFIG_GONE}`}
        onClick={() => void registry.run('expand', target, ctx).catch(() => {})}>?</button>
    : config ? <Pane id={id} config={config} level={level} title={title} target={target} ctx={ctx} opened={opened} /> : <Missing />
  /* the slide-out folds back to its disc: by ×, a tap on the disc, or Esc
     within it (not in a field); the disc then has the focus */
  const fold = () => {
    void registry.run('collapse', target, ctx).then(() => requestAnimationFrame(() =>
      document.querySelector<HTMLElement>(`.mg-zone[data-magnet="${CSS.escape(id)}"] .mg-disc`)?.focus()),
    (e: Error) => nav.toast({ text: e.message }))
  }
  const escFold = (e: React.KeyboardEvent) => {
    if (e.key !== 'Escape' || e.defaultPrevented || (e.target as Element).closest('input, textarea, select, [contenteditable="true"]')) return
    e.preventDefault(); e.stopPropagation(); fold()
  }
  /* a solid panel is laid on the canvas as strongly as its opacity says, so
     at full opacity it is opaque in every atmosphere (the raised surface
     token is itself a little translucent) */
  const k = Math.round(appearance.opacity * 100)
  const under = slide ? { '--mg-under': appearance.panel !== 'solid' ? 'transparent' : k >= 100 ? 'var(--canvas)' : `color-mix(in srgb, var(--canvas) ${k}%, transparent)` } as React.CSSProperties : undefined
  return <section ref={zoneEl} className={'mg-zone ' + (icon ? 'mg-at-icon' : slide ? 'mg-pane mg-slide' : 'mg-pane') + (revealed ? ' mg-revealed' : '')} data-magnet={id} data-level={level} aria-label={`${title} magnet`}
    style={under} onKeyDown={slide ? escFold : undefined}>
    {/* in the slide-out no grip: the disc is its handle (moves it, never docks it); Dock is in its actions */}
    <SurfaceChrome target={target} placement={at} level={level} label={title} className={'mg-frame' + (slide ? ' mg-slide-panel' : '')}
      visibility={icon ? 'hidden' : 'full'} bodyIsControl={icon} grip={slide ? undefined : grip}
      title={slide ? <SlideHead id={id} config={config!} title={title} opened={opened!} />
        : <span className="mg-title"><span className="mg-mini" aria-hidden="true">{initialOf(title)}</span>{title}</span>}
      {...(slide ? {
        dismiss: { label: `Close ${title}: back to its disc`, title: 'Close: back to its disc (Esc). Close here and Remove are in its actions (⚙)', run: fold },
        ...(floating?.resize ? { header: { content: <SizeControl title={title} size={{ w: r.w, h: r.h }} resize={floating.resize} /> } } : {}),
      } : {})}
      body={body} />
    {icon && config && peeked && at === 'float' && <Peeked id={id} config={config} title={title} how={peeked} target={target} ctx={ctx} />}
    {slide && <Disc id={id} config={config!} title={title} target={target} ctx={ctx} move={move} raise={floating?.raise} opened={fold} />}
    {/* Look, from its T2: the shared Look column; back to its default is, as the slide-out, opaque */}
    {lookOpen && at === 'float' && !icon && <LookSheet zone={z.id} page={page} name={title} appearance={appearance} own={!!own}
      anchor={t2Opener(zoneEl.current?.querySelector('.mg-frame') ?? zoneEl.current)} onClose={() => setLookOpen(false)}
      {...(slide ? { resetLabel: ['Back to its opaque look', 'Opaque'] as [string, string], resetWords: `${title} is opaque again.` } : {})} />}
  </section>
}

/** When the slide-out now open was opened: what was seen before then, kept
 *  while it stays open (opening it marks it seen), forgotten when it folds. */
function useOpenedAt(id: MagnetId, open: boolean): number | undefined {
  const at = useRef<number | null>(null)
  if (!open) at.current = null
  else if (at.current == null) at.current = seenAt(id)
  return at.current ?? undefined
}

/* -- what a Magnet is now: its results, what is new, how it is ----------------------- */

/** `opened`: count what is new from then (a slide-out's, from before it was
 *  opened), not from when it was last seen (now, once it is open). */
function useNow(id: MagnetId, config: MagnetConfig, opened?: number) {
  const live = useMagnet(config)
  const conversation = conversationOf(config)
  const coll = useCollection('conversation:' + (conversation ?? ''))
  useEffect(() => { if (conversation && !store.collections.has('conversation:' + conversation)) void store.loadConversation(conversation).catch(() => {}) }, [conversation])
  useEffect(() => { if (conversation && !store.conversations.has(conversation)) void store.loadConversations([conversation]).catch(() => {}) }, [conversation])
  const since = opened ?? seenAt(id)
  const unread = coll ? unreadSince(coll.items.flatMap((p) => store.posts.get(p.id) ?? []), since) : 0
  const off = notRunning(config, BUILD_ENV, adapters).length
  const status = magnetStatus(config, { unread, loading: live.loading, held: live.results.length, error: live.error, off })
  const totals = live.summaries.map((x) => x.summary)
  const holding = holdingOf(live.results, totals.some((x) => x.posts != null) ? totals.reduce((n, x) => n + (x.posts ?? 0), 0) : undefined)
  return { live, unread, status, holding }
}

const runOn = (verb: 'expand' | 'openAsWorkspace', target: ActionTarget, ctx: ActionCtx) =>
  void registry.run(verb, target, ctx).catch((e: Error) => nav.toast({ text: e.message }))

/* -- the summary card, on a mouse's rest or Peek ----------------------------------- */

const resting = new Map<string, ReturnType<typeof setTimeout>>()
/* a disc just moved shows no card until the pointer has left it: while it
   follows the pointer it is left and entered again, which is not a rest */
const moved = new Set<string>()
const stay = (id: string) => { const t = resting.get(id); if (t) clearTimeout(t); resting.delete(id) }
const restOn = (id: string, raise?: () => void) => {
  stay(id)
  if (moved.has(id)) return
  resting.set(id, setTimeout(() => { raise?.(); openPeek(id, 'hover') }, MAGNET_CHOICES.peekAfterMs))
}
const leaveFrom = (id: string) => { stay(id); resting.set(id, setTimeout(() => closePeek(id, true), 220)) }

function Peeked({ id, config, title, how, target, ctx }: { id: MagnetId; config: MagnetConfig; title: string; how: 'hover' | 'pinned'; target: ActionTarget; ctx: ActionCtx }) {
  const { live, unread, status } = useNow(id, config)
  return <SummaryCard how={how} id={id} config={config} title={title} live={live} unread={unread} status={status}
    onEnter={() => stay(id)} onLeave={() => { if (how === 'hover') leaveFrom(id) }}
    open={() => { closePeek(id); runOn('expand', target, ctx) }}
    {...(conversationOf(config) ? { workspace: () => { closePeek(id); runOn('openAsWorkspace', target, ctx) } } : {})} />
}

/* -- the slide-out: the disc, and its panel out of the disc's centre ---------------- */

/** Its head: what it is, and what was new when it was opened (counted from
 *  before, though opening it marks it seen), as the summary card's. */
function SlideHead({ id, config, title, opened }: { id: MagnetId; config: MagnetConfig; title: string; opened: number }) {
  const { status } = useNow(id, config, opened)
  return <span className="mg-slide-head"><b className="mg-slide-title">{title}</b>
    <span className="mg-sum-status" data-state={status.state}>{status.words}</span></span>
}

/** Its size by a tap, for touch and the keyboard: Enlarge into a mini
 *  workspace, or Restore its normal size; its corner drags to any size
 *  between its bounds. Either is its window's size, saved as a window's is. */
function SizeControl({ title, size, resize }: { title: string; size: { w: number; h: number }; resize: NonNullable<FloatingZoneHead['resize']> }) {
  const big = slideEnlarged(size)
  return <button type="button" className="fl-btn mg-size" aria-pressed={big}
    aria-label={big ? 'Restore its normal size' : 'Enlarge into a mini workspace'}
    title={big ? 'Restore its normal size' : 'Enlarge into a mini workspace (or drag its lower corner)'}
    onClick={() => resize(big ? MAGNET_CHOICES.slide.normal : MAGNET_CHOICES.slide.large, big ? `${title} is back to its normal size.` : `${title} is enlarged: its size control restores it.`)}>
    <Icon name={big ? 'shrink' : 'grow'} size={14} /></button>
}

/* -- the disc ------------------------------------------------------------------ */

/** The disc. `opened`: it is its slide-out's, at the panel's corner, and a
 *  tap folds the panel back (the disc toggles it); it shows no summary card,
 *  the panel being open, and hides its name, the panel's title saying it. */
function Disc({ id, config, title, target, ctx, move, raise, opened }: { id: MagnetId; config: MagnetConfig; title: string; target: ActionTarget; ctx: ReturnType<typeof chromeCtx>; move?: FloatingZoneHead['move']; raise?: () => void; opened?: () => void }) {
  const { unread, status, holding } = useNow(id, config)
  const click = useRef<ReturnType<typeof setTimeout> | null>(null)
  const run = (verb: 'expand' | 'openAsWorkspace') => runOn(verb, target, ctx)
  const tap = () => {
    if (click.current) return
    click.current = setTimeout(() => { click.current = null; if (opened) opened(); else run(MAGNET_CHOICES.discTap === 'expand' ? 'expand' : 'openAsWorkspace') }, 230)
  }
  const doubleTap = () => {
    if (click.current) { clearTimeout(click.current); click.current = null }
    if (MAGNET_CHOICES.discDoubleTap === 'openAsWorkspace') run('openAsWorkspace')
  }
  /* A hold or right-click is not the disc's: the frame's (bodyIsControl) opens
     its T2, and a hold's click is swallowed there, so a tap is only a tap. A
     press is the disc's only once it MOVES past the hold's slop: then it is a
     move of its window (startMove), never a tap, a hold or a menu. */
  const press = (e: React.PointerEvent<HTMLButtonElement>) => {
    stay(id); closePeek(id, true)
    if (move) startMove(e, move, () => { moved.add(id); if (click.current) { clearTimeout(click.current); click.current = null } })
  }
  const glyph = glyphOf(config)
  const badge = stateIcon(status.state, status.limited)
  const says = `${title}: a magnet of ${SOURCE_WORD[glyph]}. ${status.words}${status.limited ? '; it asks for some things this build keeps but does not run' : ''}. It holds ${holdingWords(holding)}. `
    + (opened ? `Open; tap to close it back to its disc; double-tap opens the conversation${move ? '; drag to move it' : ''}.`
      : `${MAGNET_CHOICES.discTap === 'expand' ? 'Tap to open it out' : 'Tap to open'}; double-tap opens the conversation; hold or right-click for its actions${move ? '; drag to move it' : ''}.`)
  return <button type="button" className="mg-disc" data-renderer={config.presentation.renderer} data-state={status.state} data-glyph={glyph}
    data-limited={status.limited || undefined} aria-label={says} aria-expanded={opened ? true : undefined}
    onClick={tap} onDoubleClick={doubleTap} onPointerDown={press}
    onPointerEnter={(e) => { if (!opened && e.pointerType === 'mouse' && !e.buttons) restOn(id, raise) }} onPointerLeave={(e) => { if (e.pointerType === 'mouse' && !e.buttons) { moved.delete(id); if (!opened) leaveFrom(id) } }}>
    <Orbit holding={holding} state={status.state} unread={unread} renderer={config.presentation.renderer} />
    <span className="mg-face" aria-hidden="true"><span className="mg-initial">{initialOf(title)}</span></span>
    <span className="mg-src" aria-hidden="true"><Icon name={glyph} size={12} /></span>
    {badge && <span className="mg-state" data-state={status.state} aria-hidden="true"><Icon name={badge} size={11} /></span>}
    {unread > 0 && <span className="mg-unread" aria-hidden="true">{unread > 99 ? '99+' : unread}</span>}
    <span className="mg-name" aria-hidden="true">{title}</span>
  </button>
}

/** Watch a press on the disc: once it moves past the slop for its pointer
 *  (choices.ts moveAfter; past the hold's on touch), it is a move of the
 *  disc's window from where it began, and the click its release would send
 *  is swallowed, so a move never also taps. */
function startMove(e: React.PointerEvent, move: NonNullable<FloatingZoneHead['move']>, cancelTap: () => void) {
  if (e.button !== 0 || !e.isPrimary) return
  const from = { x: e.clientX, y: e.clientY }, pid = e.pointerId
  const slop = e.pointerType === 'mouse' ? MAGNET_CHOICES.moveAfter.mouse : MAGNET_CHOICES.moveAfter.touch
  const stop = () => {
    window.removeEventListener('pointermove', watch)
    window.removeEventListener('pointerup', end)
    window.removeEventListener('pointercancel', end)
  }
  const end = (u: PointerEvent) => { if (u.pointerId === pid) stop() }
  const watch = (m: PointerEvent) => {
    if (m.pointerId !== pid || Math.hypot(m.clientX - from.x, m.clientY - from.y) <= slop) return
    stop()
    cancelTap()
    const released = (u: PointerEvent) => {
      if (u.pointerId !== pid) return
      window.removeEventListener('pointerup', released, true)
      swallowNextClick(window, 400)
    }
    window.addEventListener('pointerup', released, true)
    move(from)
  }
  window.addEventListener('pointermove', watch)
  window.addEventListener('pointerup', end)
  window.addEventListener('pointercancel', end)
}

/* -- the pane: tabs, results, search, summary, configuration --------------------- */

/** `opened`: the slide-out's pane (Slide), new counted from before it was
 *  opened, its summary's lead above its tabs wherever Summary is not shown. */
function Pane({ id, config, level, title, target, ctx, opened }: { id: MagnetId; config: MagnetConfig; level: Level; title: string; target: ActionTarget; ctx: ActionCtx; opened?: number }) {
  const now = useNow(id, config, opened)
  const live = now.live
  const tabs = tabsOf(config, BUILD_ENV, adapters)
  const view = magnetView(id)
  const [tab, setTab] = useViewState<TabId>(view, 'tab', tabs[0]?.id ?? 'post')
  const [q, setQ] = useViewState<string>(view, 'q', '')
  const [panel, setPanel] = useViewState<Panel>(view, 'panel', 'results')
  const [configAt] = useViewState<'all' | 'collects'>(view, 'configAt', 'all')
  const shown = tabs.find((t) => t.id === tab) ? tab : tabs[0]?.id
  /* opened past its disc: what is here now is seen */
  useEffect(() => { markSeen(id) }, [id, level, live.results.length])
  /* scroll, per tab, kept with the Magnet */
  const body = useRef<HTMLDivElement | null>(null)
  const [scroll, setScroll] = useViewState<Record<string, number>>(view, 'scroll', {})
  const key = panel === 'results' ? shown : panel
  useLayoutEffect(() => {
    const el = body.current
    if (el && key) el.scrollTop = scroll[key] ?? 0
  }, [key, live.loading])
  const frame = useRef(0)
  const onScroll = () => {
    cancelAnimationFrame(frame.current)
    frame.current = requestAnimationFrame(() => { const el = body.current; if (el && key) setScroll((s) => ({ ...s, [key]: el.scrollTop })) })
  }
  const off = notRunning(config, BUILD_ENV, adapters)
  const conversation = conversationOf(config)
  const renderer = config.presentation.renderer
  return <>
    {opened != null && panel !== 'summary' && <div className="mg-lead"><SummaryLead config={config} live={live} unread={now.unread} brief /></div>}
    <div className="mg-tabs" role="tablist" aria-label="What it shows">
      {tabs.map((t) => {
        const why = t.availability.state === 'disabled' ? t.availability.reason.message : undefined
        const on = panel === 'results' && t.id === shown
        return <button key={t.id} type="button" role="tab" className={'mg-tab' + (on ? ' on' : '')} aria-selected={on}
          aria-disabled={why ? true : undefined} title={why ?? t.label} onClick={() => { if (!why) { setTab(t.id); setPanel('results') } }}>
          {t.label}</button>
      })}
      <span className="mg-tabs-grow" />
      <button type="button" role="tab" className={'mg-tab mg-tab-icon' + (panel === 'summary' ? ' on' : '')} aria-selected={panel === 'summary'}
        title="Summary: what it is and what it holds" aria-label="Summary" onClick={() => setPanel('summary')}><Icon name="magnet" size={14} /> Summary</button>
      <button type="button" role="tab" className={'mg-tab mg-tab-icon' + (panel === 'configure' ? ' on' : '')} aria-selected={panel === 'configure'}
        title="Configure: its sources, what it collects, how it is presented" aria-label="Configure" onClick={() => setPanel('configure')}>⚙</button>
    </div>
    {panel === 'results' && shown === 'search' && <div className="mg-search">
      <input type="search" value={q} placeholder={`Search in ${store.conversations.get(conversation ?? '')?.name ?? 'this magnet'}`} aria-label="Search in this magnet"
        onChange={(e) => setQ(e.target.value)} autoFocus />
    </div>}
    <div className="mg-body" ref={body} onScroll={onScroll} data-renderer={renderer} data-panel={panel}>
      {panel === 'configure' ? <Editor id={id} config={config} at={configAt} />
        : panel === 'summary' ? <SummaryBody id={id} config={config} title={title} live={live} unread={now.unread} status={now.status}
            {...(conversation ? { workspace: () => runOn('openAsWorkspace', target, ctx) } : {})} />
        : live.error ? <p className="mg-quiet">{live.error}</p>
        : shown === 'search' ? <SearchResults config={config} q={q} />
        : <Results results={live.results.filter((r) => r.kind === shown)} loading={live.loading} tab={shown ?? 'post'} renderer={renderer} />}
    </div>
    {panel === 'results' && off.length > 0 && <ul className="mg-off" aria-label="Kept but not running here">
      {off.map((o, i) => <li key={i} title={o.reason.message}><b>{o.facet}</b> {o.reason.message}</li>)}
    </ul>}
  </>
}

function Results({ results, loading, tab, renderer }: { results: MagnetResult[]; loading: boolean; tab: TabId; renderer: string }) {
  if (!results.length) return <p className="mg-quiet">{loading ? 'Reading…' : tab === 'post' ? 'No posts yet.' : `No ${TAB_WORD[tab] ?? 'items'} here.`}</p>
  return <ul className="mg-list" data-renderer={renderer}>
    {results.map((r) => r.kind === 'post'
      ? <PostRow key={r.id} id={r.id} conversation={(r.source as { conversation?: string }).conversation ?? null} />
      : <ObjectItem key={r.id} row={r.value as ObjectRow} kind={r.kind} pictures={renderer === 'gallery' || r.kind === 'image'} />)}
  </ul>
}
const TAB_WORD: Partial<Record<TabId, string>> = { file: 'files', image: 'images or media', attachment: 'attachments', link: 'links', form: 'forms', other: 'other items' }

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

function ObjectItem({ row, kind, pictures }: { row: ObjectRow; kind: string; pictures: boolean }) {
  const target = { address: row.address, title: row.title ?? row.kind, kind: row.kind, from: `from #${row.number ?? '?'}` }
  const pic = pictures ? pictureOf(row) : null
  return <li>
    <button type="button" className="mg-row" data-kind={kind} title={`Open ${row.title ?? row.kind}`}
      onClick={(e) => act.open({ ...target, anchor: e.currentTarget })}>
      {pic && <img className="mg-pic" src={pic} alt="" loading="lazy" />}
      <span className="mg-meta"><Icon name={(kind as 'file')} size={12} /> from #{row.number ?? '?'}</span>
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
