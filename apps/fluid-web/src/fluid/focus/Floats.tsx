import { useLayoutEffect, useRef, useState, type ReactNode } from 'react'
import { Mount } from './hosts'
import { CONVERSATION_ID, MIN_FLOAT_H, MIN_FLOAT_W, type Float } from './types'
import { armTouchDrag, beginDrag, pulseArrived } from './drag'
import { bringPrimary } from './bring'
import { minimizeConversation } from './Launcher'
import RunPanel from '../runs/RunPanel'
import * as nav from '../nav'
import { RUN_SHOW, closeFloat, dockBack, drawnFloatRect, locate, moveFloat, primaryOf, tidyFloats, toFront, updateFloatSlot } from './model'
import type { Rect } from '../workspace/tree'
import { workspace } from '../workspace/place'
import { store } from '../store'
import { onPage, pageView, useShownView } from './page'
import { WorkspaceZone, type FloatingZoneHead } from '../workspace/Zones'
import type { ZoneCtl } from '../workspace/TreeView'
import { Opt, Sheet } from '../frame/Sheet'
import { DEFAULT_APPEARANCE, readAppearance, zoneAppearanceStyle } from '../present'
import { useScheme } from '../frame/look'
import { FocusSplit } from './FocusSplit'
import { adoptTidied, focusSurface, useLens } from './lensImpl'
import { compose, shapeOf, type Rect as LensRect } from './compose'
import './floats.css'

const ctl: ZoneCtl = { stacked: false, across: false, canSplitRow: false, canSplitCol: false,
  whyNoSplitRow: 'Floating surfaces must be docked before they can be split', whyNoSplitCol: 'Floating surfaces must be docked before they can be split',
  canMerge: false, canClose: true, split: () => {}, merge: () => {}, close: () => {}, closing: false, widen: () => false, docked: false, fit: false, toggleFit: () => {} }

