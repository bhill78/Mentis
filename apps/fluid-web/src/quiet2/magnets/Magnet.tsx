import { useEffect, useId, useRef, useState, useSyncExternalStore } from 'react'
import type { CSSProperties, PointerEvent as ReactPointerEvent } from 'react'
import type { RouteResult } from '../../fluid/surface/magnet/route'
import type { MagnetResource, MagnetTab } from './contract'
import './magnet.css'

const PUCK = 64
const GAP = 12
export const DRAG_THRESHOLD = 7

/** Puck coordinates belong to this canvas, never to a saved arrangement. */
export function clampPuck(x: number, y: number, width: number, height: number) {
  return { x: Math.max(GAP, Math.min(Number.isFinite(x) ? x : GAP, Math.max(GAP, width - PUCK - GAP))),
    y: Math.max(GAP, Math.min(Number.isFinite(y) ? y : GAP, Math.max(GAP, height - PUCK - GAP))) }
}

/** Keep the card joined to its puck, flipping at the edge rather than detaching. */
export function cardGeometry(x: number, y: number, width: number, height: number) {
  const cardWidth = Math.min(420, Math.max(0, width - GAP * 2))
  const right = x + 32 + cardWidth > width - GAP
  const left = right ? Math.max(GAP - x, PUCK - 32 - cardWidth) : Math.min(32, width - GAP - x - cardWidth)
  const top = Math.max(GAP - y, Math.min(0, height - GAP - y - Math.min(570, height - GAP * 2)))
  return { left, top, width: cardWidth, maxHeight: Math.max(80, Math.min(570, height - GAP * 2)), flip: right }
}

