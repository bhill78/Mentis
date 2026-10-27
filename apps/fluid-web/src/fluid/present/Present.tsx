/* HOW A ZONE SHOWS WHAT IT HOLDS (#448, #442 area 2; pack section 6).
 *
 *   cards     each object in a card; as many tracks as the width holds
 *             (adm-c93a 5.2: 1 to 3), each drawn at the size its track allows
 *   gallery   a grid of plates, sized to the zone
 *   slides    one at a time, filling the zone; arrows, dots, keys
 *   list      one line each
 *   focus     one large, the rest as a strip below (a tall zone) or a list
 *             beside it (a wide one)
 *   previews  several at once, each as tall as its content, wide things
 *             across two columns
 *   across    side by side (B7): one row of previews across the zone, each
 *             as tall as the zone, scrolled sideways
 *
 * Every mode draws through the same item, which adapts to the box it is
 * given (size.ts) and opens out of itself: a picture into the post-scoped
 * viewer (#188: attachments open in the media viewer, limited to that post),
 * anything else through the zone's `onOpen` (charts, tables and documents
 * open over the arrangement from their card). */

import { useEffect, useLayoutEffect, useRef, useState, type KeyboardEvent as ReactKey, type ReactNode } from 'react'
import * as nav from '../nav'
import { store, type PostObjectEntry } from '../store'
import ObjectBody from '../workspace/ObjectBody'
import { From } from '../workspace/from'
import { useFlickable } from '../workspace/flick'
import { titleOf, useNav, useObject, usePost } from '../workspace/hooks'
import { flash } from '../workspace/motion'
import { focusObject, opener } from '../workspace/open'
import { openSuggested } from '../workspace/suggested'
import { openMedia } from './viewer'
import { declaredOf, fitFor, isPicture, isViewable, sizeOf, type Fit } from './size'
import type { ObjectRef, PresentProps } from './types'
import { Glyph, SourceMark } from './marks'
import { kindOf } from '../../experimental/objectkinds'

const GAP = 12
const PAD = 24 /* a card's padding, both sides */

/** The kind an object is, in a word, for the list and a plate's caption:
 *  the kind registry's word (experimental/objectkinds.ts), the chip's. */
export const kindWord = (o: PostObjectEntry): string => kindOf(o).word

/** Open an object: a picture (or sound, film) in the viewer, anything else
 *  through the zone's `onOpen`. */
function useOpen(item: ObjectRef, onOpen: PresentProps['onOpen']) {
  return (o: PostObjectEntry | null, el: HTMLElement | null) => {
    if (o && isViewable(o)) openMedia(item.address, el)
    else onOpen(item, el)
  }
}

/* A drawn object can be dragged onto another zone, or flicked toward one
   (stream A: a followed one is kept there, a kept one moves; Ctrl keeps a
   copy; workspace/flick.ts). */

/** Returned into (spec 1.7): the ring stays 300ms, then flashes and fades. */
function useReturned(address: string, ref: React.RefObject<HTMLElement | null>) {
  const [on, setOn] = useState(false)
  useEffect(() => {
    let t: number | undefined
    const off = nav.onReturnTo((a) => {
      if (a.kind !== 'object' || a.address !== address) return
      if (opener.el && opener.el !== ref.current && opener.el.isConnected) return
      setOn(true)
      clearTimeout(t)
      t = window.setTimeout(() => { setOn(false); flash(ref.current) }, 300)
    })
    return () => { off(); clearTimeout(t) }
  }, [address, ref])
  return on
}

/** An object that is not read yet is asked for once, wherever it is shown. */
function useLoaded(address: string) {
  const st = useObject(address)
  useEffect(() => { if (!st) void store.loadObject(address).catch(() => {}) }, [st, address])
  return st
}

/** NOTHING FITS: a readable plate, with Open wider (adm-c93a 3.3). */
function Readable({ o, open }: { o: PostObjectEntry; open: () => void }) {
  return (
    <div className="pz-readable">
      <span className="pz-kind">{kindWord(o)}</span>
      <span className="wk-quiet">Too small here to draw.</span>
      <button className="pz-wider" data-act="wider" onClick={(e) => { e.stopPropagation(); open() }}>Open wider</button>
    </div>
  )
}

