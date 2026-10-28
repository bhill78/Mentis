/* A PAGE'S ZONES, DRAWN AND SHAPED (Fluid completion, stream A; #1, #156,
 * #187 #6, #188 "boundaries are for space, edges for structure").
 *
 * The tree is laid out into the space it has; every gutter between two
 * zones is a boundary the reader drags, sideways or up and down, or moves
 * with the arrow keys, and while it moves it says the sizes it gives. Each
 * side stops at its minimum -- but dragged on past it, a zone closes: let go
 * there and it MERGES into the zone beside it (what it kept comes along),
 * with Undo. Too narrow for the tree, the zones stack in order. Shared
 * by every workspace page and by Home: what a zone holds is the caller's
 * (`renderZone`); the tree's shape is this file's.
 *
 * A ZONE MINIMIZED TO A RAIL GIVES ITS ROOM BACK (`dock`, Home's
 * conversation): it is drawn at the rail's width at the nearer end of its
 * row and the zones beside it take the rest (tree.ts `docked`). What is kept
 * is the tree as it was; a boundary moved among the others is read back into
 * it (`undocked`). The boundary beside the rail opens it: pressed, Enter or
 * the arrow away from the edge, or dragged out to the width it reads at.
 * Such a zone is never MERGED by a drag (adm-07db9ae51efc): dragged narrower
 * than it reads, the readout says it will be minimized to the rail, and
 * letting go leaves it there -- the rail, with Undo; its close is on it. */

import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { armTouchDrag, beginDrag, pulseArrived } from '../focus/drag'
import { floatOut, makePrimary, primaryOf, swapBack } from '../focus/model'
import { workspace } from './place'
import {
  bounds, canMerge, canSplit, closeZone, docked, docks, even, fixedOf, foldedHeight, GUTTER, keepShare, mergeZone, MIN_H, MIN_W, minSize, place, resize, splitZone, undocked, whyNoSplit, widenZone, wrapped, wrapFits, zones,
  type Dock, type Folded, type Node, type Rect, type Split, type Zone,
} from './tree'
import { asDrawn, fitAxes, fitMeasureKey, setFit, type Natural } from './tree'
import './tree.css'

export interface ZoneCtl {
  /** content id, and Fluid Focus actions when this is a focusable place */
  id?: string
  focus?: () => void
  float?: () => void
  drag?: (e: React.PointerEvent<HTMLElement>) => void
  stacked: boolean
  /** it is as wide as the page: stacked, or nothing shares its row */
  across: boolean
  canSplitRow: boolean
  canSplitCol: boolean
  /** why it cannot be split that way, said where Split is offered */
  whyNoSplitRow: string | null
  whyNoSplitCol: string | null
  canMerge: boolean
  canClose: boolean
  split: (dir: 'row' | 'col') => void
  merge: () => void
  close: () => void
  /** this zone is being dragged closed: let go and it merges */
  closing: boolean
  /** make it at least `px` across, taking the room from the zones beside it
   *  in its row (`widenZone`), as one step with Undo; false when they have
   *  not that much to give, or nothing shares its row */
  widen: (px: number) => boolean
  /** drawn as a rail at the edge of its row (`dock`) */
  docked: boolean
  /** Fit to content: sized to what it holds along its split (`Zone.fit`) */
  fit: boolean
  /** Fit to content on or off, as one step with Undo */
  toggleFit: () => void
}

/** A zone drawn as a rail while it is narrower than `below`: `w` across, at
 *  the nearer end of its row (Home's conversation). */
export interface DockRule { is: (z: Zone) => boolean; w: number; below: number }

/** How far past a minimum a divider is dragged before the zone closes. */
const CLOSE_PAST = 56

const NO_ROOM = 'No room to open it here: the zones beside it are at their least'

