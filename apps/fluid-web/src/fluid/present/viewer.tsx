/* THE MEDIA VIEWER, SCOPED TO ITS POST (#181 decision 4, #188 table: "full-
 * screen over all media" becomes "scoped to the post it opened from"; #184:
 * every detail opens out of its anchor and returns into it).
 *
 * It grows out of the plate or card it was opened from over the workspace,
 * and shrinks back into it; the anchor then flashes once and nothing else
 * has moved. It steps through that post's pictures, films and sound only
 * ("3 of 7"), never the conversation's. Full screen fills the screen (the
 * browser's own full screen where it allows it), zoom is − / Fit / 1:1 / +,
 * Ctrl+wheel and a double click, and a zoomed picture is dragged to pan.
 *
 * Esc leaves full screen first, then returns. Moving to another post closes
 * it, as every temporary detail closes (#184 choice 2). */

import { useCallback, useEffect, useLayoutEffect, useRef, useState, useSyncExternalStore } from 'react'
import { store, type PostObjectEntry } from '../store'
import { titleOf, useNav, useObject, usePost, usePostObjects } from '../workspace/hooks'
import { flash } from '../workspace/motion'
import { isPicture, isViewable } from './size'

/* -- what is open: one viewer, opened from one anchor ----------------------- */

interface Open { address: string; from: HTMLElement | null; key: number }
let open: Open | null = null
let seq = 0
const heard = new Set<() => void>()
const tell = () => heard.forEach((fn) => fn())
const useOpenViewer = () => useSyncExternalStore((fn) => { heard.add(fn); return () => { heard.delete(fn) } }, () => open)

/** Open the post-scoped viewer on this object, growing out of `from`. */
export function openMedia(address: string, from: HTMLElement | null) {
  open = { address, from, key: ++seq }
  tell()
}
export const mediaOpen = () => !!open
export const useMediaOpen = () => !!useOpenViewer()
function shut() { open = null; tell() }
/* The top bar's ← Back returns the viewer into its anchor first (#184: Esc,
   the detail's ‹ and ← Back all do the same thing). */
const closers = new Set<() => void>()
export function closeMedia(): boolean {
  if (!open) return false
  closers.forEach((fn) => fn())
  return true
}

/** The ‹ label names where it goes back to (#184): the zone it came from. */
function backTo(from: HTMLElement | null): string | null {
  const zone = from?.closest('[data-zone]')?.getAttribute('data-zone')
  if (zone === 'following') return 'This post'
  if (zone === 'kept') return 'Kept'
  if (zone === 'page') return from?.closest('[data-page]') ? 'the page' : null
  return null
}

const urlOf = (o: PostObjectEntry) => o.artifact?.url ?? (o.ref ? `/api/artifacts/${o.ref}` : null)
const reduced = () => typeof matchMedia !== 'undefined' && matchMedia('(prefers-reduced-motion: reduce)').matches

/** Where the viewer sits when it is not full screen: over the workspace, as
 *  an object's detail does (the conversation stays in view). */
function homeRect(): DOMRect {
  const ws = document.querySelector('.wk') as HTMLElement | null
  const r = ws?.getBoundingClientRect()
  if (r && r.width >= 520 && r.height > 240) return r
  /* A workspace too narrow to look at a picture in: the window below the bar. */
  const bar = document.querySelector('.fx-bar')?.getBoundingClientRect().bottom ?? 48
  return new DOMRect(8, bar + 8, innerWidth - 16, innerHeight - bar - 16)
}

/** The post's viewable objects, in its order: what the viewer steps through. */
function useScope(o: PostObjectEntry | null): string[] {
  const post = o?.post ?? ''
  const listing = usePostObjects(post)
  useEffect(() => { if (post && !store.postObjects.has(post)) void store.loadObjects(post).catch(() => {}) }, [post])
  const [, bump] = useState(0)
  /* each listed object, as the store resolves it */
  useEffect(() => {
    if (!listing) return
    const offs = listing.addresses.map((a) => store.subscribe('obj:' + a, () => bump((n) => n + 1)))
    return () => offs.forEach((off) => off())
  }, [listing])
  if (!listing) return []
  return listing.addresses.filter((a) => {
    const st = store.objects.get(a)
    return st && 'object' in st && st.object.parent === null && isViewable(st.object)
  })
}