/** A body clipped to its card, which fades out only where it was cut. */
function Clipped({ className, children }: { className: string; children: ReactNode }) {
  const ref = useRef<HTMLDivElement | null>(null)
  useLayoutEffect(() => {
    const el = ref.current
    if (!el) return
    const check = () => el.toggleAttribute('data-over', el.scrollHeight > el.clientHeight + 2)
    check()
    const ro = new ResizeObserver(check)
    ro.observe(el)
    if (el.firstElementChild) ro.observe(el.firstElementChild)
    return () => ro.disconnect()
  })
  return <div ref={ref} className={className}>{children}</div>
}

/** One object's body at the size its box allows. */
function Body({ o, fit, open }: { o: PostObjectEntry; fit: Fit; open: () => void }) {
  if (fit === 'fallback') return <Readable o={o} open={open} />
  return <ObjectBody o={o} size={fit} />
}

/* FOLDED WHERE ITS AUTHOR SAID open=false (adm-c93a 3.1, L8): a card starts
   as its title, and ▸ shows it. Each card's choice is its own -- the same
   object in two zones folds separately -- and lasts while this page does. */
const folds = new Map<string, boolean>()

/** One object as a card: Keep... and the expand mark on hover (and the cross
 *  where it is kept), its body sized to the card, its caption tracing it to
 *  its post. An object that names a page offers it (adm-c93a 5.1, L8). */
export function Card({ item, w, h, onOpen, onKeep, onRemove, className }: {
  item: ObjectRef; w: number; h: number; onOpen: PresentProps['onOpen']; onKeep: PresentProps['onKeep']
  onRemove?: PresentProps['onRemove']; className?: string
}) {
  const { address } = item
  const st = useLoaded(address)
  const ref = useRef<HTMLDivElement | null>(null)
  const returning = useReturned(address, ref)
  const n = useNav()
  const open = useOpen(item, onOpen)
  const [, redraw] = useState(0)
  const flick = useFlickable(item)
  const foldKey = (item.zone ?? '') + '|' + address
  if (!st) return <div className={'wk-obj pz-item wk-pending' + (className ? ' ' + className : '')} data-address={address} aria-busy="true" />
  if ('unresolved' in st)
    return (
      <div className={'wk-obj pz-item wk-unresolved fw-unresolved' + (className ? ' ' + className : '')} data-address={address} ref={ref}>
        <div className="wk-acts">
          {item.kept && onRemove && <button onClick={(e) => { e.stopPropagation(); onRemove(item) }}>Remove</button>}
        </div>
        <h4>Not found</h4>
        <p className="wk-quiet">This object no longer resolves: {st.unresolved}.</p>
      </div>
    )
  const o = st.object
  const title = titleOf(o)
  const fit = fitFor(o, w - PAD, h)
  const foldable = declaredOf(o)?.open === false
  const unfolded = folds.get(foldKey) ?? !foldable
  const fold = (on: boolean) => { folds.set(foldKey, on); redraw((x) => x + 1) }
  const shown = n.detail?.kind === 'object' && n.detail.address === address && (!opener.el || opener.el === ref.current || !opener.el.isConnected)
  const go = () => open(o, ref.current)
  const identity = o.identity === 'declared' ? `name=${o.name}` : o.identity === 'reference' ? 'by reference' : 'by position'
  return (
    <div ref={ref} data-identity={identity}
      className={'wk-obj wk-card pz-item turn-body' + (shown || returning ? ' wk-anchor' : '') + (item.kept ? ' wk-kept-here' : '') + (unfolded ? '' : ' pz-folded') + (className ? ' ' + className : '')}
      data-address={address} data-key={o.key} data-kind={o.kind === 'block' ? o.type : o.kind} data-fit={fit}
      data-folded={unfolded ? undefined : ''}
      data-kept={item.kept ? '' : undefined}
      style={h > 0 ? { ['--pz-h' as string]: h + 'px' } : undefined}
      tabIndex={0} {...flick}
      onClick={go} onKeyDown={(e) => { if (e.key === 'Enter' && e.target === e.currentTarget) go() }}>
      <div className="wk-acts">
        {o.page && (
          <button data-act="onpage" title={`Open its page, "${o.page}": everything its post marks for it`}
            onClick={(e) => { e.stopPropagation(); openSuggested(o.page!, o.post) }}>{o.page} {'↗'}</button>
        )}
        <button className="fw-keep" data-act="keep" aria-haspopup="menu"
          title="Keep it where you choose: here, in another zone, or on a page"
          onClick={(e) => { e.stopPropagation(); onKeep(item, e.currentTarget) }}>{'Keep…'}</button>
        {item.kept && onRemove && (
          <button data-act="unkeep" title="Stop keeping it here" aria-label={`Stop keeping ${title} here`}
            onClick={(e) => { e.stopPropagation(); onRemove(item) }}>{'✕'}</button>
        )}
        <button data-act="focus" title="Focus: on its own, over everything (Esc returns here)" aria-label={`Focus on ${title}`}
          onClick={(e) => { e.stopPropagation(); focusObject(address, ref.current) }}><Glyph name="focus" /></button>
        <button data-act="open" title={isViewable(o) ? 'View' : 'Open'} aria-label={`Open ${title}`}
          onClick={(e) => { e.stopPropagation(); go() }}>{'⤢'}</button>
      </div>
      <h4 title={o.stable ? `${identity}: its key survives edits that move it` : `${identity}: an edit that moves it can change which object this is`}>
        {foldable && (
          <button className="pz-fold" data-act="fold" aria-expanded={unfolded} aria-label={unfolded ? `Fold ${title}` : `Show ${title}`}
            title={unfolded ? 'Fold it to its title' : 'Show it (its author started it folded)'}
            onClick={(e) => { e.stopPropagation(); fold(!unfolded) }}>{unfolded ? '▾' : '▸'}</button>
        )}
        {title}
      </h4>
      {unfolded ? (
        <Clipped className="wk-cbody pz-body">
          <Body o={o} fit={fit} open={go} />
        </Clipped>
      ) : (
        <button className="pz-unfold" data-act="unfold" onClick={(e) => { e.stopPropagation(); fold(true) }}>
          {'▸'} Show this {kindWord(o)}
        </button>
      )}
      <div className="pz-meta">
        <SourceMark o={o} />
        <From post={o.post} kept={item.kept} />
      </div>
    </div>
  )
}

