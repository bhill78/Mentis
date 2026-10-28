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
import { followSlot, freshId, itemsOf, keepSlot, named, valid, zone, type Appearance, type Node, type Zone } from './tree'
import { CONVERSATION_ID, MAX_FLOATS, type FocusArr } from '../focus/types'
import { carryObjectFloats, leaveObjectFloats } from '../focus/model'

export type PlaceKind = 'conversation' | 'unnamed' | 'home' | 'stream'
export interface PageArr { id: string; title: string; object?: string; tree: Node }
export interface Threads { pinned: string[]; active: string | null }
export interface Arr {
  tree: Node; pages: PageArr[]; conversation?: { width?: number; replies?: number }
  /** the place's default look; a zone with its own overrides it */
  appearance?: Appearance
  /** the threads pinned here, in tab order, and the tab shown */
  threads?: Threads
  /** Fluid Focus placement: column content, floating places and history. */
  focus?: FocusArr
}
export type From = 'session' | 'saved' | 'default' | 'product' | 'layout'

const FORMAT = 'mentis.fluid-arrangement'
const FILLS = new Set(['transparent', 'tinted', 'solid'])

export function toLayout(a: Arr): Record<string, unknown> {
  const focus = a.focus ? {
    ...(a.focus.primary && a.focus.primary !== CONVERSATION_ID ? { primary: a.focus.primary } : {}),
    ...(a.focus.column && a.focus.column.id !== CONVERSATION_ID ? { column: a.focus.column } : {}),
    ...(a.focus.floats?.length ? { floats: a.focus.floats } : {}),
    ...(a.focus.previous?.length ? { previous: a.focus.previous.slice(-20) } : {}),
  } : undefined
  return {
    format: FORMAT, version: 1, tree: a.tree,
    ...(a.pages.length ? { pages: a.pages.map((p) => ({ id: p.id, title: p.title, tree: p.tree, ...(p.object ? { object: p.object } : {}) })) } : {}),
    ...(a.conversation && Object.keys(a.conversation).length ? { conversation: a.conversation } : {}),
    ...(a.appearance ? { appearance: a.appearance } : {}),
    ...(a.threads?.pinned.length ? { threads: { pinned: a.threads.pinned, ...(a.threads.active ? { active: a.threads.active } : {}) } } : {}),
    ...(focus && Object.keys(focus).length ? { focus } : {}),
  }
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

function readFocus(v: unknown, tree: Node): FocusArr | undefined {
  const o = v as Record<string, unknown> | null
  if (!o || typeof o !== 'object') return undefined
  const used = new Set(itemsOfIds(tree))
  const column = valid(o.column) && (o.column as Node).type === 'zone' && !used.has((o.column as Zone).id) ? named(o.column as Zone) as Zone : undefined
  if (column) used.add(column.id)
  const floats = Array.isArray(o.floats) ? (o.floats as Record<string, unknown>[]).slice(0, MAX_FLOATS).flatMap((f) => {
    if (!f || typeof f.id !== 'string' || used.has(f.id) || !valid(f.zone) || (f.zone as Node).type !== 'zone') return []
    const z = f.zone as Zone
    if (used.has(z.id) || !['x', 'y', 'w', 'h'].every((k) => typeof f[k] === 'number' && Number.isFinite(f[k] as number))
      || Math.abs(f.x as number) > 100000 || Math.abs(f.y as number) > 100000
      || (f.w as number) < 1 || (f.w as number) > 100000 || (f.h as number) < 1 || (f.h as number) > 100000) return []
    used.add(f.id); used.add(z.id)
    const origin = f.origin as Record<string, unknown> | undefined
    return [{ id: f.id, zone: named(z) as Zone, x: f.x as number, y: f.y as number, w: f.w as number, h: f.h as number,
      ...(origin && typeof origin.near === 'string' && ['left', 'right', 'top', 'bottom'].includes(origin.side as string)
        ? { origin: { near: origin.near, side: origin.side as 'left' | 'right' | 'top' | 'bottom',
          ...(typeof origin.share === 'number' && origin.share >= 0 && origin.share <= 1 ? { share: origin.share } : {}) } } : {}) }]
  }) : []
  const ids = new Set([...itemsOfIds(tree), ...(column ? [column.id] : []), ...floats.map((f) => f.zone.id)])
  const primary = typeof o.primary === 'string' && ids.has(o.primary) && o.primary !== CONVERSATION_ID ? o.primary : undefined
  const previous = Array.isArray(o.previous) ? o.previous.filter((x): x is string => typeof x === 'string').slice(-20) : []
  const out: FocusArr = { ...(primary ? { primary } : {}), ...(column ? { column } : {}), ...(floats.length ? { floats } : {}), ...(previous.length ? { previous } : {}) }
  return Object.keys(out).length ? out : undefined
}
const itemsOfIds = (n: Node): string[] => n.type === 'zone' ? [n.id] : n.kids.flatMap(itemsOfIds)

/** One arrangement's identity, whatever order its keys were written in. */
const canon = (v: unknown): string => JSON.stringify(v, (_k, x) =>
  x && typeof x === 'object' && !Array.isArray(x) ? Object.fromEntries(Object.keys(x).sort().map((k) => [k, x[k]])) : x)

export function fromLayout(l: unknown): Arr | null {
  const o = l as Record<string, unknown> | null
  if (!o || !valid(o.tree)) return null
  const pages = Array.isArray(o.pages)
    ? (o.pages as Record<string, unknown>[]).filter((p) => p && typeof p.id === 'string' && typeof p.title === 'string' && valid(p.tree))
      .map((p) => ({ id: p.id as string, title: p.title as string, tree: named(p.tree as Node), ...(typeof p.object === 'string' ? { object: p.object } : {}) }))
    : []
  const c = o.conversation as Record<string, unknown> | undefined
  const conversation = c && typeof c === 'object'
    ? { ...(typeof c.width === 'number' ? { width: c.width } : {}), ...(typeof c.replies === 'number' ? { replies: c.replies } : {}) }
    : undefined
  const appearance = readLook(o.appearance)
  const threads = readThreads(o.threads)
  const tree = named(o.tree as Node)
  const focus = readFocus(o.focus, tree)
  return { tree, pages, ...(conversation ? { conversation } : {}), ...(appearance ? { appearance } : {}), ...(threads ? { threads } : {}), ...(focus ? { focus } : {}) }
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
  const room = document.getElementById('main')?.getBoundingClientRect().width || window.innerWidth
  return Math.round(Math.max(nav.READABLE, Math.min(room - 300, share * room)))
}
/** A preset as a named layout for one kind of place: Home's half, or the
 *  conversation's with its column's width in this window. */
export function presetLayout(p: Preset, kind: PlaceKind): Named {
  if (kind === 'home') return { id: p.id, name: p.name, layout: p.home }
  return { id: p.id, name: p.name, layout: { ...p.conversation, conversation: { width: presetWidth(p.share) } } }
}
/** What a place kind's default names, a preset's half or a layout kept here. */
export function defaultOf(lib: Library | null, place: DefaultPlace, kind: PlaceKind): Named | null {
  const id = lib?.defaults[place]
  if (!id) return null
  const p = lib?.presets?.find((x) => x.id === id)
  return p ? presetLayout(p, kind) : lib?.layouts.find((l) => l.id === id) ?? null
}
const holders = new Map<string, Holder>()
/** PICKING A PRESET SETS HOME AND THE CONVERSATION VIEW TOGETHER (#1012):
 *  Home takes its half and the conversation open here its other, in this
 *  tab until Save as any layout; every place kind starts from it from now
 *  on. The preset itself is never changed: Save as a layout keeps a copy.
 *  The toast says no more than that (Codex, P12): a place with an
 *  arrangement saved opens as saved in another tab, so it is not "on Home
 *  and in conversations" from now on until that place is saved so. */
export async function usePreset(p: Preset) {
  for (const h of holders.values()) h.usePreset(p)
  await setDefaults(PLACES, p.id)
  nav.toast({ text: `Using "${p.name}" in this tab, and it is now the default: Home and conversations with nothing saved start from it. Where an arrangement is saved, another tab opens it as saved until you Save this one there.` })
}
async function setDefaults(places: DefaultPlace[], layout: string | null) {
  setLibrary(await postJson<Library>('layouts/defaults', { places, layout }))
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
const TOUCHED = ':changed'
const UNDO = 20

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
  private undoStack: Arr[] = []
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
   *  its object floats, focus/model.ts): `leave` is the place as left,
   *  `bring` the place arrived at with what came from `left` */
  private readonly carry: { leave: (a: Arr) => Arr; bring: (a: Arr, left: Arr) => Arr } | null

  constructor(start: (kind: PlaceKind) => Arr, opts: { onArr?: (a: Arr) => void; holds?: string; migrate?: (a: Arr) => Arr
    carry?: { leave: (a: Arr) => Arr; bring: (a: Arr, left: Arr) => Arr } } = {}) {
    this.start = start
    this.onArr = opts.onArr
    this.holds = opts.holds ?? null
    this.migrate = opts.migrate ?? ((a) => a)
    this.carry = opts.carry ?? null
    this.arr = start('conversation')
    if (this.holds) holders.set(this.holds, this)
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
  private keepShape(layout: unknown) {
    const a = this.read(layout)
    this.savedShape = a ? canon(toLayout(a)) : null
  }

  subscribe = (fn: () => void) => { this.fns.add(fn); return () => { this.fns.delete(fn) } }
  snapshot = () => this.arr
  private emit() {
    if (this.holds) store.setHeld([...new Set([itemsOf(this.arr.tree), ...this.arr.pages.map((p) => itemsOf(p.tree)),
      ...(this.arr.focus?.floats ?? []).map((f) => itemsOf(f.zone))].flat())], this.holds)
    this.onArr?.(this.arr)
    this.fns.forEach((fn) => fn())
  }
  private writeSession() {
    if (!this.key) return
    try {
      sessionStorage.setItem(SESSION + this.key, JSON.stringify(toLayout(this.arr)))
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
    /* What goes with the reader leaves the place left, in this tab's copy of
       it, so it is in one place: the one shown (fq2 A3). */
    const left = this.carry && this.key ? this.arr : null
    if (left && this.key) {
      const stays = this.carry!.leave(left)
      if (stays !== left) try { sessionStorage.setItem(SESSION + this.key, JSON.stringify(toLayout(stays))) } catch { /* private mode */ }
    }
    const bring = (a: Arr) => (left ? this.carry!.bring(a, left) : a)
    this.key = key
    this.kind = kind
    this.undoStack = []
    this.savedAt = null
    this.savedShape = null
    const edits = ++this.edits
    const visit = ++this.visit
    let session: Arr | null = null
    try { session = this.read(JSON.parse(sessionStorage.getItem(SESSION + key) ?? 'null')) } catch { session = null }
    let touched = false
    try { touched = !!session && sessionStorage.getItem(SESSION + key + TOUCHED) === '1' } catch { touched = false }
    this.touched = touched
    const arrived = session ?? this.start(kind)
    this.arr = bring(arrived)
    this.from = session ? 'session' : 'product'
    /* what came along is this tab's copy of the place now, so a reload keeps it */
    if (this.arr !== arrived) this.writeSession()
    this.emit()
    if (kind === 'stream') return
    /* What the Brain keeps for this place, and its kind's default. */
    void Promise.all([
      getJson<{ layout: unknown; saved: number | null }>(`arrangements/${encodeURIComponent(key)}`).catch(() => null),
      loadLibrary(),
    ]).then(([saved, lib]) => {
      if (this.visit !== visit) return
      this.savedAt = saved?.saved ?? null
      this.keepShape(saved?.layout)
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
    this.undoStack = [...this.undoStack.slice(-(UNDO - 1)), before]
    this.set(next)
    if (words) nav.toast({ text: words, action: { label: 'Undo', run: () => this.undo() } })
  }
  /** While a boundary moves: drawn, not yet a step. `done` makes it one. */
  live(next: Arr, done?: { from: Arr }) {
    this.arr = next
    if (done) {
      this.edits += 1
      this.undoStack = [...this.undoStack.slice(-(UNDO - 1)), done.from]
      this.set(next)
    } else this.emit()
  }
  /** A change that is no step to undo (a boundary's width, a page's title). */
  quiet(f: (a: Arr) => Arr) {
    const next = f(this.arr)
    if (next !== this.arr) { this.edits += 1; this.set(next) }
  }
  undo() {
    const prev = this.undoStack.pop()
    if (!prev) return
    this.edits += 1
    this.set(prev)
  }
  canUndo = () => this.undoStack.length > 0

  /* -- the Brain ---------------------------------------------------------------- */

  /** Keep this place's arrangement in the Brain. The answer belongs to the
   *  place it was asked for (opr-6282c50388cb): arriving somewhere else
   *  meanwhile, it marks only that place's own copies; changed since, this
   *  place stays changed. */
  async save() {
    if (!this.key || this.kind === 'stream') throw new Error('the Stream has no saved arrangement')
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
    const a = this.read(got.layout)
    if (!a) { nav.toast({ text: 'Nothing is saved for this place yet.' }); return }
    this.savedAt = got.saved
    this.keepShape(got.layout)
    this.edit(() => a, 'Restored the saved arrangement.')
    this.from = 'saved'
    this.emit()
  }
  /** A named layout, used here: its shape, rules and look, nothing it held --
   *  so the threads pinned here stay pinned. */
  apply(l: Named) {
    const a = this.read(l.layout)
    if (!a) return
    this.edit((x) => ({ ...a, ...(x.threads ? { threads: x.threads } : {}) }), `Using the layout "${l.name}".`)
    this.from = 'layout'
    this.emit()
  }
  /** A preset's half for this holder's place. Home is always one place, so
   *  a Home not open now takes it in this tab's copy, read when it is
   *  arrived at; a conversation not open now starts from it as its default. */
  usePreset(p: Preset) {
    if (this.key && this.kind !== 'stream' && (this.kind === 'home') === (this.holds === 'home')) {
      this.apply(presetLayout(p, this.kind))
      return
    }
    if (this.holds !== 'home') return
    const a = this.read(p.home)
    if (!a) return
    try {
      sessionStorage.setItem(SESSION + 'home', JSON.stringify(toLayout(a)))
      sessionStorage.setItem(SESSION + 'home' + TOUCHED, '1')
    } catch { /* private mode: Home takes it when it is next open */ }
  }
  reset() {
    this.edit((x) => ({ ...this.start(this.kind), ...(x.threads ? { threads: x.threads } : {}) }),
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
  carry: { leave: leaveObjectFloats, bring: carryObjectFloats },
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
/** Is the place changed in this tab since it was saved? */
export const useChanged = (h: Holder = workspace) => useSyncExternalStore(h.subscribe, h.changed)

/** The tree of page `id` in an arrangement. */
export const treeOf = (a: Arr, page: string): Node | null => (page === 'this-post' ? a.tree : a.pages.find((p) => p.id === page)?.tree ?? null)
export const withTree = (a: Arr, page: string, t: Node): Arr =>
  page === 'this-post' ? { ...a, tree: t } : { ...a, pages: a.pages.map((p) => (p.id === page ? { ...p, tree: t } : p)) }