/** The floats of the page shown (page.ts): each page keeps its own. */
export default function Floats() {
  const { page, view: a } = useShownView()
  const root = useRef<HTMLDivElement>(null)
  const [room, setRoom] = useState({ w: 0, h: 0 })
  useLayoutEffect(() => {
    const el = root.current
    if (!el) return
    const read = () => setRoom((r) => (r.w === el.clientWidth && r.h === el.clientHeight ? r : { w: el.clientWidth, h: el.clientHeight }))
    const ro = new ResizeObserver(read)
    ro.observe(el); read()
    return () => ro.disconnect()
  }, [])
  /* FOCUS (lensImpl.ts): the windows stay real windows over the Focus area
     (Floating, Mixed), or wait hidden -- still drawn, so nothing in them is
     lost -- while Docked shelves them and Only Focus hides them. The one
     Focus is on is drawn in the Focus area, so its window waits too. Tidied
     around Focus, each is drawn in the band; its saved rectangle stays. */
  const L = useLens(page)
  const comp = L && room.w ? compose(room, shapeOf(L, false)) : null
  return <div ref={root} className="fq-floats" data-lens={comp?.floats}>{(a.focus?.floats ?? []).map((f, i) => <One key={f.id} f={f} page={page} front={i === (a.focus?.floats?.length ?? 0) - 1} room={room} placeAppearance={a.appearance}
    focused={!!L && L.target.kind === 'surface' && L.target.id === f.zone.id} tidied={L?.tidy?.[f.id]} />)}</div>
}
function One({ f, page, front, room, placeAppearance, focused = false, tidied }: { f: Float; page: string; front: boolean; room: { w: number; h: number }; placeAppearance?: unknown; focused?: boolean; tidied?: LensRect }) {
  const el = useRef<HTMLElement | null>(null)
  const [menuAt, setMenuAt] = useState<HTMLElement | null>(null)
  const name = f.zone.name ?? 'Zone'
  const workspaceZone = f.zone.show !== 'conversation' && f.zone.show !== RUN_SHOW
  const scheme = useScheme()
  const appearance = readAppearance(f.zone.slot?.appearance, readAppearance(placeAppearance, DEFAULT_APPEARANCE))
  const look = zoneAppearanceStyle(appearance, scheme)
  const primary = primaryOf(pageView(workspace.arr, page)) === f.zone.id
  const editPrimary = () => {
    const before = pageView(workspace.arr, page), old = locate(before, primaryOf(before))?.zone.name ?? 'Conversation'
    bringPrimary(f.zone.id, `${name} is primary. ${old} floats where it was — ◎ on that window swaps back.`, () => pulseArrived(f.zone.id, f.id))
  }
  const resize = (e: React.PointerEvent) => {
    if (armTouchDrag(e, e.currentTarget as HTMLElement, () => resizeNow(e))) return
    resizeNow(e)
  }
  /* a window tidied around Focus is taken from where it is drawn */
  const adopt = () => { if (tidied) adoptTidied(f.id, page) }
  const resizeNow = (e: React.PointerEvent) => {
    e.preventDefault(); e.stopPropagation()
    adopt()
    const g = tidied ? { ...f, ...tidied } : f
    const before = workspace.arr, x = e.clientX, y = e.clientY, w = g.w, h = g.h
    let moved = false
    const move = (m: PointerEvent) => { if (m.pointerType !== 'mouse') m.preventDefault(); moved = true; workspace.live(onPage((v) => moveFloat(v, f.id, { x: g.x, y: g.y, w: Math.max(MIN_FLOAT_W, w + m.clientX - x), h: Math.max(MIN_FLOAT_H, h + m.clientY - y) }), page)(workspace.arr)) }
    const stop = () => { window.removeEventListener('pointermove', move); window.removeEventListener('pointerup', up); window.removeEventListener('pointercancel', cancel) }
    const up = () => { stop(); if (moved) workspace.live(workspace.arr, { from: before }) }
    const cancel = () => { stop(); if (moved) workspace.live(before) }
    window.addEventListener('pointermove', move); window.addEventListener('pointerup', up); window.addEventListener('pointercancel', cancel)
  }
  const shown = tidied ?? drawnFloatRect(f, room.w, room.h)
  const focusIt = () => focusSurface(f.zone.id, name)
  const tidy = () => {
    const r = document.querySelector<HTMLElement>('.fx-main')?.getBoundingClientRect()
    workspace.edit(onPage((v) => tidyFloats(v, r?.width ?? 0, r?.height ?? 0), page), 'Tidied the floating windows.')
  }
  const close = () => workspace.edit(onPage((v) => closeFloat(v, f.id), page), 'Closed the floating surface.')
  const setSlot: NonNullable<FloatingZoneHead['setSlot']> = (fn, words) =>
    workspace.edit(onPage((v) => updateFloatSlot(v, f.id, fn), page), words)
  const useLookForPlace: NonNullable<FloatingZoneHead['useLookForPlace']> = (appearance) => workspace.edit((a) => ({
    ...onPage((v) => updateFloatSlot(v, f.id, (slot) => ({ ...slot, appearance: undefined })), page)(a), appearance,
  }), `Every zone here without a look of its own now looks like ${name}.`)
  const headProps: FloatingZoneHead['props'] = {
    tabIndex: 0,
    title: 'Drag to move; over a section, pads let you dock it',
    onPointerDown: (e) => { if (!(e.target as HTMLElement).closest('button') && el.current) { adopt(); beginDrag({ type: 'float', id: f.id }, e, el.current, name) } },
    onKeyDown: (e) => {
      if (e.key.toLowerCase() === 'f' && !e.altKey && !e.ctrlKey && !e.metaKey) { e.preventDefault(); if (e.shiftKey) focusIt(); else editPrimary(); return }
      const d = e.shiftKey ? 40 : 10, delta: Record<string, [number, number]> = { ArrowLeft: [-d, 0], ArrowRight: [d, 0], ArrowUp: [0, -d], ArrowDown: [0, d] }
      if (e.altKey && delta[e.key]) { e.preventDefault(); const [dx, dy] = delta[e.key]; workspace.edit(onPage((v) => moveFloat(v, f.id, { x: f.x + dx, y: f.y + dy, w: f.w, h: f.h }), page)) }
    },
  }
  const floating: FloatingZoneHead = {
    from: f.zone.show === 'object' ? <><span className="fl-travelling">With you · Not saved</span>
      {typeof f.zone.options?.says === 'string' && <FromPost f={f} says={f.zone.options.says} />}</> : undefined,
    beforeMenu: <span className="fl-tools">
      <button className="fl-btn" onClick={editPrimary} aria-label="Make primary" title="Make primary (F)">◎</button>
      <FocusSplit surface={{ id: f.zone.id, title: name }} className="fl-lens-btn" />
      <button className="fl-btn" onClick={() => workspace.edit(onPage((v) => dockBack(v, f.id), page), `Docked ${name} back beside the section it left.`)} aria-label="Dock back" title="Dock back">⤓</button>
    </span>,
    afterMenu: <button className="fl-btn fl-close" onClick={close} aria-label="Close floating surface" title="Close">×</button>,
    tidy,
    props: headProps,
    setSlot,
    useLookForPlace,
  }
  return <section ref={el} data-float-id={f.id} className={'wk-float ' + look.className + (front ? ' front' : '') + (primary ? ' primary' : '') + (focused ? ' fl-in-focus' : '') + (tidied ? ' fl-tidied' : '')}
    aria-hidden={focused || undefined} style={{ ...look.style, left: shown.x, top: shown.y, width: shown.w, height: shown.h }}
    onPointerDown={(e) => { if (e.pointerType === 'mouse') workspace.quiet(onPage((v) => toFront(v, f.id), page)) }}
    onClick={() => workspace.quiet(onPage((v) => toFront(v, f.id), page))} role="dialog" aria-label={`Floating ${name}`}>
    {!workspaceZone && <header className="fl-head" tabIndex={0} title="Drag to move; over a section, pads let you dock it"
      onPointerDown={(e) => { if (!(e.target as HTMLElement).closest('button') && el.current) { adopt(); beginDrag({ type: 'float', id: f.id }, e, el.current, name) } }}
      onKeyDown={(e) => {
        if (e.key.toLowerCase() === 'f' && !e.altKey && !e.ctrlKey && !e.metaKey) { e.preventDefault(); if (e.shiftKey) focusIt(); else editPrimary(); return }
        const d = e.shiftKey ? 40 : 10, delta: Record<string, [number, number]> = { ArrowLeft: [-d, 0], ArrowRight: [d, 0], ArrowUp: [0, -d], ArrowDown: [0, d] }
        if (e.altKey && delta[e.key]) { e.preventDefault(); const [dx, dy] = delta[e.key]; workspace.edit(onPage((v) => moveFloat(v, f.id, { x: f.x + dx, y: f.y + dy, w: f.w, h: f.h }), page)) }
      }}>
      <span className="zc-name">{name}</span>{typeof f.zone.options?.says === 'string' && <FromPost f={f} says={f.zone.options.says} />}<span className="grow" />
      <span className="fl-tools">
        <button className="fl-btn" onClick={editPrimary} aria-label="Make primary" title="Make primary (F)">◎</button>
        <FocusSplit surface={{ id: f.zone.id, title: name }} className="fl-lens-btn" />
        <button className="fl-btn" onClick={() => workspace.edit(onPage((v) => dockBack(v, f.id), page), `Docked ${name} back beside the section it left.`)} aria-label="Dock back" title="Dock back">⤓</button>
        {f.zone.show === 'conversation' && <button className="fl-btn" onClick={() => minimizeConversation(page)} aria-label={`Minimize ${name}`} title="Minimize to the launcher (Undo brings it back)">–</button>}
        <button className="fl-btn" aria-label="Floating window menu" aria-expanded={!!menuAt} onClick={(e) => setMenuAt(e.currentTarget)}>⋯</button>
        <button className="fl-btn fl-close" onClick={close} aria-label="Close floating surface" title="Close">×</button>
      </span>
    </header>}
    {!workspaceZone && menuAt && <Sheet anchor={menuAt} onClose={() => setMenuAt(null)} label="floating window menu">
      <Opt onPick={() => {
        setMenuAt(null)
        tidy()
      }}>Tidy floating windows</Opt>
    </Sheet>}
    <div className="fl-body fq-float-body"><FloatBody f={f} page={page} r={{ x: 0, y: 0, w: f.w, h: f.h }} floating={workspaceZone ? floating : undefined} /></div>
    <span className="fl-resize" aria-hidden="true" onPointerDown={resize} />
  </section>
}