/* -- cards ----------------------------------------------------------------- */

function Cards({ items, width, height, onOpen, onKeep, onRemove }: PresentProps) {
  const tracks = Math.max(1, Math.min(3, Math.floor((width + GAP) / 256), items.length))
  const colW = tracks > 0 ? (width - GAP * (tracks - 1)) / tracks : width
  /* One row: each card may take the zone's height. More: a card is a
     preview, about half the zone, and its detail has the rest. */
  const oneRow = items.length <= tracks
  const h = oneRow ? Math.max(120, height - 72) : Math.max(140, Math.min(520, Math.round(height * 0.5)))
  return (
    <div className="pz-cards" style={{ columnCount: tracks, columnGap: GAP }} data-tracks={tracks} data-size={sizeOf(colW - PAD)}>
      {items.map((it) => <Card key={it.address} item={it} w={colW} h={h} onOpen={onOpen} onKeep={onKeep} onRemove={onRemove} />)}
    </div>
  )
}

/* -- gallery ---------------------------------------------------------------- */

function Plate({ item, size, onOpen }: { item: ObjectRef; size: number; onOpen: PresentProps['onOpen'] }) {
  const { address } = item
  const st = useLoaded(address)
  const ref = useRef<HTMLButtonElement | null>(null)
  const returning = useReturned(address, ref)
  const open = useOpen(item, onOpen)
  const flick = useFlickable(item)
  const o = st && 'object' in st ? st.object : null
  const url = o ? o.artifact?.url ?? (o.ref ? `/api/artifacts/${o.ref}` : null) : null
  return (
    <li className="pz-plate" data-address={address} data-kept={item.kept ? '' : undefined} {...flick}>
      <button ref={ref} className={'pz-platebtn wk-card' + (returning ? ' wk-anchor' : '')} data-address={address}
        style={{ height: Math.round(size * 0.75) }} disabled={!o}
        aria-label={o ? `Open ${titleOf(o)}` : 'Not found'} onClick={() => open(o, ref.current)}>
        {o && isPicture(o) && url ? <img src={url} alt={o.title ?? ''} loading="lazy" />
          : o && o.kind === 'block' && o.type === 'chart' ? <span className="pz-platebody turn-body"><ObjectBody o={o} size="compact" /></span>
            : o ? <Thumb o={o} />
              : <span className="wk-quiet">{st ? 'Not found' : ''}</span>}
      </button>
      {o && <span className="pz-cap" title={titleOf(o)}><span className="pz-kind">{kindWord(o)}</span> {titleOf(o)}</span>}
    </li>
  )
}

