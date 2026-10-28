/* THE FOCUS LENS, KEPT PER PAGE AND NEVER SAVED (focus/lens.ts is the
 * interface; compose.ts the pure rules; LensLayer.tsx draws it).
 *
 * One lens per Page shown. Entering Focus notes where the windows are
 * (Restore puts exactly that back) and writes nothing; switching, stepping
 * back and forward, presentations, Tidy around Focus, Hide other windows and
 * revealing what Only Focus hides are all the lens's own state. Restore puts
 * the windows back quietly (no step to undo: nothing of Focus was a step);
 * Keep this layout is one ordinary `workspace.edit`, with Undo.
 *
 * This module also provides, to objects/actions.ts, the three actions that
 * are the Focus workstream's: Peek (present/viewer.tsx), Make primary (an
 * object floats beside its card and swaps in, as one step) and Focus. */

import { useSyncExternalStore } from 'react'
import * as nav from '../nav'
import { isNarrow } from '../frame/narrow'
import { workspace } from '../workspace/place'
import { floatIt, floatRectFor, floatTitle } from '../workspace/keep'
import { provide, type ObjectTarget } from '../objects/actions'
import { peek } from '../present/viewer'
import { provideLens, rememberPresentation, rememberedPresentation, type FocusPresentation, type FocusTarget, type LensImpl } from './lens'
import { backLens, compose, forwardLens, keepArr, restoreArr, sameTarget, shapeOf, startLens, surfacesOf, switchLens, targetExists, tidyInBand, type Lens, type Room } from './compose'
import { floatObject, locate, makePrimary, objectFloatsOf, primaryOf } from './model'
import { onPage, pageIn, pageView, shownPage } from './page'

const lenses = new Map<string, Lens>()
const fns = new Set<() => void>()
const emit = () => fns.forEach((fn) => fn())
const subscribe = (fn: () => void) => { fns.add(fn); return () => { fns.delete(fn) } }

/** The lens on `page`, as React reads it. */
export const useLens = (page: string): Lens | null => useSyncExternalStore(subscribe, () => lenses.get(page) ?? null)
export const lensOf = (page: string = here()): Lens | null => lenses.get(page) ?? null
const here = () => pageIn(workspace.arr, shownPage())

/* The main area as last drawn (LensLayer reports it): Keep this layout and
   Tidy around Focus need the geometry the owner sees. */
let room: Room = { w: 1200, h: 800 }
export function setLensRoom(r: Room) { if (r.w > 0 && r.h > 0) room = r }

function set(page: string, L: Lens | null) {
  if (L) lenses.set(page, L)
  else lenses.delete(page)
  emit()
}
const titleOfTarget = (t: FocusTarget, page: string): string => {
  if (t.title) return t.title
  if (t.kind === 'surface') return locate(pageView(workspace.arr, page), t.id)?.zone.name ?? 'Section'
  return floatTitle(t.address)
}
export const lensTitle = titleOfTarget
const exists = (page: string) => (t: FocusTarget) => targetExists(pageView(workspace.arr, page), t)

function restore(page: string = here()) {
  const L = lenses.get(page)
  if (!L) return
  lenses.delete(page)
  workspace.quiet(onPage((v) => restoreArr(v, L.entry), page))
  emit()
}

const impl: LensImpl = {
  enter(target, presentation) {
    const page = here()
    if (presentation) rememberPresentation(presentation)
    const L = lenses.get(page)
    if (L) {
      const next = switchLens(L, target)
      set(page, presentation && presentation !== L.presentation ? { ...next, presentation } : next)
      return
    }
    set(page, startLens(pageView(workspace.arr, page), page, target, presentation ?? rememberedPresentation()))
  },
  setPresentation(p) {
    rememberPresentation(p)
    const page = here(), L = lenses.get(page)
    if (L && L.presentation !== p) set(page, { ...L, presentation: p, reveal: false })
    else emit()
  },
  /* Esc: one step back through this Page's Focus history; at its start, out
     of Focus to the arrangement as it was. */
  stepBack() {
    const page = here(), L = lenses.get(page)
    if (!L) return false
    const back = backLens(L, exists(page))
    if (back) set(page, back)
    else restore(page)
    return true
  },
  restore: () => restore(),
  keepLayout() {
    const page = here(), L = lenses.get(page)
    if (!L) return
    const c = compose(room, shapeOf(L, false))
    const title = titleOfTarget(L.target, page)
    lenses.delete(page)
    workspace.edit(onPage((v) => keepArr(v, L, c, title), page), `Kept this layout: ${title} is primary. Undo returns the arrangement before.`)
    emit()
  },
  current: (page) => lenses.get(page ?? here()) ?? null,
  subscribe,
}
provideLens(impl)