const words = (v: unknown) => typeof v === 'string' ? v : ''
const object = (v: unknown): Record<string, unknown> => v && typeof v === 'object' ? v as Record<string, unknown> : {}
export function resultTitle(r: RouteResult): string {
  const v = object(r.value)
  return words(v.title) || words(v.name) || (r.kind === 'post' ? `Post${r.number ? ` #${r.number}` : ''}` : `${r.kind === 'image' ? 'Image' : 'File'} from a collected post`)
}
export function resultPreview(r: RouteResult): string {
  const v = object(r.value), p = object(v.preview)
  return (words(v.text) || words(v.preview) || words(p.text)).replace(/\s+/g, ' ').slice(0, 180)
}
export const isCollectedFile = (r: RouteResult) => ['file', 'attachment', 'image'].includes(r.kind)
export function activityWords(activity: unknown, previousOpen?: number) {
  if (typeof activity !== 'number' || !Number.isFinite(activity) || activity < 0) return 'Source activity unavailable.'
  if (!previousOpen) return 'Source activity reported; no last-open baseline in this tab yet.'
  return activity * 1000 > previousOpen ? 'Source activity is newer than this tab’s last-open time.' : 'No newer source activity reported since this tab last opened it.'
}

export interface MagnetProps {
  resource: MagnetResource
  onExpand: () => void
  onCollapse: () => void
  onClose: () => void
  onPost: (result: RouteResult) => void
  onFile: (result: RouteResult) => void
  onSource: () => void
  onConversation: () => void
  onOrigin: () => void
}

/** Presentation only: every navigation is emitted to Quiet's guarded host. */
export default function Magnet({ resource, onExpand, onCollapse, onClose, onPost, onFile, onSource, onConversation, onOrigin }: MagnetProps) {
  const s = useSyncExternalStore(resource.subscribe, resource.snapshot, resource.snapshot)
  const root = useRef<HTMLDivElement>(null)
  const puck = useRef<HTMLButtonElement>(null)
  const drag = useRef<{ pointer: number; x: number; y: number; startX: number; startY: number; moved: boolean } | null>(null)
  const suppress = useRef(false)
  const dismissedFocus = useRef(false)
  const [hover, setHover] = useState(false)
  const [focused, setFocused] = useState(false)
  const [dragging, setDragging] = useState(false)
  const [size, setSize] = useState({ width: 1024, height: 768 })
  const cardId = useId()
  const open = !dragging && (hover || focused || s.pinned || s.expanded)
  const saved = resource.saved
  const source = saved.config?.sources?.[0]
  const sourceId = source?.kind === 'conversation' ? source.conversation : null
  const own = saved.config?.conversation
  const hasOwn = typeof own === 'string' && /^ent-[a-z0-9]{6,40}$/i.test(own) && own !== sourceId
  const title = s.title || saved.name || 'Magnet'
  const posts = s.results.filter((r) => r.kind === 'post')
  const files = s.results.filter(isCollectedFile)
  const tally = s.summary?.summary?.posts
  const postCount = typeof tally === 'number' && Number.isFinite(tally) && tally >= 0 ? tally : null
  const partial = !!s.next || (s.status != null && s.status !== 'ok')
  const geometry = cardGeometry(s.x, s.y, size.width, size.height)

  useEffect(() => {
    const parent = root.current?.parentElement
    if (!parent) return
    const resized = () => {
      const r = parent.getBoundingClientRect()
      setSize({ width: r.width, height: r.height })
      const now = resource.snapshot(), p = clampPuck(now.x, now.y, r.width, r.height)
      if (p.x !== now.x || p.y !== now.y) resource.update(p)
    }
    resized()
    const observer = new ResizeObserver(resized)
    observer.observe(parent)
    return () => observer.disconnect()
  }, [resource])

  useEffect(() => {
    if (open && !drag.current) void resource.read()
    else if (!open) resource.cancel()
  }, [open, resource])

  useEffect(() => {
    const blur = () => {
      drag.current = null
      setDragging(false)
      suppress.current = true
      setHover(false)
    }
    window.addEventListener('blur', blur)
    return () => window.removeEventListener('blur', blur)
  }, [])

  const focusPuck = () => requestAnimationFrame(() => puck.current?.focus())
  const dismiss = () => {
    dismissedFocus.current = true
    resource.cancel()
    resource.update({ pinned: false })
    setHover(false)
    setFocused(false)
    if (s.expanded) onCollapse()
    focusPuck()
  }
  const pin = () => {
    if (suppress.current) { suppress.current = false; return }
    dismissedFocus.current = false
    if (!s.pinned) resource.update({ pinned: true, previousOpen: s.openedAt, openedAt: Date.now() })
    else dismiss()
  }
  const down = (e: ReactPointerEvent<HTMLButtonElement>) => {
    if (e.button !== 0) return
    drag.current = { pointer: e.pointerId, x: e.clientX, y: e.clientY, startX: s.x, startY: s.y, moved: false }
    suppress.current = false
    e.currentTarget.setPointerCapture(e.pointerId)
  }
  const move = (e: ReactPointerEvent<HTMLButtonElement>) => {
    const d = drag.current
    if (!d || d.pointer !== e.pointerId) return
    const dx = e.clientX - d.x, dy = e.clientY - d.y
    if (!d.moved && Math.hypot(dx, dy) < DRAG_THRESHOLD) return
    d.moved = true
    setDragging(true)
    suppress.current = true
    setHover(false)
    setFocused(false)
    resource.update(clampPuck(d.startX + dx, d.startY + dy, size.width, size.height))
  }
  const end = (e: ReactPointerEvent<HTMLButtonElement>, cancel = false) => {
    const d = drag.current
    if (!d || d.pointer !== e.pointerId) return
    drag.current = null
    setDragging(false)
    suppress.current = d.moved || cancel
    if (e.currentTarget.hasPointerCapture(e.pointerId)) e.currentTarget.releasePointerCapture(e.pointerId)
  }
  const tab = (which: MagnetTab) => resource.update({ tab: which })
  const rows = (items: RouteResult[], quick: boolean) => <ul className="q2-magnet-items">
    {(quick ? items.slice(0, 2) : items).map((r) => <li key={`${r.kind}:${r.id}:${r.version ?? ''}`}>
      <span className="q2-magnet-attribution">{r.number ? `#${r.number} · ` : ''}{r.author ? `${r.author} · ` : ''}{r.kind === 'attachment' ? 'Attachment · ' : ''}Source post</span>
      <button type="button" className="q2-magnet-item" onClick={() => r.kind === 'post' ? onPost(r) : onFile(r)}>{resultTitle(r)}</button>
      {(resultPreview(r) || (object(s.summary?.latest).id === r.id && words(object(s.summary?.latest).preview))) && <p className="q2-magnet-preview">{resultPreview(r) || words(object(s.summary?.latest).preview).slice(0, 200)}</p>}
      {r.kind !== 'post' && <button type="button" className="q2-magnet-link q2-magnet-at-post" onClick={() => onPost({ ...r, kind: 'post', id: r.post ?? words(object(r.value).post) })}>Open source post →</button>}
    </li>)}
  </ul>
  const empty = (what: string) => <p className="q2-magnet-muted">{s.loading ? 'Reading…' : s.error || s.reason || (partial ? `No ${what} in the page read so far. More may be available.` : `No ${what} in this collection's selected scope.`)}</p>
  const postsSection = (quick: boolean) => <section>
    <div className="q2-magnet-section-title"><h3>Posts {postCount !== null && <span className="q2-magnet-count">{postCount}</span>}</h3>{quick && <button type="button" className="q2-magnet-link" onClick={onExpand}>All →</button>}</div>
    <p className="q2-magnet-muted">{postCount !== null ? 'Posts in source; selected dates may narrow the pages below.' : 'Posts in source: unavailable.'}</p>
    {posts.length ? rows(posts, quick) : empty('posts')}
  </section>
  const filesSection = (quick: boolean) => <section>
    <div className="q2-magnet-section-title"><h3>Files {(files.length > 0 || s.status === 'ok' || s.status === 'partial') && <span className="q2-magnet-count">{files.length}</span>}</h3>{quick && <button type="button" className="q2-magnet-link" onClick={onExpand}>All →</button>}</div>
    <p className="q2-magnet-muted">Files loaded{!s.status && !files.length ? ': unavailable until this page answers.' : partial ? '; collection is paged or partial.' : '; from the pages read.'}</p>
    {files.length ? rows(files, quick) : empty('files')}
  </section>
  const scope = <div className="q2-magnet-scope">
    <p>From one source conversation. Reads on request. Selected types: {(saved.config?.selection.informationTypes?.length ? saved.config.selection.informationTypes : ['post', 'file', 'image']).join(', ')}.</p>
    {saved.config?.selection.dates && <p>Selected dates: {saved.config.selection.dates.after || 'any start'} to {saved.config.selection.dates.before || 'any end'}.</p>}
    {saved.config && ['criteria', 'phrases', 'topics', 'filters'].some((k) => !!saved.config?.selection[k as keyof typeof saved.config.selection]) && <p>Criteria, phrases, topics and filters are kept with the Magnet; this source does not apply them.</p>}
    <p>Change tracking unavailable.</p>
    <p>{s.previousOpen ? 'Activity is compared with this tab’s last-open time only; there is no shared read state.' : 'No last-open baseline in this tab yet.'}</p>
  </div>

  return <div ref={root} className={`q2-magnet${s.expanded ? ' q2-magnet-expanded' : ''}${geometry.flip ? ' q2-magnet-flipped' : ''}${s.y > size.height - 126 ? ' q2-magnet-low' : ''}`}
    data-magnet={saved.id} style={s.expanded ? undefined : { left: s.x, top: s.y }}
    onMouseEnter={() => { if (!drag.current && !suppress.current) { dismissedFocus.current = false; setHover(true) } }}
    onMouseLeave={() => { suppress.current = false; setHover(false); if (!s.pinned && !s.expanded && !focused) resource.cancel() }}
    onFocus={(e) => { if (!(dismissedFocus.current && (e.target as EventTarget) === puck.current)) setFocused(true) }} onBlur={(e) => { if (!e.currentTarget.contains(e.relatedTarget as Node | null)) { dismissedFocus.current = false; setFocused(false); if (!s.pinned && !s.expanded) resource.cancel() } }}
    onKeyDown={(e) => { if (e.key === 'Escape') { e.stopPropagation(); dismiss() } }}>
    <button ref={puck} type="button" className="q2-magnet-puck" aria-label={`${title} Magnet`} aria-expanded={open} aria-controls={cardId}
      onClick={pin} onPointerDown={down} onPointerMove={move} onPointerUp={(e) => end(e)} onPointerCancel={(e) => end(e, true)}
      onKeyDown={(e) => {
        const delta = e.shiftKey ? 40 : 12
        const directions: Record<string, [number, number]> = { ArrowLeft: [-delta, 0], ArrowRight: [delta, 0], ArrowUp: [0, -delta], ArrowDown: [0, delta] }
        const d = directions[e.key]
        if (d) { e.preventDefault(); resource.update(clampPuck(s.x + d[0], s.y + d[1], size.width, size.height)) }
      }}><span aria-hidden="true">{title.trim().charAt(0).toUpperCase() || 'M'}</span><i aria-hidden="true">▤</i></button>
    {!open && <span className="q2-magnet-rest-title">{title}</span>}
    {open && <div id={cardId} role="region" aria-label={`${title} collection`} className="q2-magnet-card" style={s.expanded ? undefined : { left: geometry.left, top: geometry.top, width: geometry.width, maxHeight: geometry.maxHeight } as CSSProperties}>
      <header><h2>{title}</h2><button type="button" className="q2-magnet-dismiss" aria-label={s.expanded ? 'Return to quick card' : 'Dismiss quick card'} onClick={dismiss}>×</button></header>
      <div className="q2-magnet-body">
        {s.loading && <p className="q2-magnet-muted" role="status">Reading this collection…</p>}
        <p className="q2-magnet-muted">{activityWords(s.summary?.summary?.activity, s.previousOpen)}</p>
        {(s.error || (s.status && s.status !== 'ok')) && <p className="q2-magnet-read-status" role="status">{s.error || `${s.status}: ${s.reason || 'Only what could be read is shown.'}`}</p>}
        <div className="q2-magnet-conversations"><button type="button" className="q2-magnet-link" onClick={onSource}>Source conversation →</button><button type="button" className="q2-magnet-link" disabled={!hasOwn} onClick={onConversation}>Magnet conversation →</button></div>
        {!hasOwn && <p className="q2-magnet-muted">Magnet conversation unavailable: no distinct valid saved conversation is present. Creation and repair are deferred.</p>}
        {s.expanded && <div className="q2-magnet-tabs" role="tablist" aria-label="Collection detail">{(['Overview', 'Posts', 'Files', 'Perspectives'] as const).map((t) => <button type="button" key={t} role="tab" aria-selected={s.tab === t} onClick={() => tab(t)}>{t}</button>)}</div>}
        {!s.expanded ? <>{postsSection(true)}{filesSection(true)}<section className="q2-magnet-perspectives-link"><button type="button" className="q2-magnet-link" onClick={onExpand}>Perspectives →</button><span>Questions and AI summaries · unavailable</span></section><p className="q2-magnet-muted">Change tracking unavailable.</p></>
          : <div role="tabpanel" aria-label={s.tab}>{s.tab === 'Overview' ? <>{scope}{postsSection(true)}{filesSection(true)}</> : s.tab === 'Posts' ? postsSection(false) : s.tab === 'Files' ? filesSection(false) : <section className="q2-magnet-unavailable"><h3>Perspectives unavailable</h3><p>Questions and AI summaries of this collection are not implemented in this candidate. No Perspectives have been created or populated.</p></section>}</div>}
        {s.expanded && s.tab !== 'Perspectives' && <div className="q2-magnet-read-actions">
          {s.next && <button type="button" className="q2-magnet-more" disabled={s.loading} onClick={() => void resource.read(true)}>Load more</button>}
          {(s.status === 'partial' || s.status === 'busy' || s.error) && <button type="button" className="q2-magnet-more" disabled={s.loading} onClick={() => void resource.read(false)}>Retry this page</button>}
        </div>}
      </div>
      <footer><button type="button" className="q2-magnet-link" onClick={onOrigin}>← Back to origin</button>{s.expanded ? <button type="button" className="q2-magnet-primary" onClick={onCollapse}>Back to collection</button> : <button type="button" className="q2-magnet-primary" onClick={onExpand}>Open details →</button>}</footer>
      <details className="q2-magnet-move"><summary>Move Magnet</summary><p>Drag the puck or focus it and use arrow keys. Shift moves farther.</p><div><button type="button" onClick={() => resource.update(clampPuck(GAP, GAP, size.width, size.height))}>Reset position</button><button type="button" onClick={onClose}>Close Magnet</button></div></details>
    </div>}
  </div>
}
