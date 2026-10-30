/* EACH PLACE KEEPS ITS OWN ARRANGEMENT (Fluid completion, stream A; #107,
 * #188, #190, adm-c93a 5.5).
 *
 * A place is Home, a conversation, an unnamed (provisional) conversation or
 * the Stream. Its arrangement is This post's tree, its own pages (each a
 * tree) and the boundaries the reader dragged. Where it comes from, in
 * order (#107: "unsaved arrangements remain temporary and independent per
 * browser session"):
 *
 *   1. this tab's session (sessionStorage): every change lands here, so a
 *      reload comes back exactly as left;
 *   2. what the owner SAVED for this place, in the Brain
 *      (`/fluid/api/arrangements/<key>`): Save, and Restore saved;
 *   3. the named layout the place's kind starts from (`/fluid/api/layouts`
 *      defaults: home, conversation, unnamed);
 *   4. the product's own start: one zone following what is read (Home: its
 *      five collections).
 *
 * ONE RULE EVERYWHERE (#464: "explicit Save on Home too"): Home, like every
 * place, keeps a change in this tab until Save -- its zones, a Work tab, the
 * briefing's period alike. `changed()` says when this tab differs from what
 * the Brain keeps, so the Arrange button can say so.
 *
 * The place also carries its DEFAULT LOOK (#188: "each place sets a default,
 * and any zone can override it") and the THREADS PINNED in it, as tabs
 * (#188), both saved with it; a named layout carries the look, never the
 * pins, which are this place's posts.
 *
 * Presentation only: nothing here writes to the record. */

import { useSyncExternalStore } from 'react'
import { CLIENT_HEADERS } from '../../api'
import { fluidFetch } from '../http'
import * as nav from '../nav'
import { store, newOp } from '../store'
import { followSlot, freshId, itemsOf, keepSlot, named, splitOuter, valid, zone, zones, type Appearance, type Node, type Zone } from './tree'
import { CONVERSATION_ID, MAX_FLOATS, type Float, type FocusArr } from '../focus/types'
import { canPin, carryPinnedFloats, floatThread, isContentZone, isObjectZone, isThreadZone, pinnedFloatsOf, readMinimized, threadRootOf, threadsOf, travelKey, withFocus } from '../focus/model'
import { allPageViews, onPage, pageView, shownPage, withPageView, THIS_POST } from '../focus/page'
import { lens } from '../focus/lens'
import { capsFor, transition } from '../surface/transition'
import type { Change, DevicePlacement, Outcome, PresentationClass, SurfaceCtx, SurfaceState } from '../surface/types'
import type { Displacement } from '../focus/placement'

export type PlaceKind = 'conversation' | 'unnamed' | 'home' | 'stream'
/** A page of the place's own: its tree, and its own Fluid Focus (focus/page.ts). */
export interface PageArr { id: string; title: string; object?: string; tree: Node; focus?: FocusArr; setAside?: Zone[] }
export interface Threads { pinned: string[]; active: string | null }
export interface Arr {
  tree: Node; pages: PageArr[]; conversation?: { width?: number; replies?: number }
  /** the place's default look; a zone with its own overrides it */
  appearance?: Appearance
  /** the threads pinned here, in tab order, and the tab shown */
  threads?: Threads
  /** Fluid Focus placement: column content, floating places and history. */
  focus?: FocusArr
  /** Sections displaced by a Page layout. Presentation only, recoverable. */
  setAside?: Zone[]
}
export type From = 'session' | 'saved' | 'default' | 'product' | 'layout'

function displacedFocus(focus: FocusArr | undefined, map: ReadonlyMap<string, Displacement>): FocusArr | undefined {
  if (!focus?.floats?.length) return focus
  let changed = false
  const floats = focus.floats.map((f) => {
    const d = map.get(f.zone.id)
    if (!d) return f
    changed = true
    return { ...f, x: f.x + d.dx, y: f.y + d.dy, w: d.w ?? f.w, h: d.h ?? f.h,
      ...(d.fold ? { min: true as const } : {}) }
  })
  return changed ? { ...focus, floats } : focus
}

/** Apply a preview map to saved geometry.  Exported for the dense P6 tests;
 * Holder uses it only when the reader explicitly keeps the arrangement. */
export function applyDisplacements(a: Arr, map: ReadonlyMap<string, Displacement>): Arr {
  if (!map.size) return a
  const focus = displacedFocus(a.focus, map)
  const pages = a.pages.map((p) => {
    const next = displacedFocus(p.focus, map)
    return next === p.focus ? p : { ...p, focus: next }
  })
  return focus === a.focus && pages.every((p, i) => p === a.pages[i]) ? a : { ...a, focus, pages }
}

const FORMAT = 'mentis.fluid-arrangement'
const FILLS = new Set(['transparent', 'tinted', 'solid'])

/** A page's Focus as it is kept: what differs from the start. A pinned float
 *  travels with the owner (focus/model.ts): it is the workspace's, not this
 *  place's, so no layout keeps it. An unpinned object float stays with its
 *  page in this tab's copy of the place (`tab`), but a saved or named layout
 *  is a shape, and never holds one. */
function focusLayout(f: (FocusArr) | undefined, tab = false): (FocusArr) | undefined {
  if (!f) return undefined
  const kept = (f.floats ?? []).filter((x) => !x.pinned && (tab || !isContentZone(x.zone)))
  const out: FocusArr = {
    ...(f.primary && f.primary !== CONVERSATION_ID ? { primary: f.primary } : {}),
    ...(f.column && f.column.id !== CONVERSATION_ID ? { column: f.column } : {}),
    ...(kept.length ? { floats: kept } : {}),
    ...(f.previous?.length ? { previous: f.previous.slice(-20) } : {}),
    ...(f.minimized ? { minimized: f.minimized } : {}),
  }
  return Object.keys(out).length ? out : undefined
}

/** The arrangement as kept; `tab`: this tab's own copy of the place, which
 *  also keeps the unpinned object floats where they were made. */