/** › in the Focus bar. */
export function stepForward(): boolean {
  const page = here(), L = lenses.get(page)
  const next = L && forwardLens(L, exists(page))
  if (next) set(page, next)
  return !!next
}
/** The lens's own reversible toggles. */
export function update(fn: (L: Lens) => Lens, page: string = here()) {
  const L = lenses.get(page)
  if (L) set(page, fn(L))
}
export const toggleHide = () => update((L) => ({ ...L, hideOthers: !L.hideOthers }))
export const toggleReveal = (on?: boolean) => update((L) => ({ ...L, reveal: on ?? !L.reveal }))
/** Tidy around Focus: the windows aligned in a band beside the Focus area;
 *  again, back where they were. Their saved rectangles are untouched. */
export function toggleTidy() {
  update((L) => {
    if (L.tidy) return { ...L, tidy: null }
    const c = compose(room, { ...shapeOf(L, false), tidy: true })
    if (!c.band) return L
    const fs = (pageView(workspace.arr, L.page).focus?.floats ?? []).filter((f) => !(L.target.kind === 'surface' && f.zone.id === L.target.id))
    return { ...L, tidy: tidyInBand(fs, c.band) }
  })
}
/** A tidied window taken by its title or corner: it is where it is drawn
 *  from now on, so the move starts there. */
export function adoptTidied(floatId: string, page: string = here()): void {
  const L = lenses.get(page), r = L?.tidy?.[floatId]
  if (!L || !r) return
  const { [floatId]: _gone, ...tidy } = L.tidy!
  lenses.set(page, { ...L, tidy })
  workspace.quiet(onPage((v) => ({ ...v, focus: { ...v.focus, floats: (v.focus?.floats ?? []).map((f) => f.id === floatId ? { ...f, ...r } : f) } }), page))
  emit()
}

/* -- staying honest about the Page ------------------------------------------ */
/* A target that is gone (its section closed, its window closed) ends the
   lens; another conversation ends them all (its Pages are other Pages). */
let busy = false
workspace.subscribe(() => {
  if (busy || !lenses.size) return
  busy = true
  try {
    for (const [page, L] of [...lenses]) {
      const v = pageView(workspace.arr, page)
      if (!targetExists(v, L.target)) { lenses.delete(page); emit() }
    }
  } finally { busy = false }
})
let conversation = nav.snapshot().conversation
nav.subscribe(() => {
  const c = nav.snapshot().conversation
  if (c === conversation) return
  conversation = c
  if (lenses.size) { lenses.clear(); emit() }
})

/* -- the object actions that are Focus's ------------------------------------- */

/** MAKE PRIMARY FOR AN OBJECT, IN ONE STEP: it floats beside its card and
 *  trades places with Primary (model.ts makePrimary), as one edit. Already
 *  floating on this Page, that window is swapped in. Focus is left first:
 *  ◎ swaps places in the arrangement, which Focus never writes. */
export function primaryObject(t: ObjectTarget) {
  const page = here()
  if (lenses.has(page)) restore(page)
  const title = t.title ?? floatTitle(t.address)
  const v = pageView(workspace.arr, page)
  const old = locate(v, primaryOf(v))?.zone.name ?? 'Conversation'
  const shown = objectFloatsOf(v).find((f) => f.zone.slot?.items[0] === t.address)
  if (shown) {
    workspace.edit(onPage((x) => makePrimary(x, shown.zone.id), page), `${title} is primary. ${old} floats where it was — ◎ on that window swaps back.`)
    return
  }
  const rect = floatRectFor(t.address, t.anchor ?? null)
  workspace.edit(onPage((x) => {
    const before = new Set((x.focus?.floats ?? []).map((f) => f.id))
    const floated = floatObject(x, t.address, title, rect, undefined, t.from)
    const made = floated.focus?.floats?.find((f) => !before.has(f.id))
    return made ? makePrimary(floated, made.zone.id) : x
  }, page), `${title} is primary. ${old} floats where it was — ◎ on that window swaps back.`)
}

/** Focus an object: the Page's Focus area, in the remembered presentation
 *  (or the one already on). On a narrow screen it is Only Focus. */
export function focusObject(t: ObjectTarget, presentation?: FocusPresentation) {
  impl.enter({ kind: 'object', address: t.address, title: t.title, from: t.from }, presentation)
}

/** Focus a surface on the Page by its content id. */
export function focusSurface(id: string, title?: string, presentation?: FocusPresentation) {
  impl.enter({ kind: 'surface', id, title }, presentation)
}

/** Is `t` what Focus is on, on the Page shown? */
export const isFocused = (t: FocusTarget) => sameTarget(lensOf()?.target, t)

provide({
  peek: (t) => peek(t),
  /* narrow, there is one column and no windows to swap with: it is listed
     with the workspace's floats, as before */
  primary: (t) => (isNarrow() ? floatIt(t.address, t.anchor ?? null, t.from) : primaryObject(t)),
  focus: (t) => focusObject(t),
})

/** Every surface of the Page shown, in the shelf's order (the 1-9 keys). */
export const surfacesHere = () => surfacesOf(pageView(workspace.arr, here()))