/* A THUMBNAIL IS THE WHOLE OBJECT, CLEAN (track 4; adm-a587e012624b). A
   table's plate showed a corner of it; a timeline's and a diagram's showed
   their zoom and pan controls. Now the object is drawn at a reading width
   -- a table as wide as its columns -- with every control and hint left
   out (present.css), and scaled whole into the plate, as a chart's plate
   is. It is a picture of the object: nothing in it can be reached or
   pressed (inert); the plate opens it. */
function Thumb({ o }: { o: PostObjectEntry }) {
  const box = useRef<HTMLSpanElement | null>(null)
  const inner = useRef<HTMLSpanElement | null>(null)
  const [at, setAt] = useState<{ k: number; x: number; y: number } | null>(null)
  useLayoutEffect(() => {
    const b = box.current, i = inner.current
    if (!b || !i) return
    const fit = () => {
      const bw = b.clientWidth, bh = b.clientHeight, iw = i.offsetWidth, ih = i.offsetHeight
      if (!bw || !bh || !iw || !ih) return
      const k = Math.min(1, bw / iw, bh / ih)
      const next = { k, x: Math.round(Math.max(0, (bw - iw * k) / 2)), y: Math.round(Math.max(0, (bh - ih * k) / 2)) }
      setAt((p) => (p && Math.abs(p.k - next.k) < 0.001 && p.x === next.x && p.y === next.y ? p : next))
    }
    fit()
    const ro = new ResizeObserver(fit)
    ro.observe(b)
    ro.observe(i)
    return () => ro.disconnect()
  }, [])
  return (
    <span ref={box} className="pz-thumbbox" inert aria-hidden="true">
      <span ref={inner} className="pz-thumbin turn-body" data-kind={o.kind === 'block' ? o.type : o.kind}
        style={at ? { transform: `translate(${at.x}px, ${at.y}px) scale(${at.k})` } : { visibility: 'hidden' }}>
        <ObjectBody o={o} size="medium" still />
      </span>
    </span>
  )
}

function Gallery({ items, width, onOpen }: PresentProps) {
  const cell = width < 420 ? 120 : width < 900 ? 160 : 200
  return (
    <ul className="pz-gallery" style={{ gridTemplateColumns: `repeat(auto-fill, minmax(${cell}px, 1fr))` }}>
      {items.map((it) => <Plate key={it.address} item={it} size={cell} onOpen={onOpen} />)}
    </ul>
  )
}

/* -- slides, focus: one at a time ------------------------------------------- */

/** Which item is shown, held by address so a change in the list keeps it. */
function useCurrent(items: ObjectRef[]) {
  const [cur, setCur] = useState<string | null>(items[0]?.address ?? null)
  const i = Math.max(0, cur ? items.findIndex((x) => x.address === cur) : 0)
  const at = items[i] ?? null
  const step = (d: number) => { if (items.length) setCur(items[(i + d + items.length) % items.length].address) }
  return { i, at, step, set: setCur }
}