export function toLayout(a: Arr, { tab = false }: { tab?: boolean } = {}): Record<string, unknown> {
  const focus = focusLayout(a.focus, tab)
  /* THREAD WINDOWS ARE KEPT AS THE PINNED THREADS WERE (readThreadWindows):
     this tab's copy keeps each window where it is; Save keeps which threads
     are open here, as `threads.pinned` -- the shape every build reads. */
  const pinned = tab ? a.threads?.pinned ?? [] : [...new Set([...(a.threads?.pinned ?? []), ...threadWindowRoots(a)])]
  const threads = pinned.length ? { pinned, ...(a.threads?.active && pinned.includes(a.threads.active) ? { active: a.threads.active } : {}) } : null
  return {
    format: FORMAT, version: 2, tree: a.tree,
    ...(a.pages.length ? { pages: a.pages.map((p) => {
      const pf = focusLayout(p.focus, tab)
      return { id: p.id, title: p.title, tree: p.tree, ...(p.object ? { object: p.object } : {}), ...(pf ? { focus: pf } : {}),
        ...(p.setAside?.length ? { setAside: p.setAside } : {}) }
    }) } : {}),
    ...(a.conversation && Object.keys(a.conversation).length ? { conversation: a.conversation } : {}),
    ...(a.appearance ? { appearance: a.appearance } : {}),
    ...(threads ? { threads } : {}),
    ...(focus ? { focus } : {}),
    ...(a.setAside?.length ? { setAside: a.setAside } : {}),
  }
}

/** The threads open in windows here, on every page (not those pinned to the
 *  owner, which travel and are no part of the place). */
const threadWindowRoots = (a: Arr): string[] => allPageViews(a).flatMap(({ view }) =>
  (view.focus?.floats ?? []).filter((f) => !f.pinned && isThreadZone(f.zone)).map((f) => threadRootOf(f.zone)!))

/* PINNED THREADS READ AS THREAD WINDOWS (owner feedback, round 2). A place
 * saved with pinned threads -- tabs in the panel beside the conversation --
 * opens with each in a window of its own on This post, cascading beside the
 * conversation; a thread already shown somewhere on the place is not opened
 * twice. Nothing of the old shape is lost: Save writes them back the same way. */
export function readThreadWindows(a: Arr): Arr {
  const roots = a.threads?.pinned ?? []
  if (!roots.length) return a
  const shown = new Set(allPageViews(a).flatMap(({ view }) => threadsOf(view).map((t) => threadRootOf(t.zone))))
  const { threads: _was, ...rest } = a
  let next: Arr = rest
  roots.filter((r) => !shown.has(r)).forEach((r, i) => { next = floatThread(next, r, { x: 470 + i * 28, y: 24 + i * 28, w: 420, h: 560 }) })
  return next
}

/** `fresh` (a place's start) with the thread windows `had` showed on every
 *  page kept over This post: going back to the start closes no thread. */
function keepThreadWindows(fresh: Arr, had: Arr): Arr {
  const fs = allPageViews(had).flatMap(({ view }) => (view.focus?.floats ?? []).filter((f) => !f.pinned && isThreadZone(f.zone)))
  if (!fs.length) return fresh
  const f = fresh.focus ?? {}
  return withFocus(fresh, { ...f, floats: [...(f.floats ?? []), ...fs].slice(-MAX_FLOATS) })
}

function readLook(v: unknown): Appearance | undefined {
  const o = v as Record<string, unknown> | null
  if (!o || typeof o !== 'object') return undefined
  const out: Appearance = {}
  if (FILLS.has(o.panel as string)) out.panel = o.panel as Appearance['panel']
  if (FILLS.has(o.content as string)) out.content = o.content as Appearance['content']
  if (typeof o.opacity === 'number' && Number.isFinite(o.opacity)) out.opacity = Math.min(1, Math.max(0, o.opacity))
  return Object.keys(out).length ? out : undefined
}
function readThreads(v: unknown): Threads | undefined {
  const o = v as Record<string, unknown> | null
  if (!o || !Array.isArray(o.pinned)) return undefined
  const pinned = [...new Set((o.pinned as unknown[]).filter((p): p is string => typeof p === 'string'))]
  if (!pinned.length) return undefined
  return { pinned, active: typeof o.active === 'string' && pinned.includes(o.active) ? o.active : null }
}

function readSetAside(v: unknown, used: Set<string>): Zone[] | undefined {
  if (!Array.isArray(v)) return undefined
  const out: Zone[] = []
  for (const raw of v) {
    if (!valid(raw) || raw.type !== 'zone' || used.has(raw.id)) continue
    const z = named(raw) as Zone
    used.add(z.id)
    out.push(z)
  }
  return out.length ? out : undefined
}

function readFocus(v: unknown, tree: Node, reserved: readonly string[] = []): (FocusArr) | undefined {
  const o = v as Record<string, unknown> | null
  if (!o || typeof o !== 'object') return undefined
  const used = new Set([...itemsOfIds(tree), ...reserved])
  const column = valid(o.column) && (o.column as Node).type === 'zone' && !used.has((o.column as Zone).id) ? named(o.column as Zone) as Zone : undefined
  if (column) used.add(column.id)
  const floats = Array.isArray(o.floats) ? (o.floats as Record<string, unknown>[]).slice(0, MAX_FLOATS).flatMap((f) => {
    if (!f || typeof f.id !== 'string' || used.has(f.id) || !valid(f.zone) || (f.zone as Node).type !== 'zone') return []
    const z = f.zone as Zone
    if (used.has(z.id) || !['x', 'y', 'w', 'h'].every((k) => typeof f[k] === 'number' && Number.isFinite(f[k] as number))
      || Math.abs(f.x as number) > 100000 || Math.abs(f.y as number) > 100000
      || (f.w as number) <= 0 || (f.w as number) > 100000 || (f.h as number) <= 0 || (f.h as number) > 100000) return []
    used.add(f.id); used.add(z.id)
    const origin = f.origin as Record<string, unknown> | undefined
    return [{ id: f.id, zone: named(z) as Zone, x: f.x as number, y: f.y as number, w: f.w as number, h: f.h as number, ...(f.min === true ? { min: true as const } : {}),
      ...(origin && typeof origin.near === 'string' && ['left', 'right', 'top', 'bottom'].includes(origin.side as string)
        ? { origin: { near: origin.near, side: origin.side as 'left' | 'right' | 'top' | 'bottom',
          ...(typeof origin.share === 'number' && origin.share >= 0 && origin.share <= 1 ? { share: origin.share } : {}) } } : {}) }]
  }) : []
  const ids = new Set([...itemsOfIds(tree), ...(column ? [column.id] : []), ...floats.map((f) => f.zone.id)])
  const primary = typeof o.primary === 'string' && ids.has(o.primary) && o.primary !== CONVERSATION_ID ? o.primary : undefined
  const previous = Array.isArray(o.previous) ? o.previous.filter((x): x is string => typeof x === 'string').slice(-20) : []
  const minimized = readMinimized(o.minimized, tree, floats)
  const out: FocusArr = { ...(primary ? { primary } : {}), ...(column ? { column } : {}), ...(floats.length ? { floats } : {}), ...(previous.length ? { previous } : {}), ...(minimized ? { minimized } : {}) }
  return Object.keys(out).length ? out : undefined
}
const itemsOfIds = (n: Node): string[] => n.type === 'zone' ? [n.id] : n.kids.flatMap(itemsOfIds)

