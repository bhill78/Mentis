/* An object's detail (spec 6.4). OVER, the Mixed default: it grows out of
 * its card over the arrangement, which dims, and shrinks back into the card
 * on close. BESIDE: it opens as a column beside This post. Its head names
 * where "<" goes back to, then Keep, Open as page and close.
 *
 * FOCUS (Objects round, B2) is now INSPECTION, the one way any object is
 * enlarged (render/inspect.ts, present/viewer.tsx): a detail's ◱ inspects
 * it, out of the card it grew from, with the same head, close and keys as a
 * picture. It is a moment, not a place: Esc, ‹ or ✕ return into the card
 * it came from, and nothing about the arrangement changes. Over and Beside
 * stay how objects open (Arrange). Its body is the one every detail draws
 * (ObjectBody), so whatever an object can show there -- a player, a
 * document, and later a sandboxed HTML preview (B1, the owner's to decide)
 * -- it shows there. */

import { useEffect, useLayoutEffect, useRef, useState, type RefObject } from 'react'
import * as nav from '../nav'
import type { Detail } from '../nav'
import { store } from '../store'
import ObjectBody from './ObjectBody'
import { From } from './from'
import { askKeep } from './keep'
import { tabTitle, titleOf, useNav, useObject } from './hooks'
import { fly, tabFor } from './motion'
import { opener } from './open'
import { isNarrow } from '../frame/narrow'
import { Glyph, SourceMark } from '../present/marks'
import { inspect } from '../present/viewer'

/* Where the detail's left edge sits in the workspace: a margin of the
   arrangement showing beside it, or -- in the narrow sheet -- none. */
const leftOf = (w: number) => (isNarrow() ? 0 : Math.max(48, w * 0.14))

type ObjectDetail = Extract<Detail, { kind: 'object' }>

/** Keep, from a detail: "here" is the zone of the card it grew from. */
function keepFrom(address: string, button: HTMLElement) {
  const card = opener.el?.isConnected ? opener.el : null
  const zone = (card?.closest('[data-zone-id]') as HTMLElement | null)?.dataset.zoneId
  const page = (card?.closest('[data-page]') as HTMLElement | null)?.dataset.page
  askKeep({ address, zone, page }, button)
}

/** OPEN AS PAGE: the object on a page of its own, its clone flying from
 *  `from` (where it was drawn) to the page's tab. From a detail's head or
 *  the inspector's. */
export function openAsPage(address: string, from?: DOMRect) {
  const st = store.objects.get(address)
  const o = st && 'object' in st ? st.object : null
  const title = o ? titleOf(o) : 'Not found'
  const had = new Set(nav.snapshot().pages.map((p) => p.id))
  const home = o ? store.posts.get(o.post)?.home_name : null
  const here = nav.snapshot().conversation
  nav.openAsPage(address, tabTitle(title, [home, here ? store.conversations.get(here)?.name : null]))
  /* The clone flies from the detail to the tab the frame just drew -- or,
     when the object is already a page, to that page's tab. */
  requestAnimationFrame(() => requestAnimationFrame(() => {
    const added = nav.snapshot().pages.find((p) => !had.has(p.id))
    const tab = added ? tabFor(added.id) : tabFor(nav.snapshot().page)
    if (from && tab) {
      tab.classList.add('wk-born')
      setTimeout(() => tab.classList.remove('wk-born'), 650)
      const ghost = document.createElement('div')
      Object.assign(ghost.style, { position: 'fixed', left: from.left + 'px', top: from.top + 'px', width: from.width + 'px', height: from.height + 'px' })
      document.body.appendChild(ghost)
      fly(ghost, tab)
      ghost.remove()
    }
  }))
}

/** Inspect the object a detail shows: the detail gives way, and the
 *  inspector grows out of the card the detail grew from. */
function inspectFrom(address: string) {
  const card = opener.el?.isConnected ? opener.el : null
  nav.closeDetail()
  inspect(address, card)
}

function Inner({ d }: { d: ObjectDetail }) {
  const st = useObject(d.address)
  const body = useRef<HTMLDivElement | null>(null)
  useEffect(() => { if (!st) void store.loadObject(d.address).catch(() => {}) }, [st, d.address])
  const o = st && 'object' in st ? st.object : null
  const title = o ? titleOf(o) : 'Not found'
  return (
    <>
      <div className="wk-sheet-head">
        <button className="wk-ret" data-act="return" onClick={() => nav.closeDetail()}>{'‹'} This post</button>
        <h3 title={title}>{title}</h3>
        <span className="wk-hbreak" aria-hidden="true" />
        {o && <SourceMark o={o} compact />}
        {o && <From post={o.post} className="wk-dfrom" />}
        <span className="wk-grow" />
        <span className="wk-hctl">
          {o && <button className="wk-ctl" data-act="keep" aria-haspopup="menu" onClick={(e) => keepFrom(d.address, e.currentTarget)}>Keep…</button>}
          {o && (
            <button className="wk-ctl" data-act="focus" title="Focus: on its own, enlarged (Esc returns)" aria-label="Focus on it, enlarged"
              onClick={() => inspectFrom(d.address)}>
              <Glyph name="focus" />
            </button>
          )}
          {o && <button className="wk-ctl" data-act="aspage" onClick={() => openAsPage(d.address, body.current?.getBoundingClientRect())}>Open as page</button>}
          <button className="wk-ctl wk-x" data-act="close" aria-label="Close" onClick={() => nav.closeDetail()}>{'✕'}</button>
        </span>
      </div>
      <div className="wk-sheet-body wk-big wk-fadein turn-body" ref={body}>
        {o ? <ObjectBody o={o} big /> : st && 'unresolved' in st ? <p className="wk-quietline">This object no longer resolves: {st.unresolved}.</p> : null}
      </div>
    </>
  )
}

