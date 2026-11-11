/* ONE POST, EDITORIAL.
 *
 * A substantial post reads like an article: topics, a title, the byline, the
 * body at reading measure. A brief post stays a line in the conversation: a
 * small byline and its words, its controls shown only when it is pointed at.
 *
 * Material that belongs beside a passage (an annotation, an extra picture, a
 * form) is a small mark in the margin at that passage's height; it opens
 * there on request and reserves nothing while closed. Wide material breaks
 * out of the column and the text returns to its measure after it. */
import { createContext, useCallback, useContext, useEffect, useLayoutEffect, useRef, useState, type ReactNode } from 'react'
import { READ_ONLY } from './live'
import { editPost } from '../fluid/actions'
import { useLayer } from '../fluid/frame/layer'
import { Avatar } from '../fluid/identity/Who'
import { Prose } from '../prose'
import type { ViewerItem } from '../quiet/media/view'
import { useLink, pointAt } from './links'
import { workingOn, type Working } from './presence'
import { postOf, readThread, threadSize } from './real'
import type { GalleryLayout, Viewable, ViewerSource, ViewImage } from './viewer/types'
import { repairText } from './text'
import { readPrefs, savePrefs } from './prefs'
import Margin from './annotate/Margin'
import { DogEar, StatusLine, useStatus } from './status/DogEar'
import type { Aside, Attachment, Block, Id, Person, Picture, Post as PostT } from './sample'
import './collections.css'

const item = (p: Picture): ViewerItem => p.item ?? ({ url: p.src, name: p.caption ?? p.alt, alt: p.alt, kind: 'image', ref: '', mediaType: 'image/svg+xml', size: null })

const imageOf = (p: Picture): ViewImage => { const i = item(p); return { url: i.url, name: i.name, alt: i.alt } }

/** Opening a picture: every picture goes to the unified viewer as the post's
 *  pictures, starting at it (a margin picture, not among them, alone). */
function useOpenPicture(post: PostT) {
  const page = usePage()
  return (p: Picture, at?: number) => {
    const all = picturesOf(post)
    const start = at ?? all.findIndex((x) => x.url === item(p).url)
    page.onView(start >= 0 ? { kind: 'gallery', images: all, start } : { kind: 'gallery', images: [imageOf(p)], start: 0 }, { conversation: post.conversation, post: post.id })
  }
}

/** How many of a collection are shown before "+N more". */
const SHOWN = 4