export default function Tree({ tree, onEdit, onLive, renderZone, label, made, canCloseLast = false, page, folded, wrap = false, keepWide, dock }: {
  tree: Node
  /** one step: the tree's next shape, said in `words` (with Undo) */
  onEdit: (f: (t: Node) => Node, words?: string) => void
  /** while a divider moves; `done` makes the move one step */
  onLive: (t: Node, done?: { from: Node }) => void
  renderZone: (z: Zone, r: Rect, ctl: ZoneCtl) => ReactNode
  label: string
  /** the zone a split makes (by default one following what is read) */
  made?: (t: Node) => Zone
  canCloseLast?: boolean
  page?: string
  /** a zone that needs only so much height, and how much (Home) */
  folded?: Folded
  /** a row too full for the width wraps in its own space, and only it (Home) */
  wrap?: boolean
  /** how wide a zone stays when it is split side by side, the new zone
   *  taking the rest (Home's conversation, READABLE); 0: halves */
  keepWide?: (z: Zone) => number
  /** a zone too narrow to read drawn as a rail at its row's edge (Home) */
  dock?: DockRule
}) {
  const box = useRef<HTMLDivElement>(null)
  const cellEls = useRef(new Map<string, HTMLDivElement>())
  const lastCells = useRef(new Map<string, DOMRect>())
  const [size, setSize] = useState({ w: 0, h: 0 })
  useLayoutEffect(() => {
    const el = box.current
    if (!el) return
    const measure = () => setSize((s) => (s.w === el.clientWidth && s.h === el.clientHeight ? s : { w: el.clientWidth, h: el.clientHeight }))
    const ro = new ResizeObserver(measure)
    ro.observe(el)
    measure()
    return () => ro.disconnect()
  }, [])
  useLayoutEffect(() => {
    const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches
    const next = new Map<string, DOMRect>()
    for (const [id, el] of cellEls.current) {
      const now = el.getBoundingClientRect(), was = lastCells.current.get(id)
      next.set(id, now)
      if (!reduce && was && Math.abs(was.left - now.left) + Math.abs(was.top - now.top) + Math.abs(was.width - now.width) + Math.abs(was.height - now.height) > 2)
        el.animate([
          { left: `${was.left - (box.current?.getBoundingClientRect().left ?? 0)}px`, top: `${was.top - (box.current?.getBoundingClientRect().top ?? 0)}px`, width: `${was.width}px`, height: `${was.height}px` },
          { left: `${now.left - (box.current?.getBoundingClientRect().left ?? 0)}px`, top: `${now.top - (box.current?.getBoundingClientRect().top ?? 0)}px`, width: `${now.width}px`, height: `${now.height}px` },
        ], { duration: 460, easing: 'cubic-bezier(.2,.75,.2,1)' })
    }
    lastCells.current = next
  })
  useEffect(() => {
    if (page !== 'this-post') return
    const key = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement | null
      if (t?.closest('input,textarea,select,[contenteditable=true],[role=dialog],.sheet')) return
      if (e.key === 'Escape') { const next = swapBack(workspace.arr); if (next !== workspace.arr) { e.preventDefault(); workspace.edit(() => next, 'Returned to the previous primary.'); } return }
      if (/^[1-9]$/.test(e.key)) { const z = zones(workspace.arr.tree)[Number(e.key) - 1]; if (z) { e.preventDefault(); workspace.edit((a) => makePrimary(a, z.id), `${z.name ?? 'The section'} is primary.`) } }
    }
    window.addEventListener('keydown', key)
    return () => window.removeEventListener('keydown', key)
  }, [page])
  /* FIT TO CONTENT (DESIGN.md 4): what each fitted zone measures, along its
     split's axis, kept as it was last read from its cell (`measureFit`,
     below); `paused`: zones a divider is sizing by hand right now, which take
     their share while it moves. */
  const [nat, setNat] = useState<Map<string, Measured>>(() => new Map())
  const paused = useRef<Set<string>>(new Set())
  const natural = useCallback<Natural>((z, axis) => (z.fit && !paused.current.has(z.id) ? nat.get(z.id)?.[axis] ?? null : null), [nat])
  /* A tree that does not fit across (a narrow window, the narrow sheet) is
     shown as an ordered stack, in its own order -- and never rewritten: the
     arrangement is the same one, laid out again when there is room. With
     `wrap` that is only for a width narrower than its widest zones: a row
     that is merely too full wraps, and the rest keeps its shape. */
  /* `kept`: where each node sits in the tree as kept; `rects`, as drawn --
     the same, but for a zone docked as a rail (`ds`), drawn from `drawn`. */
  const { stacked, kept, rects, ds, drawn, fixed } = useMemo(() => {
    const none = { ds: [] as Dock[], drawn: tree, fixed: undefined as Map<string, number> | undefined }
    if (!size.w || !size.h) return { stacked: false, kept: new Map<Node, Rect>(), rects: new Map<Node, Rect>(), ...none }
    const box = { x: 0, y: 0, w: size.w, h: size.h }
    const laid = tree.type === 'split' && size.w >= minSize(tree, 'w', wrap)
      ? place(tree, box, undefined, folded, wrap, undefined, natural) : null
    if (tree.type !== 'split' || (laid && wrapFits(tree, laid))) {
      const kept = laid ?? place(tree, box, undefined, folded, wrap, undefined, natural)
      const ds = dock ? docks(tree, kept, (z, r) => (dock.is(z) && r.w < dock.below ? dock.w : null)) : []
      if (!ds.length) return { stacked: false, kept, rects: kept, ...none }
      const drawn = docked(tree, ds, kept)
      const fixed = fixedOf(ds)
      return { stacked: false, kept, rects: place(drawn, box, undefined, folded, wrap, fixed, natural), ds, drawn, fixed }
    }
    /* stacked, a fitted zone is as tall as it measures, within reason */
    const fits = (z: Zone) => { const v = natural(z, 'h', size.w); return v === null ? null : Math.max(MIN_H, Math.min(STACKED_FIT_MAX, v)) }
    const rects = new Map<Node, Rect>(zones(tree).map((z) => [z, { x: 0, y: 0, w: size.w, h: folded?.(z, size.w) ?? fits(z) ?? Math.max(MIN_H * 2, size.h / 2) }]))
    return { stacked: true, kept: rects, rects, ...none }
  }, [tree, size, folded, wrap, dock, natural])
  /** a drawn tree's edit, as the tree kept */
  const back = (from: Node, n: Node) => (ds.length ? undocked(from, n, ds) : n)
  const all = zones(tree)
  const nameOf = (n: Node) => zones(n)[0]?.name ?? 'zone'

  /* -- a divider moving ----------------------------------------------------- */
  /* `closing` is the side that goes; `into` the zone that takes what it kept
     (when the other side is itself split, the zone of it nearest the
     pointer); `blocked`: dragged past a side that is itself split, which no
     single merge can close -- the readout says so, and letting go only sizes. */
  const [moving, setMoving] = useState<{
    split: Split; i: number; a: number; b: number; closing: 'a' | 'b' | null; into: Zone | null; blocked: string | null; key: string; text?: string
  } | null>(null)
  const [said, setSaid] = useState<{ key: string; a: number; b: number; text?: string } | null>(null)
  useEffect(() => { if (!said) return; const t = setTimeout(() => setSaid(null), 1600); return () => clearTimeout(t) }, [said])
  /* A drag under way ends when the pointer is cancelled (a touch taken by
     the browser, a lost capture) or the tree goes (opr-52e4899752df). */
  const endDrag = useRef<(() => void) | null>(null)
  useEffect(() => () => endDrag.current?.(), [])

  /* -- fit to content, measured ----------------------------------------------- */
  /* Each fitted zone is read from its cell once it is fitted, moves place,
     or the window changes size: through rAF, never while a divider moves or
     a cell animates (no oscillation). A reading that only
     followed the zone's own size -- content drawn to fill it -- is not
     taken, so a fitted zone never grows itself. */
  const axes = useMemo(() => fitAxes(drawn, stacked), [drawn, stacked])
  const fitKey = fitMeasureKey(drawn, stacked)
  const movingNow = useRef(false)
  movingNow.current = !!moving
  const measureFit = useRef<() => void>(() => {})
  measureFit.current = () => {
    const root = box.current
    if (!root || !axes.size) return
    let next: Map<string, Measured> | null = null
    for (const [id, axis] of axes) {
      const cell = cellOf(root, id)
      const v = cell ? naturalOf(cell, axis) : null
      if (!cell || v === null) continue
      const at = axis === 'w' ? cell.offsetWidth : cell.offsetHeight
      const was = (next ?? nat).get(id)
      const prev = was?.[axis]
      const prevAt = axis === 'w' ? was?.atW : was?.atH
      if (prev !== undefined && Math.abs(v - prev) < 2) continue
      if (prev !== undefined && prevAt !== undefined && Math.abs(at - prevAt) > 1 && Math.abs(v - prev - (at - prevAt)) < 2) continue
      next ??= new Map(nat)
      next.set(id, axis === 'w' ? { ...was, w: v, atW: at } : { ...was, h: v, atH: at })
    }
    if (next) setNat(next)
  }
  const frame = useRef(0)
  const later = useRef(0)
  const scheduleFit = useCallback(() => {
    cancelAnimationFrame(frame.current)
    clearTimeout(later.current)
    frame.current = requestAnimationFrame(() => {
      if (movingNow.current) return
      const root = box.current
      const busy = root && Array.from(root.children).some((c) => c.classList.contains('wt-cell') && c.getAnimations?.().some((a) => a.playState === 'running'))
      if (busy) { later.current = window.setTimeout(() => scheduleFit(), 120); return }
      measureFit.current()
    })
  }, [])
  useEffect(() => () => { cancelAnimationFrame(frame.current); clearTimeout(later.current) }, [])
  /* Fit is for a zone taking a new place (DESIGN.md 4, owner fq2 E): read
     again when it is fitted or moves, or when the window really changes --
     not when a swap elsewhere nudges the workspace by a scrollbar. */
  const fitAt = useRef<{ key: string; w: number; h: number } | null>(null)
  useLayoutEffect(() => {
    if (!fitKey || moving) return
    const was = fitAt.current
    if (was && was.key === fitKey && Math.abs(was.w - size.w) < 40 && Math.abs(was.h - size.h) < 40) return
    fitAt.current = { key: fitKey, w: size.w, h: size.h }
    scheduleFit()
  }, [fitKey, size.w, size.h, moving, scheduleFit])
  /* A fitted zone beside a divider sized by hand stops fitting (the
     prototype's `unfit`): the fitted kids of `split` at `idx`. */
  const fittedAt = (split: Split, idx: number[]) =>
    idx.map((j) => split.kids[j]).filter((k): k is Zone => !!k && k.type === 'zone' && !!k.fit)
  const unfitWords = (off: Zone[]) => `Fit to content is off for ${off.map((z) => z.name ?? 'the zone').join(' and ')}: you sized it.`

  const startDrag = (e: React.PointerEvent, split: Split, i: number, key: string, held = false) => {
    if (e.button !== 0) return
    if (!held && armTouchDrag(e, e.currentTarget as HTMLElement, () => startDrag(e, split, i, key, true))) return
    e.preventDefault()
    endDrag.current?.()
    const row = split.dir === 'row'
    const r0 = rects.get(split.kids[i])
    if (!r0) return
    const p0 = row ? e.clientX : e.clientY
    const s0 = row ? r0.w : r0.h
    const from = tree
    const start = drawn
    const rects0 = rects
    const origin = box.current?.getBoundingClientRect() ?? { left: 0, top: 0 }
    let cur = drawn
    let curSplit = split
    let closing: 'a' | 'b' | null = null
    let into: Zone | null = null
    let minimizing: string | null = null
    /* A fitted zone beside it is sized by hand from where it is drawn, and
       stops fitting once it moves. */
    const off = fittedAt(split, [i, i + 1])
    if (off.length) { const d = asDrawn(drawn, split, rects); cur = d.tree; curSplit = d.split; paused.current = new Set(off.map((z) => z.id)) }
    const sized = cur
    const settle = (t: Node) => (off.length ? setFit(t, off.map((z) => z.id), false) : t)
    const { lo, hi: hi0, along } = bounds(split, i, rects, wrap)
    const total = (curSplit.sizes[i] + curSplit.sizes[i + 1]) * along
    const hi = off.length ? total - minSize(split.kids[i + 1], row ? 'w' : 'h', wrap) : hi0
    /* A zone drawn as the rail when narrow (`dock`) is not closed by a drag
       across: it is minimized, never merged. */
    const rails = (n: Node): n is Zone => row && n.type === 'zone' && !!dock?.is(n)
    /* The zone that takes what a closing side kept: the other side, or, when
       it is split, its zone along the divider nearest the pointer. */
    const takerOf = (side: Node, ev: PointerEvent): Zone | null => {
      if (side.type === 'zone') return side
      const sr = rects0.get(side)
      if (!sr) return null
      const atStart = side === split.kids[i + 1]
      const edge = (r: Rect) => (row ? (atStart ? r.x : r.x + r.w) : (atStart ? r.y : r.y + r.h))
      const want = edge(sr)
      const onEdge = zones(side).map((z) => ({ z, r: rects0.get(z) })).filter((x): x is { z: Zone; r: Rect } => !!x.r && Math.abs(edge(x.r) - want) < 1)
      const c = row ? ev.clientY - origin.top : ev.clientX - origin.left
      const gap = (r: Rect) => { const a = row ? r.y : r.x; const b = a + (row ? r.h : r.w); return c < a ? a - c : c > b ? c - b : 0 }
      return onEdge.sort((p, q) => gap(p.r) - gap(q.r))[0]?.z ?? null
    }
    const mv = (ev: PointerEvent) => {
      if (ev.pointerType !== 'mouse') ev.preventDefault()
      const want = s0 + ((row ? ev.clientX : ev.clientY) - p0)
      const past = want < lo - CLOSE_PAST ? 'a' : want > hi + CLOSE_PAST ? 'b' : null
      const gone = past ? (past === 'a' ? split.kids[i] : split.kids[i + 1]) : null
      closing = gone?.type === 'zone' && !rails(gone) ? past : null
      into = closing ? takerOf(closing === 'a' ? split.kids[i + 1] : split.kids[i], ev) : null
      if (closing && !into) closing = null
      const blocked = gone && gone.type === 'split' ? zones(gone).map((z) => z.name ?? 'zone').join(' and ') : null
      const live = place(cur, { x: 0, y: 0, w: size.w, h: size.h }, undefined, folded, wrap, fixed, natural)
      const res = resize(cur, curSplit, i, want, live, wrap)
      cur = res.tree
      curSplit = res.split
      onLive(back(from, cur))
      const a = Math.max(lo, Math.min(hi, want))
      const rail = rails(split.kids[i]) ? { z: split.kids[i] as Zone, w: a } : rails(split.kids[i + 1]) ? { z: split.kids[i + 1] as Zone, w: total - a } : null
      minimizing = dock && rail && (rail.w < dock.below || gone === rail.z) ? nameOf(rail.z) : null
      const text = minimizing ? `Let go to minimize ${minimizing} to the rail` : undefined
      setMoving({ split: curSplit, i, a, b: total - a, closing, into, blocked: rail && gone === rail.z ? null : blocked, key, text })
    }
    const stop = () => {
      window.removeEventListener('pointermove', mv)
      window.removeEventListener('pointerup', up)
      window.removeEventListener('pointercancel', cancel)
      endDrag.current = null
      paused.current = new Set()
    }
    /* Cancelled: back as it was, no step taken. */
    const cancel = () => {
      stop()
      setMoving(null)
      if (cur !== start) onLive(from)
    }
    const up = () => {
      stop()
      setMoving(null)
      if (closing && into) {
        const gone = (closing === 'a' ? split.kids[i] : split.kids[i + 1]) as Zone
        const taker = into
        onLive(from)
        onEdit((t) => mergeZone(t, gone.id, taker.id).tree, `Merged ${gone.name ?? 'the zone'} into ${taker.name ?? 'the zone beside it'}; what it kept came along.`)
        return
      }
      if (minimizing && cur !== start) {
        const next = settle(back(from, cur))
        onLive(from)
        onEdit(() => next, `Minimized ${minimizing} to the rail. Its ⤢, or the boundary beside it, opens it.`)
        return
      }
      if (off.length) {
        if (cur === sized) return
        const next = settle(back(from, cur))
        onLive(from)
        onEdit(() => next, unfitWords(off))
        return
      }
      if (cur !== start) onLive(back(from, cur), { from })
    }
    window.addEventListener('pointermove', mv)
    window.addEventListener('pointerup', up)
    window.addEventListener('pointercancel', cancel)
    endDrag.current = cancel
  }

  /* -- the boundary beside a docked rail -------------------------------------- */
  /* Make zone `id` `px` across from the zones beside it in its row, in the
     tree as kept (`widenZone`), as one step with Undo. */
  const widenTo = (z: Zone, px: number): boolean => {
    if (stacked) return false
    const next = widenZone(tree, z.id, px, kept, wrap)
    if (!next) return false
    if (next !== tree) onEdit(() => next, `Widened ${z.name ?? 'the zone'} to ${px} px.`)
    return true
  }
  const railName = (d: Dock) => zones(d.split).find((z) => z.id === d.id)?.name ?? 'the zone'
  const openRail = (d: Dock, key: string) => {
    const z = zones(d.split).find((x) => x.id === d.id)
    if (!z || !dock || widenTo(z, dock.below)) return
    setSaid({ key, a: 0, b: 0, text: NO_ROOM })
  }
  /* Dragged out from the rail, it stays the rail -- and the tree as it was
     -- until it is as wide as it reads; from there it is that wide, the
     zone beside it giving the room, as any boundary. Pressed without
     moving, it opens. Never dragged closed: it is already as small as it is
     drawn. */
  const startRail = (e: React.PointerEvent, d: Dock, key: string, held = false) => {
    if (e.button !== 0 || !dock) return
    if (!held && armTouchDrag(e, e.currentTarget as HTMLElement, () => startRail(e, d, key, true))) return
    e.preventDefault()
    endDrag.current?.()
    const ri = d.split.kids.findIndex((k) => k.type === 'zone' && k.id === d.id)
    const i = d.at === 'start' ? ri : ri - 1
    const sign = d.at === 'start' ? 1 : -1
    const p0 = e.clientX
    const from = tree
    let cur = tree
    let curSplit = d.split
    let moved = false
    const name = railName(d)
    const mv = (ev: PointerEvent) => {
      if (ev.pointerType !== 'mouse') ev.preventDefault()
      const dx = ev.clientX - p0
      if (Math.abs(dx) > 3) moved = true
      const want = d.w + sign * dx
      if (want < dock.below) {
        if (cur !== from) { cur = from; curSplit = d.split; onLive(from) }
        setMoving({ split: curSplit, i, a: 0, b: 0, closing: null, into: null, blocked: null, key, text: `${name} is minimized: drag it out to ${dock.below} px to open it` })
        return
      }
      const live = place(cur, { x: 0, y: 0, w: size.w, h: size.h }, undefined, folded, wrap, undefined, natural)
      const { along } = bounds(curSplit, i, live, wrap)
      const total = (curSplit.sizes[i] + curSplit.sizes[i + 1]) * along
      const res = resize(cur, curSplit, i, d.at === 'start' ? want : total - want, live, wrap)
      cur = res.tree
      curSplit = res.split
      onLive(cur)
      const a = res.split.sizes[i] * along
      setMoving({ split: curSplit, i, a, b: total - a, closing: null, into: null, blocked: null, key })
    }
    const stop = () => {
      window.removeEventListener('pointermove', mv)
      window.removeEventListener('pointerup', up)
      window.removeEventListener('pointercancel', cancel)
      endDrag.current = null
    }
    const cancel = () => {
      stop()
      setMoving(null)
      if (cur !== from) onLive(from)
    }
    const up = () => {
      stop()
      setMoving(null)
      if (!moved) { if (cur !== from) onLive(from); openRail(d, key); return }
      if (cur !== from) onLive(cur, { from })
    }
    window.addEventListener('pointermove', mv)
    window.addEventListener('pointerup', up)
    window.addEventListener('pointercancel', cancel)
    endDrag.current = cancel
  }
  /* From the keyboard: Enter, Space, End, or the arrow away from the edge
     opens it; the arrow towards the edge says it is minimized. */
  const railKey = (e: React.KeyboardEvent, d: Dock, key: string) => {
    if (!dock) return
    const out = d.at === 'start' ? 'ArrowRight' : 'ArrowLeft'
    const into = d.at === 'start' ? 'ArrowLeft' : 'ArrowRight'
    if ([out, 'Enter', ' ', 'End'].includes(e.key)) { e.preventDefault(); openRail(d, key) }
    else if ([into, 'Home'].includes(e.key)) { e.preventDefault(); setSaid({ key, a: 0, b: 0, text: `${railName(d)} is minimized: Enter opens it` }) }
  }
  /* The keyboard moves a divider too: 16 px a press, 64 with Shift; Home and
     End go to either side's minimum. */
  const keyMove = (e: React.KeyboardEvent, split: Split, i: number, key: string) => {
    const row = split.dir === 'row'
    const step = e.shiftKey ? 64 : 16
    const r = rects.get(split.kids[i])
    if (!r) return
    const { lo, hi, along } = bounds(split, i, rects, wrap)
    const now = row ? r.w : r.h
    const d: Record<string, number> = row ? { ArrowLeft: now - step, ArrowRight: now + step } : { ArrowUp: now - step, ArrowDown: now + step }
    const to = e.key in d ? d[e.key] : e.key === 'Home' ? lo : e.key === 'End' ? hi : null
    if (to === null) return
    e.preventDefault()
    /* A fitted zone beside it: sized by hand from where it is drawn, and no
       longer fitted (one step). */
    const off = fittedAt(split, [i, i + 1])
    if (off.length) {
      const dr = asDrawn(drawn, split, rects)
      paused.current = new Set(off.map((z) => z.id))
      const live = place(dr.tree, { x: 0, y: 0, w: size.w, h: size.h }, undefined, folded, wrap, fixed, natural)
      const res = resize(dr.tree, dr.split, i, to, live, wrap)
      paused.current = new Set()
      const next = setFit(back(tree, res.tree), off.map((z) => z.id), false)
      onEdit(() => next, unfitWords(off))
      const lr = live.get(dr.split)
      const sum = lr ? (row ? lr.w : lr.h) - GUTTER * (split.kids.length - 1) : along
      const a = res.split.sizes[i] * sum
      setSaid({ key, a, b: (res.split.sizes[i] + res.split.sizes[i + 1]) * sum - a })
      return
    }
    const res = resize(drawn, split, i, to, rects, wrap)
    if (res.tree !== drawn) { const next = back(tree, res.tree); onEdit(() => next) }
    const total = (split.sizes[i] + split.sizes[i + 1]) * along
    const a = Math.max(lo, Math.min(hi, to))
    setSaid({ key, a, b: total - a })
  }

  const dividers: ReactNode[] = []
  if (!stacked) {
    const walk = (n: Node) => {
      if (n.type === 'zone') return
      const r = rects.get(n)
      if (!r) return
      /* A row wrapped onto more lines has no one boundary between its zones. */
      const lines = wrapped(n, rects)
      n.kids.forEach((k, i) => {
        walk(k)
        if (i === n.kids.length - 1 || lines) return
        const a = rects.get(k)
        if (!a) return
        const row = n.dir === 'row'
        /* Folded to its caption, a zone has no height to give or take. */
        if (!row && (foldedHeight(k, folded, r.w) !== null || foldedHeight(n.kids[i + 1], folded, r.w) !== null)) return
        const key = `${zones(k)[0]?.id}|${zones(n.kids[i + 1])[0]?.id}`
        const style: React.CSSProperties = row
          ? { left: a.x + a.w, top: r.y, width: GUTTER, height: r.h }
          : { left: r.x, top: a.y + a.h, width: r.w, height: GUTTER }
        const m = moving?.key === key ? moving : null
        const s = m ?? (said?.key === key ? said : null)
        const nameA = nameOf(k), nameB = nameOf(n.kids[i + 1])
        const ar = rects.get(k)!
        /* Beside a rail: its boundary opens it. A rail drawn away from its
           place in the row has none -- its own ⤢ and pencil open it. */
        const rail = ds.find((d) => [k, n.kids[i + 1]].some((x) => x.type === 'zone' && x.id === d.id))
        if (rail?.moved) return
        if (rail) {
          const name = railName(rail)
          dividers.push(
            <div key={key} className={'wt-div v wt-div-rail ' + rail.at + (m ? ' drag' : '')} style={style}
              role="separator" tabIndex={0} aria-orientation="vertical" aria-valuenow={Math.round(rail.w)} aria-valuetext={`${name} minimized`}
              aria-label={`Between ${nameA} and ${nameB}: ${name} is minimized. Enter, or drag it out, opens it`}
              title={`Click or drag out to open ${name} (Enter)`} data-between={`${nameA}|${nameB}`}
              onPointerDown={(e) => startRail(e, rail, key)} onKeyDown={(e) => railKey(e, rail, key)}>
              <i />
              {s && (
                <span className="wt-readout" role="status">
                  {s.text ?? (m ? `${nameA} ${Math.round(s.a)} px · ${nameB} ${Math.round(s.b)} px wide` : `${name} is minimized: Enter opens it`)}
                </span>
              )}
            </div>,
          )
          return
        }
        dividers.push(
          <div key={key} className={'wt-div ' + (row ? 'v' : 'h') + (m ? ' drag' : '') + (m?.closing ? ' closing' : '')} style={style}
            role="separator" tabIndex={0} aria-orientation={row ? 'vertical' : 'horizontal'}
            aria-valuenow={Math.round(row ? ar.w : ar.h)} aria-valuemin={Math.round(row ? MIN_W : MIN_H)}
            aria-label={`Between ${nameA} and ${nameB}: drag, or arrow keys, to resize; drag past the end to merge`}
            title="Drag to resize · arrow keys · double-click to even out · drag past the end to merge"
            data-between={`${nameA}|${nameB}`}
            onPointerDown={(e) => startDrag(e, n, i, key)}
            onKeyDown={(e) => keyMove(e, n, i, key)}
            onDoubleClick={() => {
              /* evened, its fitted zones take their share again */
              const off = fittedAt(n, n.kids.map((_, j) => j))
              const unfit = (t: Node) => (off.length ? setFit(t, off.map((z) => z.id), false) : t)
              onEdit((t) => unfit(ds.length ? back(t, even(drawn, n)) : even(t, findSplit(t, n) ?? n)), 'Evened out the zones.' + (off.length ? ' ' + unfitWords(off) : ''))
            }}>
            <i />
            {s && (
              <span className="wt-readout" role="status">
                {s.text ? s.text : m?.closing && m.into
                  ? `Let go to merge ${m.closing === 'a' ? nameA : nameB} into ${m.into.name ?? 'the zone beside it'}`
                  : m?.blocked
                    ? `${m.blocked} are split: merge them one at a time`
                    : `${nameA} ${Math.round(s.a)} px · ${nameB} ${Math.round(s.b)} px${row ? ' wide' : ' tall'}`}
              </span>
            )}
          </div>,
        )
      })
    }
    walk(drawn)
    /* A drag that has made its zone the rail drawn away from its place has
       no boundary left to speak from: the rail's own edge says it. */
    const d = moving?.text ? ds.find((x) => x.moved) : undefined
    const rr = d && all.find((z) => z.id === d.id)
    const r = rr && rects.get(rr)
    if (moving?.text && d && r && !dividers.some((x) => (x as { key?: string })?.key === moving.key))
      dividers.push(
        <div key="rail-said" className={'wt-div v wt-div-rail drag said ' + d.at} aria-hidden="true"
          style={{ left: d.at === 'start' ? r.x + r.w : r.x - GUTTER, top: r.y, width: GUTTER, height: r.h }}>
          <span className="wt-readout" role="status">{moving.text}</span>
        </div>,
      )
  }

  const closingId = moving?.closing ? zones(moving.closing === 'a' ? moving.split.kids[moving.i] : moving.split.kids[moving.i + 1])[0]?.id : null
  return (
    <div className={'wt' + (stacked ? ' stacked' : '') + (moving ? ' resizing' : '')} ref={box} aria-label={label} data-page-tree={page}>
      {all.map((z) => {
        const r = rects.get(z)
        if (!r) return null
        /* What can be done to a zone is read from the tree as kept: a rail
           is split, merged or widened as the zone it is. */
        const k = kept.get(z) ?? r
        const keep = keepWide?.(z) ?? 0
        const isDocked = ds.some((d) => d.id === z.id)
        const ctl: ZoneCtl = {
          id: z.id,
          stacked,
          across: stacked || k.w >= size.w - 1,
          canSplitRow: !stacked && canSplit(k, 'row', keep),
          canSplitCol: !stacked && canSplit(k, 'col'),
          whyNoSplitRow: whyNoSplit(k, 'row', stacked, keep),
          whyNoSplitCol: whyNoSplit(k, 'col', stacked),
          canMerge: canMerge(tree, z.id),
          canClose: all.length > 1 || canCloseLast,
          split: (dir) => onEdit((t) => splitZone(t, z.id, dir, made?.(t), false, dir === 'row' ? keepShare(k.w, keep) : 0.5).tree,
            `Split ${z.name ?? 'the zone'} ${dir === 'row' ? 'side by side' : 'top and bottom'}.`),
          merge: () => onEdit((t) => mergeZone(t, z.id).tree, `Merged ${z.name ?? 'the zone'} into the zone beside it; what it kept came along.`),
          close: () => onEdit((t) => closeZone(t, z.id), `Closed ${z.name ?? 'the zone'}. What it showed is still in its post.`),
          closing: closingId === z.id,
          widen: (px) => widenTo(z, px),
          docked: isDocked,
          ...(page === 'this-post' ? {
            focus: () => { workspace.edit((a) => makePrimary(a, z.id), `${z.name ?? 'The section'} is primary.`); pulseArrived(z.id) },
            float: () => workspace.edit((a) => floatOut(a, z.id, { x: r.x + 20, y: r.y + 20, w: Math.max(260, r.w * .8), h: Math.max(180, r.h * .8) }), `${z.name ?? 'The section'} floats; the sections beside it took its room. “Dock back” returns it.`),
            drag: (e: React.PointerEvent<HTMLElement>) => beginDrag({ type: 'section', id: z.id }, e, e.currentTarget.closest('.wt-cell') as HTMLElement, z.name ?? 'Section'),
          } : {}),
          fit: !!z.fit,
          toggleFit: () => onEdit((t) => setFit(t, [z.id], !z.fit), z.fit
            ? `${z.name ?? 'The zone'} takes its share again.`
            : `${z.name ?? 'The zone'} fits its content${tree.type === 'zone' ? ' (it is the only section, so it fills)' : ''}; the sections beside it take the rest.`),
        }
        return (
          <div key={z.id} ref={(el) => { if (el) cellEls.current.set(z.id, el); else cellEls.current.delete(z.id) }} className={'wt-cell' + (ctl.closing ? ' closing' : '') + (isDocked ? ' docked' : '') + (page === 'this-post' && primaryOf(workspace.arr) === z.id ? ' primary' : '')} data-zone-id={z.id}
            {...(isDocked ? { 'data-kept-w': Math.round(k.w), 'data-kept-h': Math.round(k.h) } : {})}
            style={stacked ? { height: r.h } : { left: r.x, top: r.y, width: r.w, height: r.h }}>
            {renderZone(z, r, ctl)}
          </div>
        )
      })}
      {dividers}
    </div>
  )
}

