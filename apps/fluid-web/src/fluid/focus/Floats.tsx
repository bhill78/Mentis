import { useLayoutEffect, useRef, useState, type ReactNode } from 'react'
import { Mount } from './hosts'
import { CONVERSATION_ID, MIN_FLOAT_H, MIN_FLOAT_W, type Float } from './types'
import { armTouchDrag, beginDrag, pulseArrived } from './drag'
import { bringPrimary } from './bring'
import RunPanel from '../runs/RunPanel'
import * as nav from '../nav'
import { RUN_SHOW, canPin, closeFloat, dockBack, drawnFloatRect, locate, lookOf, moveFloat, primaryOf, setMinimized, setPinned, tidyFloats, toFront, updateFloatSlot } from './model'
import type { Rect } from '../workspace/tree'
import { useDisplacements, workspace } from '../workspace/place'
import type { Displacement } from './placement'
import { store } from '../store'
import { onPage, pageView, useShownView } from './page'
import { WorkspaceZone } from '../workspace/Zones'
import { FloatingHeader, type FloatingZoneHead } from './FloatingHeader'
import type { ZoneCtl } from '../workspace/TreeView'
import { Sheet } from '../frame/Sheet'
import { IconMenu } from '../frame/IconMenu'
import { pointAtWindow, windowItems, type WindowActs } from '../workspace/zoneMenu'
import { DEFAULT_APPEARANCE, readAppearance, zoneAppearanceStyle } from '../present'
import { useScheme } from '../frame/look'
import { adoptTidied, focusSurface, useLens } from './lensImpl'
import { compose, shapeOf, LENS_BAR, type Rect as LensRect } from './compose'
import { ClosedHere, closeHere, useClosedHere } from '../surface/ClosedHere'
import { closeOffered, openFloats } from '../surface/projection'
import './floats.css'

const ctl: ZoneCtl = { stacked: false, across: false, canSplitRow: false, canSplitCol: false,
  whyNoSplitRow: 'Floating surfaces must be docked before they can be split', whyNoSplitCol: 'Floating surfaces must be docked before they can be split',
  canMerge: false, canClose: true, split: () => {}, merge: () => {}, close: () => {}, closing: false, widen: () => false, docked: false, fit: false, canFit: false }

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
    return () => { ro.disconnect(); workspace.clearDisplacements() }
  }, [])
  /* FOCUS (lensImpl.ts): the windows stay real windows over the Focus area
     (Floating, Mixed), or wait hidden -- still drawn, so nothing in them is
     lost -- while Docked shelves them and Only Focus hides them. The one
     Focus is on is drawn in the Focus area, so its window waits too. Tidied
     around Focus, each is drawn in the band; its saved rectangle stays. */
  const L = useLens(page)
  const comp = L && room.w ? compose(room, shapeOf(L, false)) : null
  /* a window closed on this device is not drawn here (Reopen: ClosedHere) */
  const closed = useClosedHere()
  const floats = openFloats(a.focus?.floats ?? [], closed)
  const displacements = useDisplacements()
  const front = [...floats].reverse().find((f) => !f.min)?.id
  return <div ref={root} className="fq-floats" data-lens={comp?.floats}>{floats.map((f) => <One key={f.id} f={f} page={page} front={f.id === front} room={room} placeAppearance={a.appearance} displacement={displacements.get(f.zone.id)}
    focused={!!L && L.target.kind === 'surface' && L.target.id === f.zone.id} tidied={L?.tidy?.[f.id]} bar={comp ? { ...comp.area, h: LENS_BAR } : undefined} />)}
    <MinimizedTabs floats={floats} page={page} displacements={displacements} />
    <ClosedHere view={a} />
  </div>
}

