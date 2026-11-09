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
import { useCallback, useLayoutEffect, useRef, useState, type ReactNode } from 'react'
import { useLayer } from '../fluid/frame/layer'
import { Avatar } from '../fluid/identity/Who'
import { Prose } from '../prose'
import { openViewer } from '../quiet/media/MediaLayer'
import type { ViewerItem } from '../quiet/media/view'
import type { Aside, Block, Person, Picture, Post as PostT } from './sample'

const item = (p: Picture): ViewerItem => ({ url: p.src, name: p.caption ?? p.alt, alt: p.alt, kind: 'image', ref: '', mediaType: 'image/svg+xml', size: null })

const view = (pics: Picture[], i: number, e: React.MouseEvent<HTMLElement>) => openViewer(pics.map(item), i, e.currentTarget)

/* -- icons: one stroke, one size ------------------------------------------ */
const I = ({ d, size = 18 }: { d: ReactNode; size?: number }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{d}</svg>
)
export const Icon = {
  reply: <I d={<path d="M20 15a7 7 0 0 1-7 7H5l2.5-3A8 8 0 1 1 20 15Z" />} />,
  react: <I d={<><path d="M12 21s-7-4.3-7-10a4 4 0 0 1 7-2.6A4 4 0 0 1 19 11c0 5.7-7 10-7 10Z" /></>} />,
  annotate: <I d={<><path d="M4 20h4L19 9l-4-4L4 16v4Z" /><path d="m13.5 6.5 4 4" /></>} />,
  keep: <I d={<path d="M7 3h10v18l-5-4-5 4V3Z" />} />,
  link: <I d={<><path d="M10 14a4 4 0 0 0 5.6 0l3-3a4 4 0 0 0-5.6-5.6l-1 1" /><path d="M14 10a4 4 0 0 0-5.6 0l-3 3a4 4 0 0 0 5.6 5.6l1-1" /></>} />,
  more: <I d={<><circle cx="5" cy="12" r="1" /><circle cx="12" cy="12" r="1" /><circle cx="19" cy="12" r="1" /></>} />,
  note: <I size={14} d={<><path d="M4 5h16v11H9l-5 4V5Z" /></>} />,
  image: <I size={14} d={<><rect x="3" y="5" width="18" height="14" rx="2" /><circle cx="9" cy="10" r="1.5" /><path d="m21 16-5-5-9 8" /></>} />,
  form: <I size={14} d={<><rect x="4" y="3" width="16" height="18" rx="2" /><path d="M8 8h8M8 12h8M8 16h5" /></>} />,
  file: <I size={16} d={<><path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8l-5-5Z" /><path d="M14 3v5h5" /></>} />,
}

/* -- the byline ----------------------------------------------------------- */
function Byline({ post, onWho, filtered }: { post: PostT; onWho: (p: Person) => void; filtered: boolean }) {
  const big = post.weight === 'article'
  return (
    <div className={'q2-byline' + (big ? ' big' : '')}>
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
        <span className="q2-byline-meta"><time>{post.at}</time>{big && <> · {readMinutes(post)} min read</>}</span>
      </div>
    </div>
  )
}

const readMinutes = (p: PostT) => Math.max(1, Math.round(p.blocks.reduce((n, b) => n + (b.kind === 'text' ? b.md.split(/\s+/).length : 0), 0) / 220))

/* -- margin material ------------------------------------------------------ */
const asideIcon = (a: Aside) => a.kind === 'annotation' ? Icon.note : a.kind === 'media' ? Icon.image : Icon.form
const asideLabel = (a: Aside) => a.kind === 'annotation' ? `Annotation by ${a.by.name}` : a.kind === 'media' ? `Picture: ${a.image.alt}` : `Form: ${a.title}`

function AsideCard({ a }: { a: Aside }) {
  if (a.kind === 'annotation') return (
    <>
      <div className="q2-aside-head"><Avatar id={a.by.id} name={a.by.name} size={18} /> <b>{a.by.name.replace(/^@/, '')}</b> <span>{a.at}</span></div>
      <p>{a.text}</p>
    </>
  )
  if (a.kind === 'media') return (
    <figure>
      <button className="q2-pic" onClick={(e) => view([a.image], 0, e)} aria-label={`View ${a.image.alt} larger`}><img src={a.image.src} alt={a.image.alt} /></button>
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

function Asides({ asides, id }: { asides: Aside[]; id: string }) {
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
      <AsideCard a={asides[open]} />
    </div>
  ))
  return (
    <div className="q2-asides">
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

/* -- the body ------------------------------------------------------------- */
function BlockView({ b, scope }: { b: Block; scope: string }) {
  if (b.kind === 'wide') return (
    <figure className={'q2-wide' + (b.images.length > 1 ? ' gallery' : '')} style={{ ['--n' as string]: b.images.length }}>
      <div className="q2-wide-row">
        {b.images.map((p, i) => (
          <button key={i} className="q2-pic" onClick={(e) => view(b.images, i, e)} aria-label={`View ${p.alt} larger`}>
            <img src={p.src} alt={p.alt} />
          </button>
        ))}
      </div>
      {b.caption && <figcaption>{b.caption}</figcaption>}
    </figure>
  )
  return (
    <div className={'q2-block' + (b.asides?.length ? ' has-asides' : '')}>
      {b.kind === 'text'
        ? <div className="q2-prose"><Prose src={b.md} scope={scope} /></div>
        : (
          <figure className="q2-figure">
            <button className="q2-pic" onClick={(e) => view([b.image], 0, e)} aria-label={`View ${b.image.alt} larger`}><img src={b.image.src} alt={b.image.alt} /></button>
            {b.image.caption && <figcaption>{b.image.caption}</figcaption>}
          </figure>
        )}
      {b.asides?.length ? <Asides asides={b.asides} id={scope} /> : null}
    </div>
  )
}

/* -- the toolbar ---------------------------------------------------------- */
function Toolbar({ post, onReply }: { post: PostT; onReply: () => void }) {
  const [reacted, setReacted] = useState(false)
  const [kept, setKept] = useState(false)
  const n = (post.reactions ?? 0) + (reacted ? 1 : 0)
  return (
    <div className="q2-toolbar" role="toolbar" aria-label="post actions">
      <button onClick={() => setReacted(!reacted)} aria-pressed={reacted} title="React">{Icon.react}{n > 0 && <span>{n}</span>}</button>
      <button onClick={onReply} title="Reply">{Icon.reply}{post.replies ? <span>{post.replies}</span> : null}</button>
      <span className="q2-toolbar-gap" />
      <button title="Annotate" aria-label="Annotate">{Icon.annotate}</button>
      <button onClick={() => setKept(!kept)} aria-pressed={kept} title={kept ? 'Kept' : 'Keep'} aria-label="Keep">{Icon.keep}</button>
      <button title="Copy link" aria-label="Copy link">{Icon.link}</button>
      <button title="More" aria-label="More">{Icon.more}</button>
    </div>
  )
}

export default function Post({ post, onWho, onTopic, onReply, who, topic, replyingTo }: {
  post: PostT
  onWho: (p: Person) => void
  onTopic: (t: string) => void
  onReply: (p: PostT) => void
  who: Person | null
  topic: string | null
  /** what this post answers, said in its "replying to" line */
  replyingTo?: { name: string; title?: string }
}) {
  const article = post.weight === 'article'
  return (
    <article className={`q2-post q2-${post.weight}`} id={post.id} aria-label={post.title ?? `${post.by.name}, ${post.at}`}>
      {replyingTo && !article && <p className="q2-replying">replying to {replyingTo.name.replace(/^@/, '')}{replyingTo.title ? <> · <i>{replyingTo.title}</i></> : null}</p>}
      {post.topics?.length ? (
        <div className="q2-topics">
          {post.topics.map((t) => <button key={t} className={'q2-pill' + (t === topic ? ' on' : '')} onClick={() => onTopic(t)} aria-pressed={t === topic}>#{t}</button>)}
        </div>
      ) : null}
      {post.title && (article ? <h2 className="q2-title">{post.title}</h2> : <h3 className="q2-title-small">{post.title}</h3>)}
      <Byline post={post} onWho={onWho} filtered={who?.id === post.by.id} />
      <div className="q2-body">
        {post.blocks.map((b, i) => <BlockView key={i} b={b} scope={`q2:${post.id}:${i}`} />)}
      </div>
      {post.attachments?.length ? (
        <section className="q2-attachments" aria-label={`${post.attachments.length} attachments`}>
          {post.attachments.map((a) => (
            <button key={a.name} className="q2-file" title={`Open ${a.name}`}
              onClick={(e) => { if (a.url) openViewer([{ url: a.url, name: a.name, alt: a.name, kind: 'file', ref: '', mediaType: '', size: null }], 0, e.currentTarget) }}>
              {Icon.file}<span className="q2-file-name">{a.name}</span><span className="q2-file-meta">{a.type} · {a.size}</span>
            </button>
          ))}
        </section>
      ) : null}
      <Toolbar post={post} onReply={() => onReply(post)} />
    </article>
  )
}