function findSplit(n: Node, like: Split): Split | null {
  if (n.type === 'zone') return null
  if (n.dir === like.dir && n.kids.length === like.kids.length && n.kids.every((k, i) => sameShape(k, like.kids[i]))) return n
  for (const k of n.kids) {
    const f = findSplit(k, like)
    if (f) return f
  }
  return null
}
const sameShape = (a: Node, b: Node): boolean =>
  a.type === 'zone' ? b.type === 'zone' && a.id === b.id : b.type === 'split' && a.kids.length === b.kids.length && a.kids.every((k, i) => sameShape(k, b.kids[i]))

/* -- fit to content: reading a cell ------------------------------------------- */

/** What a fitted zone measured, and how big its cell was when it did. */
interface Measured { w?: number; h?: number; atW?: number; atH?: number }

/** The tallest a fitted zone is drawn while the zones are stacked. */
const STACKED_FIT_MAX = 600

const cellOf = (root: HTMLElement, id: string) => root.querySelector<HTMLElement>(`:scope > .wt-cell[data-zone-id="${CSS.escape(id)}"]`)

/** A zone's content, inside its cell: the element that scrolls what it
 *  shows (Zones.tsx `.wk-zbody`; `.zb-in` or `[data-fit-body]` where a zone
 *  marks its own). */