function MinimizedTabs({ floats, page, displacements }: { floats: Float[]; page: string; displacements: ReadonlyMap<string, Displacement> }) {
  const minimized = floats.filter((f) => f.min || displacements.get(f.zone.id)?.fold)
  if (!minimized.length) return null
  return <nav className="fq-mintabs" aria-label="Minimised windows">
    {minimized.map((f) => {
      const name = f.zone.name ?? 'Zone'
      const folded = !!displacements.get(f.zone.id)?.fold && !f.min
      return <button key={f.id} className="fq-mintab"
        onClick={() => folded ? workspace.clearDisplacements() : workspace.edit(onPage((v) => toFront(setMinimized(v, f.id, false), f.id), page), `Restored ${name}.`)}
        aria-label={`Restore ${name}`} title={folded ? 'Put the yielded surfaces back' : `Restore ${name} where it was`}>{name}</button>
    })}
  </nav>
}
function One({ f, page, front, room, placeAppearance, focused = false, tidied, bar, displacement }: { f: Float; page: string; front: boolean; room: { w: number; h: number }; placeAppearance?: unknown; focused?: boolean; tidied?: LensRect; bar?: LensRect; displacement?: Displacement }) {
  const el = useRef<HTMLElement | null>(null)
  const [menuAt, setMenuAt] = useState<HTMLElement | null>(null)
  const name = f.zone.name ?? 'Zone'
  const workspaceZone = f.zone.show !== 'conversation' && f.zone.show !== RUN_SHOW
  const scheme = useScheme()
  const appearance = readAppearance(lookOf(f.zone), readAppearance(placeAppearance, DEFAULT_APPEARANCE))
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
  /* THE FOCUS BAR STAYS REACHABLE: a window over the Focus area is drawn below
     its bar (Restore, the presentations), never on it. Drawing only: the
     window's own rectangle is unchanged, so Restore and the saved layout are too. */
  const base = tidied ?? drawnFloatRect(f, room.w, room.h)
  const drawn = displacement && !tidied ? { ...base, x: base.x + displacement.dx, y: base.y + displacement.dy,
    w: displacement.w ?? base.w, h: displacement.h ?? base.h } : base
  const onBar = !!bar && !tidied && drawn.y < bar.y + bar.h && drawn.y + drawn.h > bar.y && drawn.x < bar.x + bar.w && drawn.x + drawn.w > bar.x
  const lifted = onBar ? { ...drawn, y: bar!.y + bar!.h + 6 } : drawn
  /* MINIMISED, the real window stays mounted but hidden; MinimizedTabs is its
     compact way back. Scroll, drafts and searches therefore survive. */
  const min = !!(f.min || displacement?.fold) && !tidied
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
  /* ONE WINDOW CHROME: every desktop float uses FloatingHeader's grip,
     title, minimise, gear and close. Every other window action stays in the
     gear's Arrange column (workspace/zoneMenu.tsx), by icon and word. */
  const toggleMin = () => workspace.edit(onPage((v) => setMinimized(v, f.id, !f.min), page), f.min ? undefined : `${name} is minimised: ▭ or its menu opens it again.`)
  const headProps: FloatingZoneHead['props'] = {
    tabIndex: 0,
    title: 'Drag to move; over a section, pads let you dock it. Double-click to minimise or restore',
    onPointerDown: (e) => { if (!(e.target as HTMLElement).closest('button') && el.current) { adopt(); beginDrag({ type: 'float', id: f.id }, e, el.current, name) } },
    onDoubleClick: (e) => { if (!(e.target as HTMLElement).closest('button, input')) toggleMin() },
    onKeyDown: (e) => {
      if (e.key.toLowerCase() === 'f' && !e.altKey && !e.ctrlKey && !e.metaKey) { e.preventDefault(); if (e.shiftKey) focusIt(); else editPrimary(); return }
      const d = e.shiftKey ? 40 : 10, delta: Record<string, [number, number]> = { ArrowLeft: [-d, 0], ArrowRight: [d, 0], ArrowUp: [0, -d], ArrowDown: [0, d] }
      if (e.altKey && delta[e.key]) { e.preventDefault(); const [dx, dy] = delta[e.key]; workspace.edit(onPage((v) => moveFloat(v, f.id, { x: f.x + dx, y: f.y + dy, w: f.w, h: f.h }), page)) }
    },
  }
  /* THE PIN (model.ts setPinned): pinned, this window goes with the owner to
     every Page and conversation; unpinned, it stays where it was made. */
  const pinned = !!f.pinned
  const pin = () => workspace.edit(onPage((v) => setPinned(v, f.id, !pinned), page), pinned
    ? `${name} is unpinned: it stays here.` : `${name} is pinned: it stays with you in every conversation.`)
  const dock = () => workspace.edit(onPage((v) => dockBack(v, f.id), page), `Docked ${name} back beside the section it left.`)
  const acts: WindowActs = {
    primary: editPrimary, focus: focusIt,
    ...(canPin(f.zone) ? { pin: { on: pinned, run: pin } } : {}),
    dockBack: dock,
    minimise: { on: !!f.min, run: toggleMin },
    tidy, close,
  }
  const floating: FloatingZoneHead = {
    tidy,
    props: headProps,
    setSlot,
    useLookForPlace,
    window: acts,
    id: f.zone.id,
    ...(closeOffered('float', 'float') ? { closeHere: closeHere(f.zone.id) } : {}),
  }
  return <section ref={el} data-float-id={f.id} className={'wk-float ' + look.className + (front ? ' front' : '') + (primary ? ' primary' : '') + (focused ? ' fl-in-focus' : '') + (tidied ? ' fl-tidied' : '') + (min ? ' fl-min' : '')}
    aria-hidden={focused || min || undefined} style={{ ...look.style, left: lifted.x, top: lifted.y, width: lifted.w, height: lifted.h }}
    onFocusCapture={() => pointAtWindow(acts)}
    onPointerDown={(e) => { if (e.pointerType === 'mouse') workspace.quiet(onPage((v) => toFront(v, f.id), page)) }}
    onClick={() => workspace.quiet(onPage((v) => toFront(v, f.id), page))} role="dialog" aria-label={`Floating ${name}`}>
    {!workspaceZone && <FloatingHeader name={name} floating={floating} menuAt={menuAt} onMenu={setMenuAt}
      settingsTitle="Settings for this window: where it sits" />}
    {!workspaceZone && menuAt && <Sheet anchor={menuAt} onClose={() => setMenuAt(null)} label="floating window menu">
      <IconMenu groups={[{ title: 'Arrange', items: windowItems(acts), summary: 'Floating window' }]} label={`${name} window`} onDone={() => setMenuAt(null)} layout="accordion" open="arrange" />
    </Sheet>}
    <div className="fl-body fq-float-body"><FloatBody f={f} page={page} r={{ x: 0, y: 0, w: lifted.w, h: lifted.h }} floating={workspaceZone ? floating : undefined} /></div>
    {!min && <span className="fl-resize" aria-hidden="true" onPointerDown={resize} />}
  </section>
}