/** One arrangement's identity, whatever order its keys were written in. */
const canon = (v: unknown): string => JSON.stringify(v, (_k, x) =>
  x && typeof x === 'object' && !Array.isArray(x) ? Object.fromEntries(Object.keys(x).sort().map((k) => [k, x[k]])) : x)

export function fromLayout(l: unknown): Arr | null {
  const o = l as Record<string, unknown> | null
  if (!o) return null
  if (typeof o.version === 'number' && o.version !== 1 && o.version !== 2) {
    nav.toast({ text: `Cannot read layout version ${o.version}: this build reads versions 1 and 2.` })
    return null
  }
  if (!valid(o.tree)) return null
  const pages = Array.isArray(o.pages)
    ? (o.pages as Record<string, unknown>[]).filter((p) => p && typeof p.id === 'string' && typeof p.title === 'string' && valid(p.tree))
      .map((p) => {
        const tree = named(p.tree as Node)
        const setAside = readSetAside(p.setAside, new Set(itemsOfIds(tree)))
        const focus = readFocus(p.focus, tree, setAside?.map((z) => z.id) ?? [])
        return { id: p.id as string, title: p.title as string, tree, ...(typeof p.object === 'string' ? { object: p.object } : {}),
          ...(focus ? { focus } : {}), ...(setAside ? { setAside } : {}) }
      })
    : []
  const c = o.conversation as Record<string, unknown> | undefined
  const conversation = c && typeof c === 'object'
    ? { ...(typeof c.width === 'number' ? { width: c.width } : {}), ...(typeof c.replies === 'number' ? { replies: c.replies } : {}) }
    : undefined
  const appearance = readLook(o.appearance)
  const threads = readThreads(o.threads)
  const tree = named(o.tree as Node)
  const setAside = readSetAside(o.setAside, new Set(itemsOfIds(tree)))
  const focus = readFocus(o.focus, tree, setAside?.map((z) => z.id) ?? [])
  return readThreadWindows({ tree, pages, ...(conversation ? { conversation } : {}), ...(appearance ? { appearance } : {}), ...(threads ? { threads } : {}),
    ...(focus ? { focus } : {}), ...(setAside ? { setAside } : {}) })
}

/** The owner's pinned floats, wherever among this place's pages they are now,
 * one per thing shown (an object's live address, else a section). */
export function pagePinnedFloatsOf(a: Arr): Float[] {
  const seen = new Set<string>()
  return allPageViews(a).flatMap(({ view }) => pinnedFloatsOf(view)).filter((f) => {
    const key = travelKey(f)
    if (seen.has(key)) return false
    seen.add(key)
    return true
  })
}

async function getJson<T>(path: string): Promise<T> {
  const res = await fluidFetch('/fluid/api/' + path, { headers: { ...CLIENT_HEADERS } })
  const body = await res.json().catch(() => null)
  if (!res.ok || !body || body.error) throw Object.assign(new Error(body?.error ?? res.statusText), { status: res.status })
  return body as T
}
async function postJson<T>(path: string, body: unknown): Promise<T> {
  const res = await fluidFetch('/fluid/api/' + path, {
    method: 'POST', headers: { ...CLIENT_HEADERS, 'Content-Type': 'application/json' }, body: JSON.stringify(body),
  })
  const got = await res.json().catch(() => null)
  if (!res.ok || !got || got.error) throw Object.assign(new Error(got?.error ?? res.statusText), { status: res.status })
  return got as T
}

/* -- named layouts and defaults, read once and kept current -------------------- */

export interface Named { id: string; name: string; saved?: number; layout: Record<string, unknown> }
/** A built-in layout (P12): Home's arrangement and a conversation's together,
 *  read-only -- the Brain never keeps one; a user saves a copy of their own.
 *  `share` is the conversation column's part of the width. */
export interface Preset { id: string; name: string; says: string; preset: true; share: number; home: Record<string, unknown>; conversation: Record<string, unknown> }
export type DefaultPlace = 'home' | 'conversation' | 'unnamed'
export interface Library { layouts: Named[]; presets?: Preset[]; defaults: Record<DefaultPlace, string | null>; unreadable?: string }
let library: Library | null = null
let libraryLoad: Promise<Library | null> | null = null
const libraryFns = new Set<() => void>()
const setLibrary = (l: Library) => { library = l; libraryFns.forEach((fn) => fn()) }
export function loadLibrary(force = false): Promise<Library | null> {
  /* The library as it now stands: a default named since it was first read counts. */
  if (!force && library) return Promise.resolve(library)
  if (!force && libraryLoad) return libraryLoad
  libraryLoad = getJson<Library>('layouts').then((l) => { setLibrary(l); return l }, () => null)
  return libraryLoad
}
export const useLibrary = () => useSyncExternalStore((fn) => { libraryFns.add(fn); return () => { libraryFns.delete(fn) } }, () => library)
export async function saveNamed(name: string, a: Arr): Promise<Named> {
  const id = freshId('l')
  const got = await postJson<Library>('layouts', { id, name, layout: toLayout(a) })
  setLibrary(got)
  return got.layouts.find((l) => l.id === id)!
}
export async function deleteNamed(id: string) { setLibrary(await postJson<Library>(`layouts/${encodeURIComponent(id)}/delete`, {})) }
export async function setDefault(place: DefaultPlace, layout: string | null) {
  setLibrary(await postJson<Library>('layouts/defaults', { place, layout }))
}
export const PLACES: DefaultPlace[] = ['home', 'conversation', 'unnamed']