const bodyOf = (cell: HTMLElement | null) => cell?.querySelector<HTMLElement>('[data-fit-body], .zb-in, .wk-zbody') ?? null

/** What a zone drawn in `cell` needs along `axis`: its caption and whatever
 *  else is around its content, and the content itself -- height: down to its
 *  last child's bottom, wherever the body is scrolled; width: the body at
 *  its max-content width (the prototype's `natural`). Null when it has no
 *  body to read. */
export function naturalOf(cell: HTMLElement, axis: 'w' | 'h'): number | null {
  const zone = cell.firstElementChild as HTMLElement | null
  const body = bodyOf(cell)
  if (!zone || !body) return null
  if (axis === 'w') {
    const was = body.style.width
    body.style.width = 'max-content'
    const w = body.offsetWidth
    body.style.width = was
    return zone.offsetWidth - body.offsetWidth + w
  }
  const cs = getComputedStyle(body)
  const top = body.getBoundingClientRect().top
  let end = top + body.clientTop + parseFloat(cs.paddingTop || '0')
  for (const k of Array.from(body.children)) {
    const kr = k.getBoundingClientRect()
    if (!kr.width && !kr.height) continue
    end = Math.max(end, kr.bottom + (parseFloat(getComputedStyle(k).marginBottom || '0') || 0))
  }
  const content = end - top + body.scrollTop + parseFloat(cs.paddingBottom || '0') + parseFloat(cs.borderBottomWidth || '0')
  return Math.ceil(zone.offsetHeight - body.offsetHeight + content)
}

