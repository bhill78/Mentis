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
import { useEffect, useRef, useState, type ReactNode } from 'react'
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

function Asides({ asides, id }: { asides: Aside[]; id: string }) {
  const [open, setOpen] = useState<number | null>(null)
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (open === null) return
    const away = (e: PointerEvent) => { if (!ref.current?.contains(e.target as Node)) setOpen(null) }
    const esc = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpen(null) }
    document.addEventListener('pointerdown', away); document.addEventListener('keydown', esc)
    return () => { document.removeEventListener('pointerdown', away); document.removeEventListener('keydown', esc) }
  }, [open])
  return (
    <div className="q2-asides" ref={ref}>
      <div className="q2-aside-marks">
        {asides.map((a, i) => (
          <button key={i} className={`q2-aside-mark q2-aside-${a.kind}` + (open === i ? ' on' : '')}
            aria-expanded={open === i} aria-controls={`${id}-aside-${i}`} aria-label={asideLabel(a)} title={asideLabel(a)}
            onClick={() => setOpen(open === i ? null : i)}>{asideIcon(a)}</button>
        ))}
      </div>
      {open !== null && (
        <div className="q2-aside-card" id={`${id}-aside-${open}`} role="region" aria-label={asideLabel(asides[open])}>
          <AsideCard a={asides[open]} />
        </div>
      )}
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
  replyingTo?: PostT
}) {
  const article = post.weight === 'article'
  return (
    <article className={`q2-post q2-${post.weight}`} id={post.id} aria-label={post.title ?? `${post.by.name}, ${post.at}`}>
      {replyingTo && !article && <p className="q2-replying">replying to {replyingTo.by.name.replace(/^@/, '')}{replyingTo.title ? <> · <i>{replyingTo.title}</i></> : null}</p>}
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
            <button key={a.name} className="q2-file" title={`Open ${a.name}`}>
              {Icon.file}<span className="q2-file-name">{a.name}</span><span className="q2-file-meta">{a.type} · {a.size}</span>
            </button>
          ))}
        </section>
      ) : null}
      <Toolbar post={post} onReply={() => onReply(post)} />
    </article>
  )
}