/* -- presets (P12) ------------------------------------------------------------- */

/** The conversation column's width for a preset's share of the room here:
 *  never narrower than a reader can read, never leaving the workspace less
 *  than its least. */
export function presetWidth(share: number): number {
  const room = (typeof document === 'undefined' ? 0 : document.getElementById('main')?.getBoundingClientRect().width)
    || (typeof window === 'undefined' ? 1200 : window.innerWidth)
  return Math.round(Math.max(nav.READABLE, Math.min(room - 300, share * room)))
}
/** A preset as a named layout for one kind of place: Home's half, or the
 *  conversation's with its column's width in this window. */
export function presetLayout(p: Preset, kind: PlaceKind): Named {
  if (kind === 'home') return { id: p.id, name: p.name, layout: p.home }
  return { id: p.id, name: p.name, layout: materializeFractionFloats({ ...p.conversation, conversation: { width: presetWidth(p.share) } }) }
}
/** What a place kind's default names, a preset's half or a layout kept here. */
export function defaultOf(lib: Library | null, place: DefaultPlace, kind: PlaceKind): Named | null {
  const id = lib?.defaults[place]
  if (!id) return null
  const p = lib?.presets?.find((x) => x.id === id)
  return p ? presetLayout(p, kind) : lib?.layouts.find((l) => l.id === id) ?? null
}
/** Apply a preset to the shown Page. Defaults are deliberately separate. */
export function usePreset(p: Preset) {
  applyLayout(presetLayout(p, workspace.kind), 'page')
}
export async function setDefaults(places: DefaultPlace[], layout: string | null) {
  setLibrary(await postJson<Library>('layouts/defaults', { places, layout }))
}

export type LayoutScope = 'page' | 'place'

const sectionZones = (a: Arr): Zone[] => [
  ...zones(a.tree),
  ...(a.focus?.column ? [a.focus.column] : []),
  ...(a.focus?.floats ?? []).filter((f) => !isContentZone(f.zone) && !f.pinned).map((f) => f.zone),
  ...(a.setAside ?? []),
]

const mergePlaced = (shape: Zone, had: Zone | undefined): Zone => {
  if (!had?.slot || !shape.slot) return shape
  const items = [...new Set([...had.slot.items, ...shape.slot.items])]
  return items.length === shape.slot.items.length && items.every((x, i) => x === shape.slot!.items[i])
    ? shape : { ...shape, slot: { ...shape.slot, items } }
}

const mapZones = (n: Node, f: (z: Zone) => Zone): Node => n.type === 'zone'
  ? f(n)
  : { ...n, kids: n.kids.map((k) => mapZones(k, f)) }

const fractionFloats = (focus: FocusArr | undefined): FocusArr | undefined => {
  if (!focus?.floats?.some((f) => f.w > 0 && f.w <= 1 && f.h > 0 && f.h <= 1)) return focus
  const el = typeof document === 'undefined' ? null : document.querySelector<HTMLElement>('.fx-main')
  const room = el?.getBoundingClientRect()
  const w = room?.width || (typeof window === 'undefined' ? 1200 : window.innerWidth)
  const h = room?.height || (typeof window === 'undefined' ? 800 : window.innerHeight)
  return { ...focus, floats: focus.floats.map((f) => f.w > 0 && f.w <= 1 && f.h > 0 && f.h <= 1
    ? { ...f, x: f.x * w, y: f.y * h, w: f.w * w, h: f.h * h }
    : f) }
}

function materializeFractionFloats(layout: Record<string, unknown>): Record<string, unknown> {
  const a = fromLayout(layout)
  if (!a) return layout
  return toLayout({
    ...a,
    ...(a.focus ? { focus: fractionFloats(a.focus) } : {}),
    pages: a.pages.map((p) => ({ ...p, ...(p.focus ? { focus: fractionFloats(p.focus) } : {}) })),
  })
}

/** Put one layout shape on one Page view, preserving its content and history. */
export function layoutPage(view: Arr, shape: Arr): Arr {
  const old = new Map(sectionZones(view).map((z) => [z.id, z]))
  const shapeFocus = fractionFloats(shape.focus)
  const tree = mapZones(shape.tree, (z) => mergePlaced(z, old.get(z.id)))
  const column = shapeFocus?.column ? mergePlaced(shapeFocus.column, old.get(shapeFocus.column.id)) : undefined
  const shapeFloats = (shapeFocus?.floats ?? []).map((f) => ({ ...f, zone: mergePlaced(f.zone, old.get(f.zone.id)) }))
  /* object and thread windows, and pinned ones, are no part of a layout's shape: they stay */
  const objectFloats = (view.focus?.floats ?? []).filter((f) => isContentZone(f.zone) || f.pinned)
  const inLayout = new Set([...zones(tree).map((z) => z.id), ...(column ? [column.id] : []), ...shapeFloats.map((f) => f.zone.id)])
  const setAside = sectionZones(view).filter((z, i, all) => !inLayout.has(z.id) && all.findIndex((x) => x.id === z.id) === i)
  const previous = view.focus?.previous
  const focus: FocusArr = {
    ...(shapeFocus ?? {}),
    ...(column ? { column } : {}),
    ...((shapeFloats.length || objectFloats.length) ? { floats: [...shapeFloats, ...objectFloats] } : {}),
    ...(previous?.length ? { previous } : {}),
  }
  return {
    ...view,
    tree,
    ...(Object.keys(focus).length ? { focus } : { focus: undefined }),
    ...(setAside.length ? { setAside } : { setAside: undefined }),
  }
}

/** Sections waiting outside a Page's layout, in recoverable order. */
export function setAsideOf(page: string = shownPage()): readonly Zone[] {
  return pageView(workspace.arr, page).setAside ?? []
}