/* The zone's own tools, quiet until the zone is hovered or focused: split
   side by side, split top and bottom, merge, close (#188: the existing split
   icons; #187 #7: compact controls for routine manipulation). On a zone
   minimized to the rail (`rail`) only close: a rail is not split, and merged
   it would only go as closed does, into a zone it is drawn away from. */
const ICON = {
  splitV: <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.4"><rect x="1.5" y="2" width="11" height="10" rx="1.5" /><path d="M7 2v10" /></svg>,
  splitH: <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.4"><rect x="1.5" y="2" width="11" height="10" rx="1.5" /><path d="M1.5 7h11" /></svg>,
  merge: <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round"><rect x="1.5" y="2" width="11" height="10" rx="1.5" /><path d="M5 7h4M7.5 5.5 9 7 7.5 8.5" /></svg>,
  close: <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round"><path d="M4 4l6 6M10 4l-6 6" /></svg>,
}

/* Fit to content (the prototype's ⇕, DESIGN.md 4): pressed, the zone is
   sized to what it holds along its split and the zones beside it take the
   rest; pressed again, it takes its share. */
const FIT_ICON = <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round"><path d="M2 1.5h10M2 12.5h10M7 3.5v7M5 5.5l2-2 2 2M5 8.5l2 2 2-2" /></svg>