/** What a float on `page` shows, at `r`: the conversation (or, given, what
 *  stands in for it), a run's panel, or the zone body every place uses. The
 *  narrow screen's list of floats draws the same (NarrowFloats.tsx). */
export function FloatBody({ f, page, r, conversation, floating }: { f: Float; page: string; r: Rect; conversation?: ReactNode; floating?: FloatingZoneHead }) {
  const name = f.zone.name ?? 'Zone'
  const close = () => workspace.edit(onPage((v) => closeFloat(v, f.id), page))
  return f.zone.show === 'conversation' ? <>{conversation ?? <Mount id={CONVERSATION_ID} />}</>
    : f.zone.show === RUN_SHOW ? <RunPanel run={String(f.zone.options?.run ?? '')} who={String(f.zone.options?.who ?? name)} floating onClose={close} onOpenPost={(c, p, decision) => nav.read(c, p, decision ? { decision } : null)} />
    : <WorkspaceZone z={f.zone} r={r} ctl={{ ...ctl, close }} page={page} first={false} floating={floating} />
}

/** Where an object float came from ("Tidewater survey · #12"), wherever the
 *  owner has gone since (model.ts carryPinnedFloats); pressed, its home post
 *  is read, in its own conversation. A whole post (`post:<id>`) is its own. */
export function FromPost({ f, says }: { f: Float; says: string }) {
  const address = f.zone.slot?.items[0]
  const st = address && !address.startsWith('post:') ? store.objects.get(address) : undefined
  const post = address?.startsWith('post:') ? store.posts.get(address.slice(5))
    : st && 'object' in st ? store.posts.get(st.object.post) : undefined
  const home = post?.home
  return <button className="fl-from" title={home ? `From ${says}: open its post` : `From ${says}`} disabled={!home}
    onClick={() => { if (post && home) nav.read(home, post.id, post.number ?? null) }}>{says}</button>
}