/** Restore a set-aside section at the right of its Page, as one Undo step. */
export function restoreSetAside(page: string, zoneId: string): void {
  workspace.edit(onPage((view) => {
    const z = view.setAside?.find((x) => x.id === zoneId)
    if (!z) return view
    const setAside = view.setAside!.filter((x) => x.id !== zoneId)
    return { ...view, tree: splitOuter(view.tree, 'right', z, .75), ...(setAside.length ? { setAside } : { setAside: undefined }) }
  }, page), 'Restored the set-aside section to this Page.')
}

/** The shared preset API used by Arrange. */
export function applyLayout(layout: Named, scope: LayoutScope = 'page'): void {
  workspace.applyLayout(layout, scope)
}
/** Is this layout one for a conversation's workspace, or for Home? */
export const layoutKind = (l: Named): 'home' | 'workspace' => {
  const zs: Zone[] = []
  const walk = (n: Node) => (n.type === 'zone' ? zs.push(n) : n.kids.forEach(walk))
  if (valid(l.layout.tree)) walk(l.layout.tree as Node)
  /* Home keeps things too now (its kept zones, D1): a zone that shows
     anything but a conversation's objects is Home's. */
  return zs.some((z) => z.slot) && zs.every((z) => z.show === 'objects') ? 'workspace' : 'home'
}

/* -- one holder of a place's arrangement ---------------------------------------- */

const SESSION = 'mentis.fluid.arr:'
/** the workspace's travelling floats, in this tab (Holder `carry`) */
const TRAVEL = 'mentis.fluid.travel'
/** Travelling floats read back: each well formed, or left out. An entry kept
 *  before pins (an object float, which always travelled then) reads pinned:
 *  it was with the owner, and stays so. */
export function readTravel(v: unknown): Float[] {
  if (!Array.isArray(v)) return []
  const n = (x: unknown) => typeof x === 'number' && Number.isFinite(x)
  return v.filter((f): f is Float => !!f && typeof f.id === 'string' && valid(f.zone) && f.zone.type === 'zone' && canPin(f.zone)
    && (f.pinned === true || isObjectZone(f.zone)) && n(f.x) && n(f.y) && n(f.w) && n(f.h)).slice(0, MAX_FLOATS)
    .map((f) => ({ ...f, pinned: true as const }))
}
const TOUCHED = ':changed'
const UNDO = 20

/* -- surfaces (Surface Tension §3.3, P1) ------------------------------------------- */

type Devices = Partial<Record<'medium' | 'compact', DevicePlacement>>
/** One undo step: the arrangement and the class records as they were. */
interface Step { arr: Arr; devices: Devices; label?: string }
/** What a surface change is made in, where the caller does not say. */
export interface SurfaceEnv { page?: string | null; cls?: PresentationClass; viewport?: { w: number; h: number } }
/** The presentation class of the window now: frame/narrow.ts presentationClass's
 *  rule (not imported: narrow -> threads -> place is a cycle). */
const classNow = (): PresentationClass => {
  const w = typeof innerWidth === 'number' ? innerWidth : 1280
  return w > 1024 ? 'wide' : w > 760 ? 'medium' : 'compact'
}
const viewportNow = () => ({ w: typeof innerWidth === 'number' ? innerWidth : 1280, h: typeof innerHeight === 'number' ? innerHeight : 800 })

export class Holder {
  key: string | null = null
  kind: PlaceKind = 'conversation'
  arr: Arr
  from: From = 'product'
  /** when what the Brain keeps for this place was saved; null: never */
  savedAt: number | null = null
  /** what the Brain keeps for this place, as `canon` writes it; null: nothing
   *  saved, or not read yet */
  private savedShape: string | null = null
  private undoStack: Step[] = []
  /** this place's medium and compact records, as this tab has them (P2 keeps
   *  them in the arrangement as `presentations`) */
  devices: Devices = {}
  /** the surfaces closed on this browser device, per class (P5 keeps them in
   *  localStorage, shared by this device's tabs) */
  closed: Record<PresentationClass, ReadonlySet<string>> = { wide: new Set(), medium: new Set(), compact: new Set() }
  /** full screen, this tab only, never saved (the lens is focus/lens.ts's) */
  emphasis: Record<string, SurfaceState['emphasis']> = {}
  /** Wide Make room preview, per tab.  It is drawing state: toLayout/save
   * never consult it, and commit is the only path into arrangement geometry. */
  private displacements: ReadonlyMap<string, Displacement> = new Map()
  /** the place entered has settled: what the Brain keeps for it was asked
   *  and is in force (or this tab's copy is), so a change made now is not
   *  overtaken by it -- what opens a thread window on arrival waits for this */
  ready = false
  private edits = 0
  /** one per arrival: an answer asked for on an earlier visit is not this one's */
  private visit = 0
  private fns = new Set<() => void>()
  private readonly start: (kind: PlaceKind) => Arr
  private readonly onArr?: (a: Arr) => void
  /** the name its kept objects are read again under, when its post changes
   *  (the workspace's, and Home's kept zones: each its own, opr-1da1081bab59) */
  private readonly holds: string | null
  /** an arrangement kept before this place took its present shape, read as
   *  it now is (Home: its conversation column, D1) -- what the Brain keeps is
   *  read so too, so reading it is no change of the reader's */
  private readonly migrate: (a: Arr) => Arr
  /** what goes with the reader from one place to the next (the workspace:
   *  its pinned floats, focus/model.ts): `pick` what travels out of a place,
   *  `bring` the place arrived at with it over it. What travels is the
   *  workspace's, kept in this tab (TRAVEL), never in a place's layout. */
  private readonly carry: { pick: (a: Arr) => Float[]; bring: (a: Arr, left: Arr) => Arr } | null
  private travel: Float[] = []

  constructor(start: (kind: PlaceKind) => Arr, opts: { onArr?: (a: Arr) => void; holds?: string; migrate?: (a: Arr) => Arr
    carry?: { pick: (a: Arr) => Float[]; bring: (a: Arr, left: Arr) => Arr } } = {}) {
    this.start = start
    this.onArr = opts.onArr
    this.holds = opts.holds ?? null
    this.migrate = opts.migrate ?? ((a) => a)
    this.carry = opts.carry ?? null
    if (this.carry) try { this.travel = readTravel(JSON.parse(sessionStorage.getItem(TRAVEL) ?? 'null')) } catch { this.travel = [] }
    this.arr = start('conversation')
  }
  private read(layout: unknown): Arr | null {
    const a = layout ? fromLayout(layout) : null
    return a ? this.migrate(a) : null
  }