export function FitTool({ ctl }: { ctl: ZoneCtl }) {
  return (
    <button data-act="fit" className={ctl.fit ? 'on' : undefined} aria-pressed={ctl.fit} aria-label="Fit to content"
      title={ctl.fit ? 'Fitted to its content: press to take its share again' : 'Fit to content: size it to what it holds'}
      onClick={ctl.toggleFit}>{FIT_ICON}</button>
  )
}

export function ZoneTools({ ctl, name, rail = false, compact = false, search }: {
  ctl: ZoneCtl
  name: string
  rail?: boolean
  compact?: boolean
  search?: ReactNode
}) {
  if (rail)
    return (
      <span className="wt-tools" role="toolbar" aria-label={`${name} zone`}>
        <button data-act="close-zone" disabled={!ctl.canClose} aria-label="Close this zone"
          title={ctl.canClose ? 'Close this zone (Undo brings it back)' : 'A page keeps one zone'} onClick={ctl.close}>{ICON.close}</button>
      </span>
    )
  return (
    <span className={'wt-tools' + (compact ? ' compact' : '')} role="toolbar" aria-label={`${name} zone`}>
      {ctl.drag && <button className="wt-grip" data-act="drag-zone" aria-label={`Move ${name}`} title="Drag to move, dock or float" onPointerDown={ctl.drag}>⠿</button>}
      {ctl.focus && <span className="wt-focus-tools">
        <button data-act="focus" aria-label="Make primary" title="Make primary" onClick={ctl.focus}>◎</button>
      </span>}
      {search}
      {!compact && (
        <>
          <FitTool ctl={ctl} />
          {ctl.float && <span className="wt-focus-tools">
            <button data-act="float" aria-label="Float this section" title="Float this section" onClick={ctl.float}>⇱</button>
          </span>}
          <button data-act="split-row" disabled={!ctl.canSplitRow} aria-label="Split side by side"
            title={ctl.canSplitRow ? 'Split side by side' : `Can't split side by side. ${ctl.whyNoSplitRow ?? ''}`} onClick={() => ctl.split('row')}>{ICON.splitV}</button>
          <button data-act="split-col" disabled={!ctl.canSplitCol} aria-label="Split top and bottom"
            title={ctl.canSplitCol ? 'Split top and bottom' : `Can't split top and bottom. ${ctl.whyNoSplitCol ?? ''}`} onClick={() => ctl.split('col')}>{ICON.splitH}</button>
          <button data-act="merge" disabled={!ctl.canMerge} aria-label="Merge with the zone beside it"
            title={ctl.canMerge ? 'Merge into the zone beside it (or drag the divider closed)' : 'Nothing beside it to merge into'} onClick={ctl.merge}>{ICON.merge}</button>
          <button data-act="close-zone" disabled={!ctl.canClose} aria-label="Close this zone"
            title={ctl.canClose ? 'Close this zone (Undo brings it back)' : 'A page keeps one zone'} onClick={ctl.close}>{ICON.close}</button>
        </>
      )}
    </span>
  )
}