/** The anchor card to grow from and shrink into: the one it was opened
 *  from while it is still drawn, else the first card of that address. */
function anchorOf(ws: HTMLElement, address: string): HTMLElement | null {
  if (opener.el?.isConnected && ws.contains(opener.el)) return opener.el
  return ws.querySelector<HTMLElement>(`.wk-card[data-address="${CSS.escape(address)}"]`)
}

/** OVER: positioned in the workspace from max(48, 14%) to its right edge,
 *  full height; grows from the card (.34s) and shrinks back into it. */
export function Overlay({ ws, onDim }: { ws: RefObject<HTMLElement | null>; onDim: (on: boolean) => void }) {
  const n = useNav()
  const want = n.detail?.kind === 'object' && n.detail.mode === 'over' ? n.detail : null
  const [shown, setShown] = useState<ObjectDetail | null>(null)
  const el = useRef<HTMLDivElement | null>(null)
  const closing = useRef<number | undefined>(undefined)
  const toward = useRef<string | null>(null)
  const latest = useRef(want)
  latest.current = want
  /* What is wanted changes: close what is shown, then open what is wanted
     (after .26s when one detail replaces another, as the demo sequences). */
  useEffect(() => {
    if (want && shown && want.address === shown.address) { toward.current = null; return }
    if (!want && !shown) return
    if (shown) {
      const key = want?.address ?? ''
      if (toward.current === key) return
      toward.current = key
      const box = el.current, w = ws.current
      if (box && w) {
        const wr = w.getBoundingClientRect()
        const a = anchorOf(w, shown.address)
        if (a) {
          const ar = a.getBoundingClientRect()
          const fl = parseFloat(box.style.left), fw = parseFloat(box.style.width), fh = parseFloat(box.style.height)
          box.style.transform = `translate(${ar.left - wr.left - fl}px,${ar.top - wr.top}px) scale(${ar.width / fw},${ar.height / fh})`
        }
        box.style.opacity = '0'
      }
      onDim(false)
      clearTimeout(closing.current)
      closing.current = window.setTimeout(() => { toward.current = null; setShown(latest.current) }, want ? 260 : 360)
      return
    }
    setShown(want)
  }, [want, shown, ws, onDim])
  useEffect(() => () => clearTimeout(closing.current), [])
  useLayoutEffect(() => {
    const box = el.current, w = ws.current
    if (!shown || !box || !w) return
    const wr = w.getBoundingClientRect()
    const left = leftOf(wr.width)
    const fin = { l: left, t: 0, w: wr.width - left, h: wr.height }
    Object.assign(box.style, { left: fin.l + 'px', top: fin.t + 'px', width: fin.w + 'px', height: fin.h + 'px', transition: 'none' })
    const a = anchorOf(w, shown.address)
    if (a) {
      const ar = a.getBoundingClientRect()
      box.style.transform = `translate(${ar.left - wr.left - fin.l}px,${ar.top - wr.top - fin.t}px) scale(${ar.width / fin.w},${ar.height / fin.h})`
      box.style.opacity = '.6'
      void box.offsetWidth
    }
    box.style.transition = 'transform var(--wk-t) var(--wk-ease), opacity .2s'
    box.style.transform = 'none'
    box.style.opacity = '1'
    onDim(true)
    /* NEVER STALE: the workspace narrows and widens under an open detail --
       a sheet sliding beside the conversation, the conversation's width, the
       window -- and the box is placed again from the workspace as it is now
       (the F6 review saw it float mid-screen at an earlier layout's place). */
    const ro = new ResizeObserver(() => {
      if (toward.current !== null || !el.current || !ws.current) return
      const r = ws.current.getBoundingClientRect()
      const l = leftOf(r.width)
      Object.assign(el.current.style, { left: l + 'px', top: '0px', width: r.width - l + 'px', height: r.height + 'px' })
    })
    ro.observe(w)
    return () => ro.disconnect()
  }, [shown, ws, onDim])
  if (!shown) return null
  return (
    <div ref={el} className="wk-overlay" role="dialog" aria-label="object detail" data-detail={shown.address}>
      <Inner d={shown} key={shown.address} />
    </div>
  )
}

/** BESIDE: a column beside This post, 60% (spec 6.4 A). */
export function DetailColumn() {
  const n = useNav()
  const want = n.detail?.kind === 'object' && n.detail.mode === 'aside' ? n.detail : null
  const [shown, setShown] = useState<ObjectDetail | null>(want)
  useEffect(() => {
    if (want) { setShown(want); return }
    const t = setTimeout(() => setShown(null), 380)
    return () => clearTimeout(t)
  }, [want])
  return (
    <section className={'wk-zone wk-panel wk-dcol' + (want ? ' show' : '')} data-zone="detail" aria-hidden={!want}>
      {shown && <Inner d={shown} key={shown.address} />}
    </section>
  )
}

/** FOCUS (B2), KEPT AS A DOOR: an object detail asked for in the 'focus'
 *  mode (`workspace/open.ts` focusObject, or anything still asking for it)
 *  is inspected instead, as every enlarged object is (present/viewer.tsx).
 *  Mounted by the shell; draws nothing of its own. */
export function FocusView() {
  const n = useNav()
  const want = n.detail?.kind === 'object' && n.detail.mode === 'focus' ? n.detail.address : null
  useEffect(() => { if (want) inspectFrom(want) }, [want])
  return null
}