  /** Does this tab's arrangement differ from what the Brain keeps (or, with
   *  nothing saved, has the reader changed it)? Save keeps it; until then it
   *  is this tab's. */
  changed = (): boolean => {
    if (this.kind === 'stream' || !this.key) return false
    if (this.savedShape === null) return this.touched
    return canon(toLayout(this.arr)) !== this.savedShape
  }
  /** the reader changed this place in this tab (kept with the tab's copy) */
  private touched = false
  private unknownSavedVersion: number | null = null
  private keepShape(layout: unknown) {
    const o = layout as Record<string, unknown> | null
    if (o && typeof o === 'object' && typeof o.version === 'number' && o.version !== 1 && o.version !== 2) {
      this.unknownSavedVersion = o.version
      this.savedShape = null
      return
    }
    this.unknownSavedVersion = null
    const a = this.read(layout)
    this.savedShape = a ? canon(toLayout(a)) : null
  }

  subscribe = (fn: () => void) => { this.fns.add(fn); return () => { this.fns.delete(fn) } }
  snapshot = () => this.arr
  displacementSnapshot = () => this.displacements
  displace(map: ReadonlyMap<string, Displacement>) {
    this.displacements = new Map(map)
    this.emit()
  }
  clearDisplacements() {
    if (!this.displacements.size) return
    this.displacements = new Map()
    this.emit()
  }
  /** Keep every yielded float as one ordinary arrangement edit/undo step. */
  commitDisplacements(label: string) {
    if (!this.displacements.size) return
    const map = this.displacements
    this.displacements = new Map()
    const before = this.arr
    const next = applyDisplacements(before, map)
    if (next === before) { this.emit(); return }
    this.edit(() => next, label)
  }
  private emit() {
    if (this.holds) store.setHeld([...new Set(allPageViews(this.arr).flatMap(({ view }) => [itemsOf(view.tree),
      ...(view.focus?.column ? [itemsOf(view.focus.column)] : []),
      ...(view.focus?.floats ?? []).map((f) => itemsOf(f.zone))].flat()))], this.holds)
    if (this.carry) {
      this.travel = this.carry.pick(this.arr)
      try { sessionStorage.setItem(TRAVEL, JSON.stringify(this.travel)) } catch { /* private mode: this page only */ }
    }
    this.onArr?.(this.arr)
    this.fns.forEach((fn) => fn())
  }
  private writeSession() {
    if (!this.key) return
    try {
      sessionStorage.setItem(SESSION + this.key, JSON.stringify(toLayout(this.arr, { tab: true })))
      if (this.touched) sessionStorage.setItem(SESSION + this.key + TOUCHED, '1')
      else sessionStorage.removeItem(SESSION + this.key + TOUCHED)
    } catch { /* private mode: this page only */ }
  }
  /** A change the reader made: this tab's until Save. */
  private set(a: Arr) {
    this.arr = a
    this.touched = true
    this.writeSession()
    this.emit()
  }

  /** Arrive at a place: its arrangement as this tab left it, else as saved,
   *  else its kind's default layout, else the product's start. */
  enter(key: string, kind: PlaceKind) {
    if (key === this.key && kind === this.kind) return
    /* What travels comes along over the place arrived at; the place left is
       not touched -- not its tab copy, not what the Brain keeps for it. */
    const going = this.travel
    const bring = (a: Arr) => (this.carry && going.length ? this.carry.bring(a, { tree: a.tree, pages: [], focus: { floats: going } }) : a)
    this.key = key
    this.kind = kind
    this.undoStack = []
    this.devices = {}
    this.closed = { wide: new Set(), medium: new Set(), compact: new Set() }
    this.emphasis = {}
    this.displacements = new Map()
    this.savedAt = null
    this.savedShape = null
    const edits = ++this.edits
    const visit = ++this.visit
    this.ready = kind === 'stream'
    let session: Arr | null = null
    try { session = this.read(JSON.parse(sessionStorage.getItem(SESSION + key) ?? 'null')) } catch { session = null }
    let touched = false
    try { touched = !!session && sessionStorage.getItem(SESSION + key + TOUCHED) === '1' } catch { touched = false }
    this.touched = touched
    const arrived = session ?? this.start(kind)
    this.arr = bring(arrived)
    this.from = session ? 'session' : 'product'
    this.emit()
    if (kind === 'stream') return
    /* What the Brain keeps for this place, and its kind's default. */
    void Promise.all([
      getJson<{ layout: unknown; saved: number | null }>(`arrangements/${encodeURIComponent(key)}`).catch(() => null),
      loadLibrary(),
    ]).then(([saved, lib]) => {
      if (this.visit !== visit) return
      this.ready = true
      this.savedAt = saved?.saved ?? null
      this.keepShape(saved?.layout)
      if (this.unknownSavedVersion !== null) {
        if (session || this.edits !== edits) { this.emit(); return }
        this.emit()
        return
      }
      if (session || this.edits !== edits) { this.emit(); return }
      const got = saved ? this.read(saved.layout) : null
      if (got) { this.arr = bring(got); this.from = 'saved'; this.writeSession(); this.emit(); return }
      const place = kind === 'unnamed' ? 'unnamed' : kind === 'home' ? 'home' : 'conversation'
      const def = defaultOf(lib, place, kind)
      const shaped = def ? this.read(def.layout) : null
      if (shaped) { this.arr = bring(shaped); this.from = 'default'; this.writeSession() }
      this.emit()
    })
  }