/* -- icons: one stroke, one size ------------------------------------------ */
const I = ({ d, size = 18 }: { d: ReactNode; size?: number }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{d}</svg>
)
export const Icon = {
  reply: <I d={<path d="M20 15a7 7 0 0 1-7 7H5l2.5-3A8 8 0 1 1 20 15Z" />} />,
  edit: <I d={<><path d="M4 20h4L19 9l-4-4L4 16v4Z" /><path d="m13.5 6.5 4 4" /></>} />,
  keep: <I d={<path d="M7 3h10v18l-5-4-5 4V3Z" />} />,
  link: <I d={<><path d="M10 14a4 4 0 0 0 5.6 0l3-3a4 4 0 0 0-5.6-5.6l-1 1" /><path d="M14 10a4 4 0 0 0-5.6 0l-3 3a4 4 0 0 0 5.6 5.6l1-1" /></>} />,
  more: <I d={<><circle cx="5" cy="12" r="1" /><circle cx="12" cy="12" r="1" /><circle cx="19" cy="12" r="1" /></>} />,
  note: <I size={14} d={<><path d="M4 5h16v11H9l-5 4V5Z" /></>} />,
  image: <I size={14} d={<><rect x="3" y="5" width="18" height="14" rx="2" /><circle cx="9" cy="10" r="1.5" /><path d="m21 16-5-5-9 8" /></>} />,
  form: <I size={14} d={<><rect x="4" y="3" width="16" height="18" rx="2" /><path d="M8 8h8M8 12h8M8 16h5" /></>} />,
  beside: <I size={15} d={<><rect x="3" y="4" width="18" height="16" rx="2" /><path d="M13 4v16" /><path d="m7 10 2 2-2 2" /></>} />,
  file: <I size={16} d={<><path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8l-5-5Z" /><path d="M14 3v5h5" /></>} />,
}

/* -- the byline ----------------------------------------------------------- */
function Byline({ post, onWho, filtered, marks, onThread }: { post: PostT; onWho: (p: Person) => void; filtered: boolean; marks?: ReactNode; onThread?: () => void }) {
  const big = post.weight === 'article'
  return (
    <div className={'q2-byline' + (big ? ' big' : '')}>
      {marks}
      <Avatar id={post.by.id} name={post.by.name} size={big ? 36 : 26} />
      <div className="q2-byline-words">
        <span className="q2-byline-who">
          <button className="q2-name" onClick={() => onWho(post.by)} aria-pressed={filtered}
            title={filtered ? 'Show everyone again' : `Show only ${post.by.name}'s posts`}>{post.by.name.replace(/^@/, '')}</button>
          {post.by.agent && <span className="q2-agent">agent</span>}
          {post.requestedBy && (
            <span className="q2-asked">asked by <button className="q2-name small" onClick={() => onWho(post.requestedBy!)}>{post.requestedBy.name.replace(/^@/, '')}</button></span>
          )}
        </span>
        <span className="q2-byline-meta"><time>{post.at}</time>{big && <> · {readMinutes(post)} min read</>}
          {/* THE THREAD FROM THE HEADER: the same entry as Read the thread */}
          {onThread && <> · <button className="q2-thread-link" onClick={onThread} title="Read the whole thread" aria-label={`Read the whole thread${post.number ? ` of #${post.number}` : ''}`}>
            {Icon.reply}{post.number ? <span>#{post.number}</span> : null}</button></>}
        </span>
      </div>
    </div>
  )
}

const readMinutes = (p: PostT) => Math.max(1, Math.round(p.blocks.reduce((n, b) => n + (b.kind === 'text' ? b.md.split(/\s+/).length : 0), 0) / 220))

/* -- margin material ------------------------------------------------------ */
const asideIcon = (a: Aside) => a.kind === 'annotation' ? Icon.note : a.kind === 'media' ? Icon.image : Icon.form
const asideLabel = (a: Aside) => a.kind === 'annotation' ? `Annotation by ${a.by.name}` : a.kind === 'media' ? `Picture: ${a.image.alt}` : `Form: ${a.title}`

function AsideCard({ a, post }: { a: Aside; post: PostT }) {
  const open = useOpenPicture(post)
  if (a.kind === 'annotation') return (
    <>
      <div className="q2-aside-head"><Avatar id={a.by.id} name={a.by.name} size={18} /> <b>{a.by.name.replace(/^@/, '')}</b> <span>{a.at}</span></div>
      <p>{a.text}</p>
    </>
  )
  if (a.kind === 'media') return (
    <figure>
      <button className="q2-pic" onClick={() => open(a.image)} aria-label={`View ${a.image.alt} larger`}><img src={a.image.src} alt={a.image.alt} /></button>
      {a.image.caption && <figcaption>{a.image.caption}</figcaption>}
    </figure>
  )
  return (
    <>
      <div className="q2-aside-head"><b>{a.title}</b> <span>{a.state}</span></div>
      <ol className="q2-form-fields">{a.fields.map((f) => <li key={f}>{f}</li>)}</ol>
      <button className="q2-aside-open">Open form</button>
    </>
  )
}

/** Where an aside's card goes. Beside its mark, in the margin, where the
 *  margin has room for it; otherwise under the mark (above it if the window
 *  has no room below), as wide as is useful and no wider than the window.
 *  Always inside the window: what cannot fit scrolls inside the card. */
export interface AsidePlace { left: number; top: number; width: number; maxHeight: number; mode: 'beside' | 'below' | 'above' }
const EDGE = 8, GAP = 10, TOP = 60, BESIDE_MIN = 240
export function placeAside(mark: DOMRect, col: DOMRect, heightAt: (width: number) => number, want: { beside: number; below: number }, vw: number, vh: number): AsidePlace {
  const maxHeight = vh - TOP - EDGE
  const room = vw - mark.right - GAP - EDGE
  /* beside only when the mark stands in the margin: a mark under its passage
     (no margin to spare) opens below it rather than over the next one */
  if (mark.left >= col.right && room >= BESIDE_MIN) {
    const width = Math.min(want.beside, room)
    const h = Math.min(heightAt(width), maxHeight)
    const top = Math.min(Math.max(mark.top - 4, TOP), vh - EDGE - h)
    return { left: mark.right + GAP, top, width, maxHeight, mode: 'beside' }
  }
  const width = Math.min(want.below, vw - 2 * EDGE)
  const h = heightAt(width)
  const left = Math.min(Math.max(col.left + (col.width - width) / 2, EDGE), vw - EDGE - width)
  const below = vh - EDGE - (mark.bottom + GAP)
  const above = mark.top - GAP - TOP
  if (h <= below) return { left, top: mark.bottom + GAP, width, maxHeight: below, mode: 'below' }
  if (h <= above) return { left, top: mark.top - GAP - h, width, maxHeight: above, mode: 'above' }
  /* neither side holds it whole: it takes the roomier side and shrinks to
     it (a picture scales down), so the mark and its passage stay in view */
  return below >= above
    ? { left, top: mark.bottom + GAP, width, maxHeight: Math.max(below, 120), mode: 'below' }
    : { left, top: Math.max(TOP, mark.top - GAP - above), width, maxHeight: Math.max(above, 120), mode: 'above' }
}

/** The card's natural height at `width`, independent of how it was last
 *  placed: a picture's from its own proportions, anything else as drawn. */
function heightOf(card: HTMLElement, kind: Aside['kind']) {
  const img = kind === 'media' ? card.querySelector('img') : null
  const drawnW = card.getBoundingClientRect().width || 1
  const drawnH = card.scrollHeight
  return (width: number) => {
    if (img && img.naturalWidth) {
      const chrome = drawnH - img.getBoundingClientRect().height
      return (width - 16) * (img.naturalHeight / img.naturalWidth) + chrome
    }
    /* text reflows: scale its height by the change in width, roughly */
    return drawnH * Math.max(1, drawnW / width)
  }
}

const WANT: Record<Aside['kind'], { beside: number; below: number }> = {
  annotation: { beside: 280, below: 420 },
  form: { beside: 300, below: 420 },
  /* a picture may be larger than the reading column when there is room */
  media: { beside: 480, below: 720 },
}

function Asides({ asides, id, post }: { asides: Aside[]; id: string; post: PostT }) {
  const [open, setOpen] = useState<number | null>(null)
  const [at, setAt] = useState<AsidePlace | null>(null)
  const marks = useRef<(HTMLButtonElement | null)[]>([])
  const card = useRef<HTMLDivElement | null>(null)
  const place = useCallback(() => {
    if (open === null) return
    const m = marks.current[open], c = card.current
    const col = m?.closest('.q2-col') ?? m?.closest('.q2-conv')
    if (!m || !c || !col) return
    setAt(placeAside(m.getBoundingClientRect(), col.getBoundingClientRect(), heightOf(c, asides[open].kind), WANT[asides[open].kind], window.innerWidth, window.innerHeight))
  }, [open, asides])
  useLayoutEffect(() => {
    if (open === null) { setAt(null); return }
    place()
    /* a picture arriving changes the card's height: place it again (its
       arrival, not the card's size, so placing cannot feed back on itself) */
    const loaded = () => place()
    const watch = requestAnimationFrame(() => { card.current?.querySelectorAll('img').forEach((i) => i.addEventListener('load', loaded)); place() })
    const away = (e: PointerEvent) => {
      const t = e.target as Node
      if (!card.current?.contains(t) && !marks.current.some((m) => m?.contains(t))) setOpen(null)
    }
    const esc = (e: KeyboardEvent) => { if (e.key === 'Escape') { setOpen(null); marks.current[open]?.focus() } }
    window.addEventListener('resize', place); window.addEventListener('scroll', place, true)
    document.addEventListener('pointerdown', away); document.addEventListener('keydown', esc)
    return () => {
      cancelAnimationFrame(watch); card.current?.querySelectorAll('img').forEach((i) => i.removeEventListener('load', loaded))
      window.removeEventListener('resize', place); window.removeEventListener('scroll', place, true)
      document.removeEventListener('pointerdown', away); document.removeEventListener('keydown', esc)
    }
  }, [open, place])
  /* the card is drawn in the page's layer, outside the conversation's
     container, so the window is what it is placed against */
  useLayer(open === null ? null : (
    <div ref={card} className={`q2-aside-card q2-aside-card-${asides[open].kind}` + (at ? ` ${at.mode}` : '')} id={`${id}-aside-${open}`}
      role="region" aria-label={asideLabel(asides[open])}
      style={at ? { left: at.left, top: at.top, width: at.width, maxHeight: at.maxHeight, ['--q2-card-max' as string]: at.maxHeight + 'px' } : { left: 0, top: 0, width: WANT[asides[open].kind].beside, visibility: 'hidden' }}>
      <AsideCard a={asides[open]} post={post} />
    </div>
  ))
  return (
    <div className="q2-asides" data-src-skip="">
      <div className="q2-aside-marks">
        {asides.map((a, i) => (
          <button key={i} ref={(el) => { marks.current[i] = el }} className={`q2-aside-mark q2-aside-${a.kind}` + (open === i ? ' on' : '')}
            aria-expanded={open === i} aria-controls={`${id}-aside-${i}`} aria-label={asideLabel(a)} title={asideLabel(a)}
            onClick={() => setOpen(open === i ? null : i)}>{asideIcon(a)}</button>
        ))}
      </div>
    </div>
  )
}

/* -- the body -------------------------------------------------------------
   THE MEASURE IS FOR PROSE. A table, a code block or anything else drawn
   wider than the reading column (Prose's top-level blocks other than
   paragraphs, lists, headings and quotes) takes the width it needs, up to
   what the pane it sits in can give, centred on the column as wide pictures
   are; what is wider still scrolls inside itself. Nothing widens the page.

   ONLY THE AUTHOR'S WORDS ARE WORDS. Fluid's alignment (`surfaces/passage.ts`)
   walks the text in `.q2-body` against the stored text (real.ts
   `sourceOfPost`) to place an annotation or a selection; everything else
   drawn inside the body -- the annotation layer, the open-in-a-surface
   buttons, figures and collections (captions, their bar), margin asides --
   carries `data-src-skip` so the walk never looks for it. */
const PROSE = new Set(['P', 'UL', 'OL', 'H1', 'H2', 'H3', 'H4', 'H5', 'H6', 'BLOCKQUOTE', 'HR'])
const GUTTER = 24

/** A structured element of a text block that can open in a working
 *  surface: where its action sits, and what it is. */
export interface Spot { index: number; top: number; right: number; label: string }
const labelOf = (el: HTMLElement) => el.classList.contains('pr-table-wrap') || el.tagName === 'TABLE' ? 'Table'
  : el.tagName === 'PRE' ? 'Code' : 'Rendered content'

/** The structured blocks of rendered prose, in order: the top-level
 *  elements that are not prose, a table counted once by its wrapper. Both
 *  the post and a surface showing one of them read them this way. */
export function structuredOf(prose: HTMLElement): HTMLElement[] {
  /* Prose draws its blocks directly inside the container */
  return Array.from(prose.children as HTMLCollectionOf<HTMLElement>).filter((el) => !PROSE.has(el.tagName))
}

function useBreakout(ref: React.RefObject<HTMLDivElement | null>, md: string, onSpots?: (s: Spot[]) => void) {
  /* the latest handler, so posts drawn before a surface existed still offer */
  const report = useRef(onSpots)
  report.current = onSpots
  useLayoutEffect(() => {
    const prose = ref.current
    if (!prose) return
    const pane = prose.closest<HTMLElement>('.q2-pane') ?? prose.closest<HTMLElement>('.q2-conv')
    const fit = () => {
      const col = prose.clientWidth
      const avail = Math.max(col, Math.min(1100, (pane?.clientWidth ?? col) - 2 * GUTTER))
      const structured: HTMLElement[] = []
      for (const el of structuredOf(prose)) {
        if (el.parentElement?.closest('.q2-broken-out')) continue
        el.style.width = ''; el.style.marginLeft = ''; el.classList.remove('q2-broken-out')
        structured.push(el)
        const table = el.querySelector<HTMLElement>(':scope > table')
        let natural: number
        if (table) {
          table.style.width = 'max-content'
          natural = table.getBoundingClientRect().width
          table.style.width = ''
        } else natural = el.scrollWidth
        if (natural <= col + 1) continue
        const w = Math.min(natural, avail)
        /* centred on the column, but never past either edge of the pane: a
           nested reply's column is not centred in it */
        const pr = prose.getBoundingClientRect()
        const box = pane?.getBoundingClientRect()
        let left = pr.left + (col - w) / 2
        if (box) left = Math.min(Math.max(left, box.left + GUTTER), box.right - GUTTER - w)
        el.style.width = `${w}px`
        el.style.marginLeft = `${left - pr.left}px`
        el.classList.add('q2-broken-out')
      }
      if (report.current) {
        const pr = prose.getBoundingClientRect()
        report.current(structured.map((el, index) => {
          const r = el.getBoundingClientRect()
          return { index, top: Math.round(r.top - pr.top), right: Math.round(r.right - pr.left), label: labelOf(el) }
        }))
      }
    }
    fit()
    const ro = new ResizeObserver(fit)
    ro.observe(prose)
    if (pane) ro.observe(pane)
    return () => ro.disconnect()
  }, [ref, md])
}

/** Prose, with structured content given the width it needs; each table,
 *  code block or rendered block offers to open in a working surface
 *  (`onOpen`). `focus` brings one of them into view and marks it. */
export function TextBlock({ md, scope, onOpen, focus }: { md: string; scope: string; onOpen?: (s: Spot) => void; focus?: number }) {
  const ref = useRef<HTMLDivElement>(null)
  const [spots, setSpots] = useState<Spot[]>([])
  const take = useCallback((s: Spot[]) => setSpots((was) => JSON.stringify(was) === JSON.stringify(s) ? was : s), [])
  useBreakout(ref, md, onOpen ? take : undefined)
  useEffect(() => { if (!onOpen) setSpots([]) }, [onOpen])
  useEffect(() => {
    if (focus === undefined || !ref.current) return
    const el = structuredOf(ref.current)[focus]
    if (el) { el.classList.add('q2-focused'); el.scrollIntoView({ block: 'start' }) }
  }, [focus, md])
  return (
    <div className="q2-prose-wrap">
      <div className="q2-prose" ref={ref}><Prose src={md} scope={scope} /></div>
      {onOpen && spots.map((s) => (
        <button key={s.index} data-src-skip="" className="q2-open-beside q2-open-spot" style={{ top: s.top + 6, left: s.right - 34 }}
          title={`Open this ${s.label.toLowerCase()} in a working surface`} aria-label={`Open this ${s.label.toLowerCase()} in a working surface`}
          onClick={() => onOpen(s)}>{Icon.beside}</button>
      ))}
    </div>
  )
}

/** The small action that puts something in a working surface. */
function BesideButton({ label, onClick }: { label: string; onClick: () => void }) {
  return <button className="q2-open-beside" title={label} aria-label={label} onClick={(e) => { e.stopPropagation(); onClick() }}>{Icon.beside}</button>
}

function BlockView({ b, scope, post, index }: { b: Block; scope: string; post: PostT; index: number }) {
  const page = usePage()
  const source: ViewerSource = { conversation: post.conversation, post: post.id }
  const open = useOpenPicture(post)
  /* where this block's pictures start among the post's pictures */
  const offset = post.blocks.slice(0, index).reduce((n, x) => n + (x.kind === 'figure' ? 1 : x.kind === 'wide' ? x.images.length : 0), 0)
  if (b.kind === 'wide' && b.images.length > 1) return (
    <Collection pictures={b.images} caption={b.caption} onOpen={(i) => open(b.images[i], offset + i)} />
  )
  if (b.kind === 'wide') return (
    <figure className="q2-wide" data-src-skip="" style={{ ['--n' as string]: 1 }}>
      <div className="q2-wide-row">
        <button className="q2-pic" onClick={() => open(b.images[0], offset)} aria-label={`View ${b.images[0].alt} larger`}>
          <img src={b.images[0].src} alt={b.images[0].alt} decoding="async" />
        </button>
      </div>
      {b.caption && <figcaption>{b.caption}</figcaption>}
    </figure>
  )
  return (
    <div className={'q2-block' + (b.asides?.length ? ' has-asides' : '')}>
      {b.kind === 'text'
        ? <TextBlock md={b.md} scope={scope}
            onOpen={(s) => page.onView({ kind: 'block', post: post.id, block: index, element: s.index, label: s.label }, source)} />
        : (
          <figure className="q2-figure q2-openable" data-src-skip="">
            <button className="q2-pic" onClick={() => open(b.image, offset)} aria-label={`View ${b.image.alt} larger`}><img src={b.image.src} alt={b.image.alt} decoding="async" /></button>
            {b.image.caption && <figcaption>{b.image.caption}</figcaption>}
          </figure>
        )}
      {b.asides?.length ? <Asides asides={b.asides} id={scope} post={post} /> : null}
    </div>
  )
}

/** A post's pictures, in order, as the viewer shows a collection. */
export function picturesOf(post: PostT): ViewImage[] {
  return post.blocks.flatMap((b) => b.kind === 'figure' ? [b.image] : b.kind === 'wide' ? b.images : [])
    .map(imageOf)
}

/** What viewer an attachment opens in: a PDF by pdf.js, a picture as the
 *  post's pictures, anything else by Mentis's existing viewer. */
export function viewableOf(i: ViewerItem, post: PostT): Viewable {
  const pdf = /pdf/i.test(i.mediaType) || /\.pdf$/i.test(i.name)
  if (pdf) return { kind: 'pdf', url: i.url, name: i.name, size: i.size }
  if (i.kind === 'image') {
    const all = picturesOf(post)
    const at = all.findIndex((x) => x.url === i.url)
    return at >= 0 ? { kind: 'gallery', images: all, start: at } : { kind: 'gallery', images: [{ url: i.url, name: i.name, alt: i.alt }], start: 0 }
  }
  return { kind: 'file', item: i }
}

/* -- a post's own pictures, as a collection --------------------------------
   AT MOST FOUR AT FIRST, then "+N more", which shows the rest and folds them
   away again; pictures not shown are not drawn, so not loaded. Four small
   arrangements of the same collection (Across, Grid, Focus, Mosaic); the
   selected picture stays selected whichever is chosen. Opening a picture
   opens the unified viewer on the post's pictures, starting at it. Pictures
   written inside the post's own words are Prose's, and not touched here. */
const ARRANGEMENTS: { id: GalleryLayout; label: string; d: ReactNode }[] = [
  { id: 'across', label: 'Across', d: <path d="M1.5 4.5h4v7h-4zM6.5 3.5h5v9h-5zM12.5 4.5h2v7h-2z" /> },
  { id: 'grid', label: 'Grid', d: <path d="M2 2h5v5H2zM9 2h5v5H9zM2 9h5v5H2zM9 9h5v5H9z" /> },
  { id: 'focus', label: 'Focus', d: <path d="M2 2h12v8H2zM2 12h3v2H2zM6.5 12h3v2h-3zM11 12h3v2h-3z" /> },
  { id: 'mosaic', label: 'Mosaic', d: <path d="M2 2h7v6H2zM10.5 2h3.5v3h-3.5zM10.5 6.5h3.5v7.5h-3.5zM2 9.5h3v4.5H2zM6.5 9.5H9v4.5H6.5z" /> },
]
const mosaicSpan = (r: number | undefined, i: number) => !r ? '' : r >= 1.65 ? ' wide' : r <= 0.72 ? ' tall' : i % 5 === 0 ? ' big' : ''

function Collection({ pictures, caption, onOpen }: { pictures: Picture[]; caption?: string; onOpen: (i: number) => void }) {
  /* first drawn as the reader last arranged a collection (prefs.ts); a
     change here is the reader's new default for collections drawn after it */
  const [layout, setLayoutNow] = useState<GalleryLayout>(() => readPrefs().collection)
  const setLayout = (l: GalleryLayout) => { setLayoutNow(l); savePrefs({ collection: l }) }
  const [selected, setSelected] = useState(0)
  const [expanded, setExpanded] = useState(false)
  const [ratios, setRatios] = useState<Record<number, number>>({})
  const n = pictures.length
  const more = n - SHOWN
  /* folded, the selected picture stays among those shown (in the last place) */
  const shown = expanded || more <= 0 ? pictures.map((p, i) => ({ p, i }))
    : selected >= SHOWN ? [...pictures.slice(0, SHOWN - 1).map((p, i) => ({ p, i })), { p: pictures[selected], i: selected }]
    : pictures.slice(0, SHOWN).map((p, i) => ({ p, i }))
  const learn = (i: number) => (e: React.SyntheticEvent<HTMLImageElement>) => {
    const im = e.currentTarget
    if (im.naturalWidth && im.naturalHeight && !ratios[i]) setRatios((r) => ({ ...r, [i]: im.naturalWidth / im.naturalHeight }))
  }
  const img = (p: Picture, i: number) => <img src={p.src} alt={p.alt} loading="lazy" decoding="async" draggable={false} onLoad={learn(i)} />
  /* in Focus a thumbnail chooses what is prominent; elsewhere a picture opens */
  const tile = ({ p, i }: { p: Picture; i: number }, cls = '') => (
    <button key={i} type="button" className={'q2c-tile' + cls} aria-current={i === selected ? 'true' : undefined}
      title={p.caption ?? p.alt} aria-label={layout === 'focus' ? `Show ${p.alt} (${i + 1} of ${n})` : `View ${p.alt} larger (${i + 1} of ${n})`}
      onClick={() => { setSelected(i); if (layout !== 'focus') onOpen(i) }}>{img(p, i)}</button>
  )
  const current = pictures[Math.min(selected, n - 1)]
  return (
    <figure className="q2-wide q2c" data-src-skip="" data-layout={layout} aria-label={`${n} pictures`}>
      {layout === 'focus' ? (
        <div className="q2c-focus">
          <button type="button" className="q2c-main" onClick={() => onOpen(selected)} aria-label={`View ${current.alt} larger (${selected + 1} of ${n})`} title={current.caption ?? current.alt}>
            <img key={current.src} src={current.src} alt={current.alt} decoding="async" draggable={false} />
          </button>
          <div className="q2c-strip">{shown.map((x) => tile(x))}</div>
        </div>
      ) : (
        <div className={`q2c-${layout}`} role="list">
          {shown.map((x) => <div key={x.i} role="listitem" className={'q2c-cell' + (layout === 'mosaic' ? mosaicSpan(ratios[x.i], x.i) : '')}
            style={layout === 'across' && ratios[x.i] ? { ['--r' as string]: String(ratios[x.i]) } : undefined}>{tile(x)}</div>)}
        </div>
      )}
      <div className="q2c-bar">
        <div className="q2c-seg" role="group" aria-label="Arrange these pictures">
          {ARRANGEMENTS.map((a) => (
            <button key={a.id} type="button" className="q2c-arr" aria-pressed={layout === a.id} title={a.label} aria-label={a.label} onClick={() => setLayout(a.id)}>
              <svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="1.3" strokeLinejoin="round">{a.d}</svg>
            </button>
          ))}
        </div>
        <span className="q2c-count">{n} pictures</span>
        {more > 0 && (
          <button type="button" className="q2c-more" aria-expanded={expanded} onClick={() => setExpanded(!expanded)}>
            {expanded ? 'Show fewer' : `+${more} more`}</button>
        )}
      </div>
      {caption && <figcaption>{caption}</figcaption>}
    </figure>
  )
}

/* -- a post's files: at most four at first, then "+N more" ----------------- */
function Attachments({ post, files }: { post: PostT; files: Attachment[] }) {
  const page = usePage()
  const [expanded, setExpanded] = useState(false)
  const more = files.length - SHOWN
  const shown = expanded || more <= 0 ? files : files.slice(0, SHOWN)
  const source: ViewerSource = { conversation: post.conversation, post: post.id }
  const itemOfFile = (a: Attachment): ViewerItem => a.item ?? { url: a.url ?? '', name: a.name, alt: a.name, kind: 'file', ref: '', mediaType: '', size: null }
  return (
    <section className="q2-attachments" aria-label={`${files.length} attachments`}>
      {shown.map((a, i) => (
        <span key={`${i}:${a.name}`} className="q2-file-row q2-openable">
          <button className="q2-file" title={`Open ${a.name}`} onClick={() => page.onView(viewableOf(itemOfFile(a), post), source)}>
            {Icon.file}<span className="q2-file-name">{a.name}</span><span className="q2-file-meta">{a.type}{a.size ? ` · ${a.size}` : ''}</span>
          </button>
          {a.item && <BesideButton label={`Open ${a.name} in the viewer`} onClick={() => page.onView(viewableOf(a.item!, post), source)} />}
        </span>
      ))}
      {more > 0 && (
        <button type="button" className="q2c-more q2c-files-more" aria-expanded={expanded} onClick={() => setExpanded(!expanded)}>
          {expanded ? 'Show fewer' : `+${more} more`}</button>
      )}
    </section>
  )
}

/* -- what the page lends every post ---------------------------------------
   Posts are drawn in several places (the flow, a thread, a working surface);
   what acting on one does is the page's, given once here. */
export interface PostPage {
  /** the participant the reader is, where known: whose posts they may edit */
  me: Id | null
  who: Person | null
  topic: string | null
  onWho: (p: Person) => void
  onTopic: (t: string) => void
  /** reply to this post in the composer that serves where it is shown */
  onReply: (p: PostT) => void
  /** read this post's thread in the reading column (at one post in it) */
  onEnter: (root: Id, at?: Id) => void
  /** show a thread, or one post, in a working surface; null: no surface */
  onBeside: ((v: SurfaceView) => void) | null
  /** view content (a picture, a file, a rendered block) in the viewer: in a
   *  free working column, or maximised where there is none */
  onView: (content: Viewable, source: ViewerSource) => void
  /** where this post, or the thread it roots, is open other than here,
   *  said briefly; null: nowhere */
  openElsewhere: (id: Id) => string | null
  say: (words: string) => void
  /** who is working now (presence.ts), for the marks beside posts */
  working: Working[]
}
/** What a working surface can hold. Each names its source; none is a copy. */
export type SurfaceView =
  | { kind: 'thread'; root: Id }
  | { kind: 'post'; id: Id }
  | { kind: 'conversation'; conversation: Id }
  | { kind: 'media'; item: ViewerItem; post: Id }
  | { kind: 'block'; post: Id; block: number; element: number; label: string }
  /** the epistemic records of one post, grouped by Kind (epistemic/Records.tsx) */
  | { kind: 'records'; post: Id; conversation: Id | null }
export const PageContext = createContext<PostPage | null>(null)
export const usePage = () => useContext(PageContext)!

/** The thread a post belongs to (its root), if it is in one: it has
 *  replies or answers another. Every thread-opening control uses this. */
export const threadOf = (post: PostT): Id | null => {
  const n = threadSize(post.id)
  return n > 0 || post.replyTo ? post.root ?? (post.replyTo ? post.replyTo : post.id) : null
}

/** Where a post can be read again: this interface's own address, the
 *  conversation read around the post's number. */
export const linkOf = (p: PostT) => p.real && p.conversation && p.number
  ? `${location.origin}${location.pathname}?c=${encodeURIComponent(p.conversation)}&at=${p.number}`
  : `${location.origin}${location.pathname}${location.search}#${p.id}`

/* -- the toolbar: Mentis's own acts on a post ------------------------------
   Reply with its count, Edit where the reader wrote it, Copy link, and the
   rest behind ⋯. The bookmark is a design candidate only: it does nothing. */
function Toolbar({ post, onEdit }: { post: PostT; onEdit: (() => void) | null }) {
  const page = usePage()
  const [menu, setMenu] = useState(false)
  const box = useRef<HTMLDivElement>(null)
  const n = threadSize(post.id)
  /* the thread this post is in, whole: from its root, whichever post is acted on */
  const root = post.root ?? (post.replyTo ? post.replyTo : post.id)
  const inThread = n > 0 || !!post.replyTo
  useEffect(() => {
    if (!menu) return
    const away = (e: PointerEvent) => { if (!box.current?.contains(e.target as Node)) setMenu(false) }
    const esc = (e: KeyboardEvent) => { if (e.key === 'Escape') setMenu(false) }
    document.addEventListener('pointerdown', away); document.addEventListener('keydown', esc)
    return () => { document.removeEventListener('pointerdown', away); document.removeEventListener('keydown', esc) }
  }, [menu])
  const copy = (words: string, said: string) => {
    void navigator.clipboard?.writeText(words).then(() => page.say(said), () => page.say('Could not reach the clipboard.'))
  }
  const act = (fn: () => void) => () => { setMenu(false); fn() }
  return (
    <div className="q2-toolbar" role="toolbar" aria-label="post actions" ref={box}>
      {/* THE BUBBLE AND ITS COUNT OPEN THE THREAD, as Read the thread does;
          a post with no replies offers Reply instead (where writing is on) */}
      {inThread
        ? <button onClick={() => page.onEnter(root, post.id)} title="Read the whole thread">{Icon.reply}<span>{n > 0 ? `${n} ${n === 1 ? 'reply' : 'replies'}` : 'Thread'}</span></button>
        : !READ_ONLY && <button onClick={() => page.onReply(post)} title="Reply to this post">{Icon.reply}<span>Reply</span></button>}
      {inThread && !READ_ONLY && <button onClick={() => page.onReply(post)} title="Reply to this post"><span>Reply</span></button>}
      {onEdit && !READ_ONLY && <button onClick={onEdit} title="Edit this post">{Icon.edit}<span>Edit</span></button>}
      <span className="q2-toolbar-gap" />
      <button className="q2-candidate" aria-disabled="true" title="Bookmark: a design candidate only; it does nothing yet" aria-label="Bookmark (design candidate, not functional)">{Icon.keep}</button>
      <button title="Copy link to this post" aria-label="Copy link" onClick={() => copy(linkOf(post), 'Link copied.')}>{Icon.link}</button>
      <button title="More" aria-label="More actions" aria-haspopup="menu" aria-expanded={menu} onClick={() => setMenu(!menu)}>{Icon.more}</button>
      {menu && (
        <div className="q2-menu" role="menu" aria-label="post actions">
          {inThread && <button role="menuitem" onClick={act(() => page.onEnter(root))}>Read the whole thread here</button>}
          {page.onBeside && inThread && <button role="menuitem" onClick={act(() => page.onBeside!({ kind: 'thread', root }))}>Open the thread in a working surface</button>}
          {page.onBeside && <button role="menuitem" onClick={act(() => page.onBeside!({ kind: 'post', id: post.id }))}>Open this post in a working surface</button>}
          <button role="menuitem" onClick={act(() => copy(post.text !== undefined ? repairText(post.text) : post.blocks.map((b) => b.kind === 'text' ? b.md : '').join('\n\n'), 'Words copied.'))}>Copy the words</button>
        </div>
      )}
    </div>
  )
}

/* -- who is working on this post: a presence mark in the margin -------------
   One face (or two, then "+n") with a soft pulse while the run is live, and
   the same said in words for assistive technology and reduced motion. A
   presence mark, not a control: details belong to the activity panel. */
function WorkMark({ work }: { work: Working[] }) {
  const names = work.map((w) => w.alias.replace(/^@/, ''))
  const said = `${names.join(' and ')} ${work.length === 1 ? 'is' : 'are'} working on this post`
  const doing = work.map((w) => w.doing).filter(Boolean).join('; ')
  return (
    <div className="q2-work-mark" title={[said, doing, work.some((w) => w.simulated) ? 'sample: simulated' : null].filter(Boolean).join(' · ')}>
      {work.slice(0, 2).map((w) => (
        <span key={w.key} className="q2-pulse"><Avatar id={w.participant} name={w.alias} size={22} runtime={w.runtime ?? undefined} /></span>
      ))}
      {work.length > 2 && <span className="q2-work-more">+{work.length - 2}</span>}
      <span className="q2-sr">{said}</span>
    </div>
  )
}

/* -- editing: Mentis's own post-edit command, by the post's author ---------- */
function Editor({ post, me, done }: { post: PostT; me: Id; done: () => void }) {
  const [text, setText] = useState(post.text ?? '')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const save = () => {
    setBusy(true); setErr(null)
    editPost(post.id, { by: me, text })
      .then(() => readThread(post.conversation!, post.root ?? post.id))
      .then(done, (e: unknown) => { setErr(String(e)); setBusy(false) })
  }
  return (
    <div className="q2-editor">
      <textarea value={text} onChange={(e) => setText(e.target.value)} rows={Math.min(18, Math.max(4, text.split('\n').length + 1))} aria-label="edit this post" />
      <div className="q2-editor-row">
        {err && <span className="q2-editor-err" role="alert">{err}</span>}
        <span className="q2-toolbar-gap" />
        <button className="q2-link" onClick={done} disabled={busy}>Cancel</button>
        <button className="q2-editor-save" onClick={save} disabled={busy || text.trim() === (post.text ?? '').trim()}>{busy ? 'Saving…' : 'Save edit'}</button>
      </div>
      <p className="q2-editor-note">The edit is recorded as a new version; the earlier one stays in the record.</p>
    </div>
  )
}

/* THE PASSAGE A POST IS ABOUT (an anchored reply: a comment, or a request
   sent to an agent from a selection): the words as the anchor reads them
   now (never a stored copy), and the way back to them. */
const anchorViews = new Map<string, Promise<{ excerpt: string | null; turn: string; conversation: string } | null>>()
function AnchoredOn({ anchor }: { anchor: Id }) {
  const page = usePage()
  const [v, setV] = useState<{ excerpt: string | null; turn: string; conversation: string } | null>(null)
  useEffect(() => {
    let live = true
    let p = anchorViews.get(anchor)
    if (!p) {
      p = fetch(`/api/anchors/${encodeURIComponent(anchor)}`, { headers: { 'X-Mentis-Client': '1' } })
        .then((r) => r.ok ? r.json() : null).then((j) => j && !j.error ? j : null).catch(() => null)
      anchorViews.set(anchor, p)
    }
    void p.then((x) => { if (live) setV(x) })
    return () => { live = false }
  }, [anchor])
  if (!v) return null
  const source = postOf(v.turn)
  return (
    <p className="q2-anchored">
      <span className="q2-anchored-mark" aria-hidden="true">❝</span>
      <span className="q2-anchored-words">{v.excerpt ? `“${v.excerpt}”` : 'a passage no longer shown'}</span>
      <button className="q2-link-quiet" onClick={() => page.onEnter(source?.root ?? v.turn, v.turn)}
        title="Go to the passage this is about">{source?.number ? `in #${source.number}` : 'go to the passage'}</button>
    </p>
  )
}

export default function Post({ post, replyingTo, selected, onSelect, inset = 0, threadMarks }: {
  post: PostT
  /** what this post answers, said in its "replying to" line */
  replyingTo?: { name: string; title?: string }
  /** in a thread: this is the reply chosen to work with */
  selected?: boolean
  onSelect?: () => void
  /** how far this post is indented from the reading column's edge (a reply
   *  in the tree), so its margin marks stand outside the column like any */
  inset?: number
  /** marks for work elsewhere in this post's thread (the flow's folded post) */
  threadMarks?: ReactNode
}) {
  const page = usePage()
  const link = useLink(post.id)
  const [editing, setEditing] = useState(false)
  const article = post.weight === 'article'
  const work = workingOn(page.working, post.id)
  /* ITS OPERATIONAL STATUS (status/): who it addressed and where each stands,
     a dog-ear at its corner and a line at its foot; the margin's pulsing
     faces still say who is working */
  const status = useStatus(post, work)
  /* only a post's author may edit it, and only a post of words alone */
  const mayEdit = !!(post.real && page.me && post.by.id === page.me && post.text !== undefined && !post.attachments?.length)
  return (
    <article className={`q2-post q2-${post.weight}` + (selected ? ' selected' : '') + (link.parentHot ? ' q2-parent-hot' : '')
      + (link.answering ? ' q2-answering' : '') + (link.replyHot ? ' q2-reply-hot' : '') + (status.status ? ' q2-st-on' : '')} id={post.id} data-post={post.id}
      onPointerEnter={post.replyTo ? () => pointAt(post.id, post.replyTo) : undefined}
      onPointerLeave={post.replyTo ? () => pointAt(null) : undefined}
      aria-label={post.title ?? `${post.by.name}, ${post.at}`} aria-current={selected || undefined}
      onClick={onSelect ? (e) => { if (!(e.target as Element).closest('button, a, textarea, input')) onSelect() } : undefined}>
      {link.answering && <p className="q2-answering-note">Replying to this post</p>}
      <DogEar s={status} post={post} />
      {post.anchor && <AnchoredOn anchor={post.anchor} />}
      {replyingTo && !article && <p className="q2-replying">replying to {replyingTo.name.replace(/^@/, '')}{replyingTo.title ? <> · <i>{replyingTo.title}</i></> : null}</p>}
      {post.topics?.length ? (
        <div className="q2-topics">
          {post.topics.map((t) => <button key={t} className={'q2-pill' + (t === page.topic ? ' on' : '')} onClick={() => page.onTopic(t)} aria-pressed={t === page.topic}>#{t}</button>)}
        </div>
      ) : null}
      {post.title && (article ? <h2 className="q2-title">{post.title}</h2> : <h3 className="q2-title-small">{post.title}</h3>)}
      <Byline post={post} onWho={page.onWho} filtered={page.who?.id === post.by.id} onThread={threadOf(post) ? () => page.onEnter(threadOf(post)!, post.id) : undefined}
        marks={work.length > 0 || threadMarks ? (
          /* IN THE MARGIN, LEVEL WITH THE BYLINE: outside the reading surface
             by a constant gap, whatever the post's indent; where there is no
             margin to stand in, at the end of the byline's own row */
          <div className="q2-margin-marks" style={{ ['--q2-inset' as string]: `${inset}px` }}>
            {work.length > 0 && <WorkMark work={work} />}
            {threadMarks}
          </div>
        ) : undefined} />
      {editing && page.me ? <Editor post={post} me={page.me} done={() => setEditing(false)} /> : (
        <div className="q2-body">
          {/* the post's annotations, in the right margin (annotate/Margin.tsx) */}
          {post.real && <Margin post={post} />}
          {post.blocks.map((b, i) => <BlockView key={i} b={b} scope={`q2:${post.id}:${i}`} post={post} index={i} />)}
        </div>
      )}
      {post.attachments?.length ? <Attachments post={post} files={post.attachments} /> : null}
      <StatusLine s={status} />
      <Toolbar post={post} onEdit={mayEdit && !editing ? () => setEditing(true) : null} />
    </article>
  )
}