export function MediaViewerHost() {
  const want = useOpenViewer()
  /* Moving to another post, or another conversation, closes it. */
  const n = useNav()
  const at = useRef({ reading: n.reading, conversation: n.conversation })
  useEffect(() => {
    const was = at.current
    at.current = { reading: n.reading, conversation: n.conversation }
    if (open && (was.reading !== n.reading || was.conversation !== n.conversation)) shut()
  }, [n.reading, n.conversation])
  if (!want) return null
  return <Viewer key={want.key} first={want} />
}

type Zoom = 'fit' | number

function Viewer({ first }: { first: Open }) {
  const [address, setAddress] = useState(first.address)
  const st = useObject(address)
  useEffect(() => { if (!st) void store.loadObject(address).catch(() => {}) }, [st, address])
  const o = st && 'object' in st ? st.object : null
  const firstObj = useObject(first.address)
  const scopeOf = firstObj && 'object' in firstObj ? firstObj.object : o
  const scope = useScope(scopeOf)
  const post = usePost(scopeOf?.post ?? '')
  const i = scope.indexOf(address)
  const [full, setFull] = useState(false)
  const [zoom, setZoom] = useState<Zoom>('fit')
  const [leaving, setLeaving] = useState(false)
  const box = useRef<HTMLDivElement | null>(null)
  const stage = useRef<HTMLDivElement | null>(null)

  const step = useCallback((d: number) => {
    if (scope.length < 2) return
    const j = i < 0 ? 0 : (i + d + scope.length) % scope.length
    setAddress(scope[j])
    setZoom('fit')
  }, [scope, i])

  /* -- growing out of the anchor, and shrinking back into it ------------- */
  const place = useCallback((r: DOMRect) => {
    const el = box.current
    if (!el) return
    Object.assign(el.style, { left: r.left + 'px', top: r.top + 'px', width: r.width + 'px', height: r.height + 'px' })
  }, [])
  const anchorRect = () => (first.from && first.from.isConnected ? first.from.getBoundingClientRect() : null)
  const fromTo = (a: DOMRect, r: DOMRect) =>
    `translate(${a.left - r.left}px,${a.top - r.top}px) scale(${Math.max(0.02, a.width / r.width)},${Math.max(0.02, a.height / r.height)})`

  useLayoutEffect(() => {
    const el = box.current
    if (!el) return
    const r = homeRect()
    place(r)
    const a = anchorRect()
    el.style.transition = 'none'
    if (a && !reduced()) {
      el.style.transform = fromTo(a, r)
      el.style.opacity = '.5'
      void el.offsetWidth
    }
    el.style.transition = 'transform var(--wk-t, .34s) var(--wk-ease, ease), opacity .2s'
    el.style.transform = 'none'
    el.style.opacity = '1'
    el.focus()
    first.from?.classList.add('wk-anchor')
    const was = first.from
    return () => was?.classList.remove('wk-anchor')
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  /* The workspace moves under it (the conversation's width, the window):
     placed again from where it is now, unless full screen. */
  useEffect(() => {
    if (full) return
    const again = () => { if (!leaving) place(homeRect()) }
    const ws = document.querySelector('.wk')
    const ro = new ResizeObserver(again)
    if (ws) ro.observe(ws)
    window.addEventListener('resize', again)
    return () => { ro.disconnect(); window.removeEventListener('resize', again) }
  }, [full, leaving, place])

  const leaveFull = useCallback(() => {
    if (document.fullscreenElement) void document.exitFullscreen().catch(() => {})
    setFull(false)
  }, [])
  const goFull = useCallback(() => {
    setFull(true)
    const el = box.current
    if (el?.requestFullscreen) void el.requestFullscreen().catch(() => { /* the in-page full screen stands */ })
  }, [])
  /* The browser's own Esc leaves its full screen: the viewer follows. */
  useEffect(() => {
    const sync = () => { if (!document.fullscreenElement) setFull(false) }
    document.addEventListener('fullscreenchange', sync)
    return () => document.removeEventListener('fullscreenchange', sync)
  }, [])
  useLayoutEffect(() => {
    const el = box.current
    if (!el) return
    if (full) Object.assign(el.style, { left: '0px', top: '0px', width: innerWidth + 'px', height: innerHeight + 'px' })
    else if (!leaving) place(homeRect())
  }, [full, leaving, place])

  const close = useCallback(() => {
    if (leaving) return
    if (document.fullscreenElement) void document.exitFullscreen().catch(() => {})
    setLeaving(true)
    setFull(false)
    const el = box.current
    const a = anchorRect()
    if (el && a && !reduced()) {
      const r = homeRect()
      place(r)
      el.style.transform = fromTo(a, r)
      el.style.opacity = '0'
    } else if (el) el.style.opacity = '0'
    const from = first.from
    window.setTimeout(() => {
      shut()
      from?.classList.remove('wk-anchor')
      if (from?.isConnected) { flash(from); from.focus?.({ preventScroll: true }) }
    }, reduced() ? 0 : 340)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [leaving, place])

  useEffect(() => { closers.add(close); return () => { closers.delete(close) } }, [close])

  /* -- keys: captured, so Esc here never also closes something under it --- */
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement | null
      if (t && t !== box.current && !box.current?.contains(t) && t.matches?.('input, textarea, select, [contenteditable]')) return
      let used = true
      if (e.key === 'Escape') { if (full) leaveFull(); else close() }
      else if (e.key === 'ArrowRight') step(1)
      else if (e.key === 'ArrowLeft') step(-1)
      else if (e.key === '+' || e.key === '=') setZoom((z) => Math.min(8, (z === 'fit' ? fitScale() : z) * 1.25))
      else if (e.key === '-') setZoom((z) => Math.max(0.1, (z === 'fit' ? fitScale() : z) / 1.25))
      else if (e.key === '0') setZoom('fit')
      else if (e.key === 'f' && !e.ctrlKey && !e.metaKey) { if (full) leaveFull(); else goFull() }
      else used = false
      if (used) { e.preventDefault(); e.stopPropagation() }
    }
    window.addEventListener('keydown', onKey, true)
    return () => window.removeEventListener('keydown', onKey, true)
  })

  /* -- zoom and pan ------------------------------------------------------- */
  const img = useRef<HTMLImageElement | null>(null)
  const fitScale = () => {
    const im = img.current, s = stage.current
    if (!im || !s || !im.naturalWidth) return 1
    return Math.min(1, s.clientWidth / im.naturalWidth, s.clientHeight / im.naturalHeight)
  }
  const drag = useRef<{ x: number; y: number; l: number; t: number } | null>(null)
  const picture = o && isPicture(o)
  const url = o ? urlOf(o) : null
  const zoomed = zoom !== 'fit'
  const pct = zoom === 'fit' ? null : Math.round(zoom * 100)

  return (
    <div ref={box} className={'pz-viewer' + (full ? ' full' : '')} role="dialog" aria-modal="true" tabIndex={-1}
      aria-label={`${o ? titleOf(o) : 'media'}${scope.length ? `, ${Math.max(1, i + 1)} of ${scope.length}` : ''}`}>
      <div className="pz-vhead">
        <button className="pz-vret" data-act="return" onClick={close} title="Back to where it was opened (Esc)">
          {'‹'} {backTo(first.from) ?? (post?.number != null ? `#${post.number}` : 'Back')}
        </button>
        <h3 title={o ? titleOf(o) : undefined}>{o ? titleOf(o) : st && 'unresolved' in st ? 'Not found' : '…'}</h3>
        {scope.length > 0 && <span className="pz-vcount" aria-live="polite">{Math.max(1, i + 1)} of {scope.length} in #{post?.number ?? '?'}{post?.author_name ? ` · @${post.author_name.replace(/^@/, '')}` : ''}</span>}
        <span className="pz-vgrow" />
        {picture && (
          <span className="pz-vzoom" role="group" aria-label="zoom">
            <button title="Zoom out (−)" aria-label="Zoom out" onClick={() => setZoom((z) => Math.max(0.1, (z === 'fit' ? fitScale() : z) / 1.25))}>−</button>
            <button className={zoom === 'fit' ? 'on' : ''} title="Fit (0)" aria-pressed={zoom === 'fit'} onClick={() => setZoom('fit')}>Fit</button>
            <button className={zoom === 1 ? 'on' : ''} title="Actual size" aria-pressed={zoom === 1} onClick={() => setZoom(1)}>{pct != null && zoom !== 1 ? `${pct}%` : '1:1'}</button>
            <button title="Zoom in (+)" aria-label="Zoom in" onClick={() => setZoom((z) => Math.min(8, (z === 'fit' ? fitScale() : z) * 1.25))}>+</button>
          </span>
        )}
        <button className="pz-vbtn" data-act="full" aria-pressed={full} title={full ? 'Leave full screen (Esc)' : 'Full screen (F)'} onClick={full ? leaveFull : goFull}>
          {full ? 'Exit full screen' : 'Full screen'}
        </button>
        {url && <a className="pz-vbtn" href={url} target="_blank" rel="noreferrer" title="The original, in a new tab">Original ↗</a>}
        <button className="pz-vbtn pz-vx" data-act="close" aria-label="Close" title="Close (Esc)" onClick={close}>{'✕'}</button>
      </div>
      <div ref={stage} className={'pz-vstage' + (zoomed ? ' zoomed' : '')}
        onWheel={(e) => {
          if (!picture || !(e.ctrlKey || e.metaKey)) return
          e.preventDefault()
          setZoom((z) => Math.min(8, Math.max(0.1, (z === 'fit' ? fitScale() : z) * (e.deltaY < 0 ? 1.15 : 1 / 1.15))))
        }}
        onPointerDown={(e) => {
          if (!zoomed || !stage.current) return
          drag.current = { x: e.clientX, y: e.clientY, l: stage.current.scrollLeft, t: stage.current.scrollTop }
          stage.current.setPointerCapture(e.pointerId)
        }}
        onPointerMove={(e) => {
          const d = drag.current, s = stage.current
          if (!d || !s) return
          s.scrollLeft = d.l - (e.clientX - d.x)
          s.scrollTop = d.t - (e.clientY - d.y)
        }}
        onPointerUp={() => { drag.current = null }}>
        {o && url && picture ? (
          <img ref={img} src={url} alt={o.title ?? ''} draggable={false}
            onDoubleClick={() => setZoom((z) => (z === 'fit' ? 2 : 'fit'))}
            style={zoom === 'fit' ? undefined : { width: (img.current?.naturalWidth ?? 0) * zoom || undefined, maxWidth: 'none', maxHeight: 'none' }} />
        ) : o && url && (o.media_type ?? '').startsWith('video/') ? (
          <video src={url} controls />
        ) : o && url && (o.media_type ?? '').startsWith('audio/') ? (
          <audio src={url} controls />
        ) : st && 'unresolved' in st ? <p className="wk-quietline">This no longer resolves: {st.unresolved}.</p> : null}
        {scope.length > 1 && (
          <>
            <button className="pz-vstep prev" aria-label="Previous (←)" title="Previous (←)" onClick={() => step(-1)}>{'‹'}</button>
            <button className="pz-vstep next" aria-label="Next (→)" title="Next (→)" onClick={() => step(1)}>{'›'}</button>
          </>
        )}
      </div>
      {scope.length > 1 && (
        <ul className="pz-vstrip" aria-label={`everything viewable in #${post?.number ?? ''}`}>
          {scope.map((a) => <Thumb key={a} address={a} on={a === address} pick={() => { setAddress(a); setZoom('fit') }} />)}
        </ul>
      )}
    </div>
  )
}

function Thumb({ address, on, pick }: { address: string; on: boolean; pick: () => void }) {
  const st = useObject(address)
  const o = st && 'object' in st ? st.object : null
  const url = o ? urlOf(o) : null
  const ref = useRef<HTMLButtonElement | null>(null)
  useEffect(() => { if (on) ref.current?.scrollIntoView?.({ block: 'nearest', inline: 'nearest' }) }, [on])
  return (
    <li>
      <button ref={ref} className={on ? 'on' : ''} aria-current={on || undefined} aria-label={o ? titleOf(o) : 'item'} onClick={pick}>
        {o && isPicture(o) && url ? <img src={url} alt="" loading="lazy" /> : <span>{o && (o.media_type ?? '').startsWith('audio/') ? '♪' : '▶'}</span>}
      </button>
    </li>
  )
}