  /** One change the reader made: kept in this tab; Undo takes it back. */
  edit(f: (a: Arr) => Arr, words?: string) {
    const before = this.arr
    const next = f(before)
    if (next === before) return
    this.edits += 1
    this.push({ arr: before, devices: this.devices, ...(words ? { label: words } : {}) })
    this.set(next)
    if (words) nav.toast({ text: words, action: { label: 'Undo', run: () => this.undo() } })
  }
  /** While a boundary moves: drawn, not yet a step. `done` makes it one. */
  live(next: Arr, done?: { from: Arr }) {
    this.arr = next
    if (done) {
      this.edits += 1
      this.push({ arr: done.from, devices: this.devices })
      this.set(next)
    } else this.emit()
  }
  /** A change that is no step to undo (a boundary's width, a page's title). */
  quiet(f: (a: Arr) => Arr) {
    const next = f(this.arr)
    if (next !== this.arr) { this.edits += 1; this.set(next) }
  }
  /** A change of travelling state across pages: leaves touched, edits and the undo stack alone. */
  carryOver(f: (a: Arr) => Arr) {
    const next = f(this.arr)
    if (next === this.arr) return
    this.arr = next
    this.writeSession()
    this.emit()
  }
  undo() {
    const prev = this.undoStack.pop()
    if (!prev) return
    this.edits += 1
    this.devices = prev.devices
    /* a class-record step kept the arrangement itself: only the record goes back */
    if (prev.arr !== this.arr) this.set(prev.arr)
    else this.emit()
  }
  canUndo = () => this.undoStack.length > 0
  /** What Undo would take back, in words, when the step was named. */
  undoLabel = (): string | null => this.undoStack[this.undoStack.length - 1]?.label ?? null
  private push(step: Step) { this.undoStack = [...this.undoStack.slice(-(UNDO - 1)), step] }

  /* -- one surface change (Surface Tension §3.3) ----------------------------------- */

  /** The context a surface change is made in: the page shown, the window's
   *  class, this class's record, this device's closed set, this tab's emphasis. */
  surfaceCtx(env: SurfaceEnv = {}): SurfaceCtx {
    const page = env.page !== undefined ? env.page : this === workspace ? shownPage() : THIS_POST
    const cls = env.cls ?? classNow()
    const device = cls === 'wide' ? undefined : this.devices[cls]
    const lensOn = lens.current(page ?? THIS_POST)?.target
    const emphasis = { ...this.emphasis, ...(lensOn?.kind === 'surface' ? { [lensOn.id]: 'lens' as const } : {}) }
    return {
      arr: this.arr, page, cls, ...(device ? { device } : {}), deviceLocal: { closed: this.closed[cls] },
      session: { emphasis }, viewport: env.viewport ?? viewportNow(), caps: capsFor(this.arr, page, cls, device, this.kind),
    }
  }
  /** Change one property of surface `id` (transition.ts) and keep it: an
   *  arrangement or class-record change is ONE undo step named by the
   *  outcome's label. Close/Reopen and full screen are deliberately NOT undo
   *  steps (an accepted departure from the plan's "ONE undo step" seam):
   *  Close/Reopen is this device's local state and emphasis (the lens, full
   *  screen) this tab's session state, neither part of the arrangement Undo
   *  restores; Reopen and Escape are what reverse them. A layout given
   *  instead applies it to this Page, as before. */
  apply(l: Named): void
  apply(id: string, change: Change, env?: SurfaceEnv): Outcome
  apply(a: Named | string, change?: Change, env: SurfaceEnv = {}): Outcome | void {
    if (typeof a !== 'string') return this.applyLayout(a, 'page')
    const ctx = this.surfaceCtx(env)
    const o = transition(ctx, a, change!)
    if (!o.ok) return o
    if (o.layer === 'shared') {
      this.edits += 1
      this.push({ arr: this.arr, devices: this.devices, label: o.label })
      this.set(o.arr)
    } else if (o.layer === 'device' && o.device && ctx.cls !== 'wide') {
      this.edits += 1
      this.push({ arr: this.arr, devices: this.devices, label: o.label })
      this.devices = { ...this.devices, [ctx.cls]: o.device }
      this.emit()
    } else if (o.deviceLocal) {
      this.closed = { ...this.closed, [ctx.cls]: o.deviceLocal.closed }
      this.emit()
    } else if (o.session) {
      /* the lens is the Focus workstream's (focus/lens.ts): entered and
         ended there, read back from there; full screen is kept here */
      const was = ctx.session.emphasis[a] ?? 'none'
      const now = o.session.emphasis[a] ?? 'none'
      this.emphasis = Object.fromEntries(Object.entries(o.session.emphasis).filter(([, v]) => v !== 'lens'))
      if (now === 'lens') lens.enter({ kind: 'surface', id: a })
      else if (was === 'lens') lens.restore()
      this.emit()
    }
    return o
  }

  /* -- the Brain ---------------------------------------------------------------- */