const arrows = (step: (d: number) => void) => (e: ReactKey) => {
  if (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight') return
  e.preventDefault()
  e.stopPropagation()
  step(e.key === 'ArrowRight' ? 1 : -1)
}

function Slides({ items, width, height, onOpen, onKeep, onRemove }: PresentProps) {
  const { i, at, step, set } = useCurrent(items)
  if (!at) return null
  return (
    <div className="pz-slides" role="group" aria-roledescription="slideshow" aria-label={`${i + 1} of ${items.length}`} tabIndex={0} onKeyDown={arrows(step)}>
      <Card key={at.address} item={at} w={width} h={Math.max(120, height - 44 - 72)} onOpen={onOpen} onKeep={onKeep} onRemove={onRemove} className="pz-slide" />
      <div className="pz-slidebar">
        <button className="pz-step" aria-label="Previous" title="Previous (←)" onClick={() => step(-1)} disabled={items.length < 2}>{'‹'}</button>
        <span className="pz-dots" aria-hidden="true">
          {items.length <= 24
            ? items.map((a, j) => <button key={a.address} className={j === i ? 'on' : ''} tabIndex={-1} onClick={() => set(a.address)} />)
            : null}
        </span>
        <span className="pz-count" aria-live="polite">{i + 1} of {items.length}</span>
        <button className="pz-step" aria-label="Next" title="Next (→)" onClick={() => step(1)} disabled={items.length < 2}>{'›'}</button>
      </div>
    </div>
  )
}

function Row({ item, on, onPick, compact }: { item: ObjectRef; on?: boolean; onPick: (el: HTMLElement | null) => void; compact?: boolean }) {
  const { address } = item
  const st = useLoaded(address)
  const ref = useRef<HTMLButtonElement | null>(null)
  const returning = useReturned(address, ref)
  const flick = useFlickable(item)
  const o = st && 'object' in st ? st.object : null
  const url = o && isPicture(o) ? o.artifact?.url ?? (o.ref ? `/api/artifacts/${o.ref}` : null) : null
  /* Its post, read if it is not yet: a kept object restored with its place
     comes back before anything has read its post, and its row still says
     where it came from. */
  const post = usePost(o?.post ?? '')
  useEffect(() => { if (o && !post) void store.loadPosts([o.post]).catch(() => {}) }, [o, post])
  return (
    <li className={'pz-row' + (on ? ' on' : '')} data-address={address} data-kept={item.kept ? '' : undefined} {...flick}>
      <button ref={ref} className={'pz-rowbtn wk-card' + (returning ? ' wk-anchor' : '')} data-address={address}
        aria-current={on || undefined} onClick={() => onPick(ref.current)}>
        <span className="pz-thumb" aria-hidden="true">{url ? <img src={url} alt="" loading="lazy" /> : <span className="pz-glyph">{o ? GLYPH[kindWord(o)] ?? '▤' : ''}</span>}</span>
        <span className="pz-rowtext">
          <span className="pz-rowtitle">{o ? titleOf(o) : st ? 'Not found' : '…'}</span>
          {!compact && o && <span className="pz-rowmeta">{kindWord(o)}{post?.number != null ? ` · from #${post.number}` : ''}{post?.author_name ? ` · @${post.author_name.replace(/^@/, '')}` : ''}</span>}
        </span>
      </button>
    </li>
  )
}

const GLYPH: Record<string, string> = { table: '▦', chart: '▥', checklist: '☑', diagram: '◇', timeline: '┄', text: '¶', file: '▤', doc: '▤', video: '▶', audio: '♪', panel: '▣', link: '↗' }

function List({ items, onOpen }: PresentProps) {
  return (
    <ul className="pz-list">
      {items.map((it) => <ListRow key={it.address} item={it} onOpen={onOpen} />)}
    </ul>
  )
}
function ListRow({ item, onOpen }: { item: ObjectRef; onOpen: PresentProps['onOpen'] }) {
  const st = useObject(item.address)
  const open = useOpen(item, onOpen)
  return <Row item={item} onPick={(el) => open(st && 'object' in st ? st.object : null, el)} />
}

/** One object on a page of its own (Open as page), drawn whole and
 *  scrolled, as stream A's page always drew it. */
function Whole({ item }: { item: ObjectRef }) {
  const st = useLoaded(item.address)
  if (!st) return <div className="wk-obj wk-pending" data-address={item.address} aria-busy="true" />
  if ('unresolved' in st) return <p className="wk-quietline">This object no longer resolves: {st.unresolved}.</p>
  return (
    <div className="wk-big">
      <div className="wk-obj wk-paged turn-body" data-address={item.address}>
        <h4>{titleOf(st.object)}</h4>
        <ObjectBody o={st.object} big />
        <div className="pz-meta">
          <SourceMark o={st.object} />
          <From post={st.object.post} kept />
        </div>
      </div>
    </div>
  )
}

function Focus({ items, width, height, onOpen, onKeep, onRemove }: PresentProps) {
  const { i, at, step, set } = useCurrent(items)
  if (!at) return null
  if (items.length === 1) return <Whole item={at} />
  const rest = items.length > 1
  const beside = rest && width >= 720 && width > height * 0.9
  const side = beside ? Math.min(280, Math.round(width * 0.28)) : 0
  const strip = rest && !beside ? 92 : 0
  const w = beside ? width - side - GAP : width
  const h = Math.max(120, height - strip - (strip ? GAP : 0) - 72)
  return (
    <div className={'pz-focus' + (beside ? ' beside' : ' below')} tabIndex={0} onKeyDown={arrows(step)} aria-label={`focused: ${i + 1} of ${items.length}`}>
      <div className="pz-focusmain" style={{ width: w }}>
        <Card key={at.address} item={at} w={w} h={h} onOpen={onOpen} onKeep={onKeep} onRemove={onRemove} className="pz-focused" />
      </div>
      {rest && (
        <ul className={beside ? 'pz-list pz-rest' : 'pz-strip pz-rest'} style={beside ? { width: side } : { height: strip }} aria-label="the others">
          {items.map((a) => <Row key={a.address} item={a} on={a.address === at.address} compact={!beside} onPick={() => set(a.address)} />)}
        </ul>
      )}
    </div>
  )
}

/* -- previews --------------------------------------------------------------- */

/* SEVERAL PREVIEWS AT ONCE, EACH SIZED TO ITS CONTENT (track 4;
   adm-95fd47da541a). Previews gave every item the zone's whole height, so a
   checklist left most of it empty and one preview was all there was to see.
   Now they are laid on a grid of columns about 300px or more wide -- as many
   as the zone holds, tall or wide -- and each is as tall as what it shows,
   never taller than most of the zone, so the next is always in view. A wide
   thing (a timeline, a diagram, a table of many columns, a landscape
   picture) takes two columns where there are two; the gaps fill densely,
   in the zone's order, and the rest scroll down. */
const PREVIEW_MIN = 300

/** How many of the grid's columns an object asks for: two for wide things. */
function spanOf(o: PostObjectEntry | null, aspect: number | null): 1 | 2 {
  if (!o) return 1
  if (isPicture(o)) return aspect != null && aspect > 1.45 ? 2 : 1
  if (o.kind !== 'block') return 1
  if (o.type === 'timeline' || o.type === 'diagram') return 2
  if (o.type === 'table') {
    const head = (o.block?.body ?? '').split('\n').find((l) => l.trim()) ?? ''
    return head.split(',').length > 4 ? 2 : 1
  }
  return 1
}

/** A picture's own shape, once it is read (the browser already has it). */
function useAspect(o: PostObjectEntry | null) {
  const url = o && isPicture(o) ? o.artifact?.url ?? (o.ref ? `/api/artifacts/${o.ref}` : null) : null
  const [aspect, setAspect] = useState<number | null>(null)
  useEffect(() => {
    if (!url) return
    const img = new Image()
    img.onload = () => { if (img.naturalWidth && img.naturalHeight) setAspect(img.naturalWidth / img.naturalHeight) }
    img.src = url
    return () => { img.onload = null }
  }, [url])
  return aspect
}

function Preview({ item, cols, unit, maxH, onOpen, onKeep, onRemove }: {
  item: ObjectRef; cols: number; unit: number; maxH: number
  onOpen: PresentProps['onOpen']; onKeep: PresentProps['onKeep']; onRemove?: PresentProps['onRemove']
}) {
  const st = useObject(item.address)
  const o = st && 'object' in st ? st.object : null
  const span = Math.min(cols, spanOf(o, useAspect(o)))
  const w = unit * span + GAP * (span - 1)
  return (
    <Card item={item} w={w} h={Math.max(120, maxH - 72)} onOpen={onOpen} onKeep={onKeep} onRemove={onRemove}
      className={'pz-preview' + (span > 1 ? ' pz-wide' : '')} />
  )
}

function Previews({ items, width, height, onOpen, onKeep, onRemove }: PresentProps) {
  const cols = Math.max(1, Math.min(4, Math.floor((width + GAP) / (PREVIEW_MIN + GAP))))
  const unit = Math.floor((width - GAP * (cols - 1)) / cols)
  /* One alone may have the zone; with others, each leaves room to see the next. */
  const maxH = items.length === 1 ? height : Math.max(220, Math.round(height * 0.7))
  return (
    <div className="pz-previews" style={{ gridTemplateColumns: `repeat(${cols}, minmax(0, 1fr))`, ['--pz-max' as string]: maxH + 'px' }} data-cols={cols}>
      {items.map((it) => <Preview key={it.address} item={it} cols={cols} unit={unit} maxH={maxH} onOpen={onOpen} onKeep={onKeep} onRemove={onRemove} />)}
    </div>
  )
}

/* -- across: side by side (B7) ------------------------------------------------ */

/* PREVIEWS SIDE BY SIDE (B7). Previews lays several down the zone; this lays
   them in one row ACROSS it, each as tall as the zone and about as wide as
   a reading column (300px or more, so two or three show at once in a wide
   zone, one and the edge of the next in a narrow one), scrolled sideways
   with the wheel, the arrows or a swipe, each snapping into place. A wide
   thing (a timeline, a diagram, a wide table or picture) takes half as much
   again. */
const ACROSS_MIN = 300

function Across({ items, width, height, onOpen, onKeep, onRemove }: PresentProps) {
  const row = useRef<HTMLDivElement | null>(null)
  const fit = Math.max(1, Math.min(3, Math.floor((width + GAP) / (ACROSS_MIN + GAP)), items.length))
  const unit = Math.max(Math.min(ACROSS_MIN, width), Math.floor((width - GAP * (fit - 1)) / fit))
  const h = Math.max(160, height - 16)
  /* The wheel scrolls the row sideways where it would otherwise do nothing
     (the zone does not scroll down: the row is as tall as the zone). */
  const wheel = (e: React.WheelEvent) => {
    const el = row.current
    if (!el || Math.abs(e.deltaY) <= Math.abs(e.deltaX) || el.scrollWidth <= el.clientWidth) return
    /* a card's own body that scrolls down keeps the wheel */
    const body = (e.target as HTMLElement).closest('.wk-cbody')
    if (body && body.scrollHeight > body.clientHeight + 2) return
    el.scrollLeft += e.deltaY
  }
  const keys = (e: ReactKey) => {
    const el = row.current
    if (!el || (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight') || e.target !== el) return
    e.preventDefault()
    el.scrollBy({ left: (e.key === 'ArrowRight' ? 1 : -1) * (unit + GAP), behavior: 'smooth' })
  }
  return (
    <div ref={row} className="pz-across" tabIndex={0} role="group" aria-label="side by side: scroll sideways"
      style={{ ['--pz-h' as string]: h + 'px', gap: GAP }} data-fit={fit} onWheel={wheel} onKeyDown={keys}>
      {items.map((it) => <AcrossItem key={it.address} item={it} unit={unit} h={h} onOpen={onOpen} onKeep={onKeep} onRemove={onRemove} />)}
    </div>
  )
}

function AcrossItem({ item, unit, h, onOpen, onKeep, onRemove }: {
  item: ObjectRef; unit: number; h: number
  onOpen: PresentProps['onOpen']; onKeep: PresentProps['onKeep']; onRemove?: PresentProps['onRemove']
}) {
  const st = useObject(item.address)
  const o = st && 'object' in st ? st.object : null
  const wide = spanOf(o, useAspect(o)) > 1
  const w = Math.round(wide ? unit * 1.5 : unit)
  return (
    <div className="pz-acrossitem" style={{ width: w, flex: `0 0 ${w}px` }}>
      <Card item={item} w={w} h={Math.max(120, h - 72)} onOpen={onOpen} onKeep={onKeep} onRemove={onRemove}
        className={'pz-preview pz-acrosscard' + (wide ? ' pz-wide' : '')} />
    </div>
  )
}

const MODES: Record<PresentProps['mode'], (p: PresentProps) => ReactNode> = {
  cards: Cards, gallery: Gallery, slides: Slides, list: List, focus: Focus, previews: Previews, across: Across,
}

/** THE SEAM (pack section 6): a zone body draws its objects through this. */
export default function Present(props: PresentProps) {
  const { items, mode } = props
  /* Before the zone has been measured, draw nothing rather than at 0px. */
  const ready = props.width > 0
  const Draw = MODES[mode] ?? Cards
  if (!items.length) return null
  return (
    <div className="pz" data-present={mode} data-items={items.length}>
      {ready ? <Draw key={mode} {...props} /> : null}
    </div>
  )
}