/** What a float on `page` shows, at `r`: the conversation (or, given, what
 *  stands in for it), a run's panel, or the zone body every place uses. The
 *  narrow screen's list of floats draws the same (NarrowFloats.tsx). */
export function FloatBody({ f, page, r, conversation, floating }: { f: Float; page: string; r: Rect; conversation?: ReactNode; floating?: FloatingZoneHead }) {
  const name = f.zone.name ?? 'Zone'
  const close = () => workspace.edit(onPage((v) => closeFloat(v, f.id), page))
  return f.zone.show === 'conversation' ? <>{conversation ?? <Mount id={CONVERSATION_ID} />}</>
    : f.zone.show === RUN_SHOW ? <RunPanel run={String(f.zone.options?.run ?? '')} who={String(f.zone.options?.who ?? name)} floating onClose={close} onOpenPost={(c, p) => nav.read(c, p, null)} />
    : <WorkspaceZone z={f.zone} r={r} ctl={{ ...ctl, close }} page={page} first={false} floating={floating} />
}

/** Where an object float came from ("Tidewater survey · #12"), wherever the
 *  owner has gone since (model.ts carryObjectFloats); pressed, its home post
 *  is read, in its own conversation. */
export function FromPost({ f, says }: { f: Float; says: string }) {
  const address = f.zone.slot?.items[0]
  const st = address ? store.objects.get(address) : undefined
  const post = st && 'object' in st ? store.posts.get(st.object.post) : undefined
  const home = post?.home
  return <button className="fl-from" title={home ? `From ${says}: open its post` : `From ${says}`} disabled={!home}
    onClick={() => { if (post && home) nav.read(home, post.id, post.number ?? null) }}>{says}</button>
}