  /** Keep this place's arrangement in the Brain. The answer belongs to the
   *  place it was asked for (opr-6282c50388cb): arriving somewhere else
   *  meanwhile, it marks only that place's own copies; changed since, this
   *  place stays changed. */
  async save() {
    if (!this.key || this.kind === 'stream') throw new Error('the Stream has no saved arrangement')
    if (this.unknownSavedVersion !== null) {
      nav.toast({ text: `Cannot overwrite layout version ${this.unknownSavedVersion}: leaving the saved copy alone.` })
      return
    }
    const key = this.key
    const kind = this.kind
    const visit = this.visit
    const edits = this.edits
    const layout = toLayout(this.arr)
    const got = await postJson<{ saved: number }>(`arrangements/${encodeURIComponent(key)}`, { layout, op: newOp() })
    store.arrangements.set(key, layout)
    const what = kind === 'home' ? 'Home' : 'this arrangement'
    if (this.visit !== visit) {
      /* Left meanwhile: the tab's copy of that place is saved, if it is still what was sent. */
      try {
        const left = fromLayout(JSON.parse(sessionStorage.getItem(SESSION + key) ?? 'null'))
        if (left && canon(toLayout(left)) === canon(layout)) sessionStorage.removeItem(SESSION + key + TOUCHED)
      } catch { /* private mode */ }
      nav.toast({ text: `Saved ${kind === 'home' ? 'Home' : 'the arrangement you left'} in the Brain.` })
      return
    }
    this.savedAt = got.saved
    this.keepShape(layout)
    if (this.edits === edits) {
      this.from = 'saved'
      this.touched = false
    }
    this.writeSession()
    this.emit()
    nav.toast({ text: this.edits === edits
      ? `Saved ${what} in the Brain: it opens like this on any browser.`
      : `Saved ${what} as it was when you pressed Save; what you changed since is still only in this tab.` })
  }
  /** Back to what is saved, this tab's changes let go (Undo brings them back).
   *  An answer that comes back after the reader moved on, or changed the place
   *  again, is let go: it never lands on another place (opr-6282c50388cb). */
  async restoreSaved() {
    if (!this.key) return
    const key = this.key
    const visit = this.visit
    const edits = this.edits
    const got = await getJson<{ layout: unknown; saved: number | null }>(`arrangements/${encodeURIComponent(key)}`)
    if (this.visit !== visit) return
    if (this.edits !== edits) { nav.toast({ text: 'You changed this place while the saved arrangement was read: nothing was restored. Try again.' }); return }
    const o = got.layout as Record<string, unknown> | null
    if (o && typeof o === 'object' && typeof o.version === 'number' && o.version !== 1 && o.version !== 2) {
      nav.toast({ text: `Cannot read layout version ${o.version}: this build reads versions 1 and 2.` })
      return
    }
    const a = this.read(got.layout)
    if (!a) { nav.toast({ text: 'Nothing is saved for this place yet.' }); return }
    this.savedAt = got.saved
    this.keepShape(got.layout)
    this.edit(() => a, 'Restored the saved arrangement.')
    this.from = 'saved'
    this.emit()
  }
  /** Apply a layout to the shown Page, or to every Page in this place. It is
   *  one edit, never a default change, and never discards placed content. */
  applyLayout(l: Named, scope: LayoutScope = 'page') {
    const shape = this.read(l.layout)
    if (!shape) return
    const shown = this === workspace ? shownPage() : 'this-post'
    this.edit((current) => {
      if (scope === 'page') return withPageView(current, shown, layoutPage(pageView(current, shown), shape))
      let next = layoutPage(current, shape)
      const templates = new Map(shape.pages.map((p) => [p.id, pageView(shape, p.id)]))
      next = { ...next, pages: current.pages.map((p) => {
        const view = layoutPage(pageView(current, p.id), templates.get(p.id) ?? shape)
        return { ...p, tree: view.tree, ...(view.focus ? { focus: view.focus } : { focus: undefined }),
          ...(view.setAside?.length ? { setAside: view.setAside } : { setAside: undefined }) }
      }) }
      for (const p of shape.pages) if (!next.pages.some((x) => x.id === p.id)) {
        const fresh = layoutPage(pageView(shape, p.id), pageView(shape, p.id))
        next.pages.push({ ...p, tree: fresh.tree, ...(fresh.focus ? { focus: fresh.focus } : {}),
          ...(fresh.setAside?.length ? { setAside: fresh.setAside } : {}) })
      }
      return {
        ...next,
        ...(shape.conversation ? { conversation: shape.conversation } : {}),
        ...(shape.appearance ? { appearance: shape.appearance } : {}),
        ...(current.threads ? { threads: current.threads } : {}),
      }
    }, `Applied "${l.name}" to ${scope === 'page' ? 'this Page' : 'the whole place'}. Defaults unchanged.`)
    this.from = 'layout'
    this.emit()
  }
  reset() {
    this.edit((x) => keepThreadWindows({ ...this.start(this.kind), ...(x.threads ? { threads: x.threads } : {}) }, x),
      this.kind === 'home' ? 'Home is back as Mentis starts it.' : 'Back to the start: one zone following what you read.')
  }
}

/* -- the conversation's workspace: its holder, and its pages kept with nav -------- */

export const productStart = (): Arr => ({ tree: zone(null, followSlot()), pages: [] })

/** A page's tree as it starts: what it was opened with, kept and shown large;
 *  a blank page asks for something. */
export const pageTree = (object?: string): Node => ({ ...zone(null, keepSlot(object ? [object] : [], object ? 'focus' : 'cards')) })

export const workspace = new Holder(() => productStart(), {
  holds: 'workspace',
  carry: { pick: pagePinnedFloatsOf, bring: carryPinnedFloats },
  onArr: (a) => {
    /* nav's tabs are the place's pages, in its order, with its titles. */
    const want = a.pages.map((p) => ({ id: p.id, title: p.title, ...(p.object ? { object: p.object } : {}) }))
    const have = nav.snapshot().pages.filter((p) => p.id !== 'this-post')
    const same = have.length === want.length && have.every((p, i) => p.id === want[i].id && 'title' in p && p.title === want[i].title)
    if (!same) nav.setPages(want)
    /* ...and its boundaries where the reader left them. */
    if (a.conversation?.width != null) nav.setConvPx(a.conversation.width)
    if (a.conversation?.replies != null) nav.setThreadPx(a.conversation.replies)
  },
})

/* A page nav made (Open as page, +) gets its tree; one nav closed goes. */
nav.subscribe(() => {
  const pages = nav.snapshot().pages.filter((p): p is { id: string; title: string; object?: string } => p.id !== 'this-post')
  const a = workspace.arr
  const ids = new Set(pages.map((p) => p.id))
  const known = new Set(a.pages.map((p) => p.id))
  if (pages.every((p) => known.has(p.id)) && a.pages.every((p) => ids.has(p.id))) return
  workspace.quiet((x) => ({
    ...x,
    pages: pages.map((p) => x.pages.find((q) => q.id === p.id) ?? { id: p.id, title: p.title, ...(p.object ? { object: p.object } : {}), tree: pageTree(p.object) }),
  }))
})

export const useArr = (h: Holder = workspace) => useSyncExternalStore(h.subscribe, h.snapshot)
/** The current drawing-only Make room preview. */
export const useDisplacements = (h: Holder = workspace) => useSyncExternalStore(h.subscribe, h.displacementSnapshot)
/** Is the place changed in this tab since it was saved? */
export const useChanged = (h: Holder = workspace) => useSyncExternalStore(h.subscribe, h.changed)

/** The tree of page `id` in an arrangement. */
export const treeOf = (a: Arr, page: string): Node | null => (page === 'this-post' ? a.tree : a.pages.find((p) => p.id === page)?.tree ?? null)
export const withTree = (a: Arr, page: string, t: Node): Arr =>
  page === 'this-post' ? { ...a, tree: t } : { ...a, pages: a.pages.map((p) => (p.id === page ? { ...p, tree: t } : p)) }
