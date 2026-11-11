/* A POST'S EXISTING ANNOTATIONS, IN MARK 2 (Builder B, annotation round).
 *
 * WHAT IS SHOWN. An anchor that carries something now (a reaction, an
 * anchored comment, a deep dive: `carries`) is a small mark in the RIGHT
 * margin, outside the reading measure, level with its passage. Agent-activity
 * marks stand in the LEFT margin level with the byline (`.q2-margin-marks`),
 * so the two never meet. Its passage carries a faint lasting wash, stronger
 * while its mark is pointed at or its card is open. A card opens only on
 * request: one mark, one card.
 *
 * WHERE A MARK GOES. Measured, never matched by text: the passage is placed
 * in the rendered words by Fluid's alignment (`drawnRange` over
 * `surfaces/passage.ts`) against the post's stored words as its body draws
 * them (`sourceOfPost`, real.ts), and the mark is set level with the first
 * line of the range. A whole-post anchor (selector `version`) sits level with
 * the byline; one whose passage cannot be placed (an earlier version, a
 * deleted passage) sits at the top of the body, still reachable. Marks a
 * line apart are stacked apart, each carrying its count. The layer is the
 * body's first child with no height, positioned in the body's own
 * coordinates, so scrolling never moves a mark relative to its words; a
 * change of shape (width, columns, a picture arriving, the words redrawn)
 * measures again.
 *
 * WHERE THERE IS NO MARGIN (a narrow conversation, one of several columns)
 * the marks stand just past the words' right edge, inside the column's own
 * padding, and the card opens under its mark.
 *
 * A POST'S EPISTEMIC RECORDS stand in the same stack (epistemic/Records.tsx):
 * one mark for all of them, level with the byline and first in the stack
 * there, so a whole-post annotation steps below it; the card is this file's
 * card, holding the records instead. Margin material drawn by others in this
 * margin -- the "Replying to this post" note, the status dog-ear (status/),
 * a block's asides, anything marked `data-q2-margin-keep` -- is measured too
 * and stepped past where it stands in the marks' way.
 *
 * READ LIVE. `useAnchors` holds the post's anchors and reads them again when
 * the change feed names `anchors:<post>` or when anything here (or the
 * selection toolbar) calls `reread(post)`, so a new reaction or comment
 * appears without a reload.
 *
 * THE LAYER IS NOT THE POST'S WORDS: it carries `data-src-skip`, as every
 * other non-word element inside `.q2-body` does, so the alignment never
 * looks for its glyphs in the stored text. */
import { useCallback, useEffect, useId, useLayoutEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { ago } from '../../api'
import { Prose } from '../../prose'
import { highlightFor } from '../../surfaces/passage'
import { withdrawReaction, type PostAnchor } from '../../fluid/actions'
import { carries, commentsOldestFirst, drawnRange, inTextOrder, lead, reread, tallyWords, useAnchors } from '../../fluid/conversation/annotated'
import { usePost } from '../../fluid/conversation/hooks'
import { said } from '../../fluid/conversation/text'
import { useLayer } from '../../fluid/frame/layer'
import { store, type Id } from '../../fluid/store'
import { READ_ONLY } from '../live'
import { PageContext, placeAside, usePage, type AsidePlace } from '../Post'
import { nameOf, postOf, sourceOfPost } from '../real'
import type { Post as PostT } from '../sample'
import { refusalWords } from '../refusal'
import { repairText } from '../text'
import { markLabel, RECORDS_GLYPH, RecordsPanel } from '../epistemic/Records'
import { homeOf, usePostRecords } from '../epistemic/read'
import './margin.css'

/** A mark's height, for stacking two that would otherwise overlap. */
const MARK = 22
const APART = 4
const WANT = { beside: 300, below: 420 }

/** The records mark's key in the stack: never an anchor's id (`ent-…`). */
const RECORDS = 'records'
/** What else stands in this margin, measured so no mark sits over it. */
const KEEP = ':scope > .q2-answering-note, :scope > .q2-st-ear, .q2-aside-mark, [data-q2-margin-keep]'

const WASH = 'q2-anno'
const HERE = 'q2-anno-here'

const svg = (d: ReactNode) => (
  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{d}</svg>
)
const BUBBLE = svg(<path d="M4 5h16v11H9l-5 4V5Z" />)
const DIVE = svg(<><path d="M7 17 17 7" /><path d="M8 7h9v9" /></>)

/** The mark's glyph: the leading reaction, else a comment, else a deep dive. */
function glyphOf(a: PostAnchor): ReactNode {
  const top = [...a.reactions].sort((x, y) => y.count - x.count)[0]
  if (top) return <span className="q2m-emoji">{top.token}</span>
  return a.replies.length ? BUBBLE : DIVE
}

const onWords = (a: PostAnchor) => a.selector.type === 'version' ? 'the whole post' : `“${repairText(a.excerpt ?? '')}”`

/** The first drawn line of a range (a range may start on an empty line end). */
const firstLine = (r: Range) => Array.from(r.getClientRects()).find((x) => x.width > 0 && x.height > 0) ?? r.getClientRects()[0]

export default function Margin({ post }: { post: PostT }) {
  /* a margin is a measurement: there is nothing to measure without a layout */
  if (typeof document === 'undefined') return null
  return <Layer post={post} />
}

function Layer({ post }: { post: PostT }) {
  const anchors = useAnchors(post.id)
  const list = useMemo(() => inTextOrder(anchors.filter(carries)), [anchors])
  /* read from the post's home conversation, where its work was recorded */
  const home = homeOf(post.id, post.conversation)
  const { held } = usePostRecords(post.id, home)
  const recs = held?.length ?? 0
  /* re-adapted (an edit, a re-read) with the post: its words as drawn now */
  const src = useMemo(() => sourceOfPost(post.id), [post])
  /* the same post may be drawn twice (the flow and a working surface): each
     drawing marks its own ranges under the shared highlight */
  const owner = post.id + useId()
  const layer = useRef<HTMLDivElement>(null)
  const [tops, setTops] = useState<Record<string, { y: number; placed: boolean }>>({})
  const [open, setOpen] = useState<string | null>(null)
  const [hot, setHot] = useState<string | null>(null)
  const ranges = useRef(new Map<string, Range>())
  const active = useRef<string | null>(null)
  active.current = open ?? hot

  const paintActive = useCallback(() => {
    const r = active.current ? ranges.current.get(active.current) : undefined
    highlightFor(HERE, owner, r ? [r] : [])
  }, [owner])

  /* WHERE EACH MARK GOES, and the wash, measured together */
  const live = useRef({ list, src, recs })
  live.current = { list, src, recs }
  const measure = useCallback(() => {
    const el = layer.current
    const body = el?.parentElement
    if (!el || !body) return
    const { list, src, recs } = live.current
    const origin = el.getBoundingClientRect().top
    const art = body.closest('.q2-post')
    const byline = art?.querySelector(':scope > .q2-byline')?.getBoundingClientRect()
    const atByline = byline ? byline.top + byline.height / 2 - origin - MARK / 2 : 0
    const rs = new Map<string, Range>()
    /* the records first: the sort keeps it ahead of a whole-post annotation */
    const ys = [...(recs ? [{ id: RECORDS, y: atByline, placed: true }] : []), ...list.map((a) => {
      if (a.selector.type === 'version') {
        return { id: a.anchor, y: atByline, placed: !!byline }
      }
      const r = src ? drawnRange(a, body, src) : null
      const line = r ? firstLine(r) : undefined
      if (r && line) rs.set(a.anchor, r)
      return { id: a.anchor, y: line ? line.top + line.height / 2 - origin - MARK / 2 : 0, placed: !!line }
    })].sort((x, y) => x.y - y.y)
    /* "Replying to this post" stands in the same margin at the post's top,
       a block's asides beside their block: a mark that would sit over one
       goes just below it. Only what stands where the marks stand counts. */
    const marks = el.firstElementChild?.getBoundingClientRect()
    const blocked = !marks ? [] : Array.from(art?.querySelectorAll(KEEP) ?? [])
      .filter((k) => !el.contains(k))
      .map((k) => k.getBoundingClientRect())
      .filter((r) => r.height > 0 && r.right > marks.left && r.left < marks.left + 40)
      .map((r) => ({ top: r.top - origin, bottom: r.bottom - origin }))
      .sort((a, b) => a.top - b.top)
    const out: Record<string, { y: number; placed: boolean }> = {}
    let floor = -Infinity
    for (const m of ys) {
      let y = Math.max(m.y, floor)
      for (const b of blocked) if (y < b.bottom && y + MARK > b.top) y = b.bottom + APART
      out[m.id] = { y: Math.round(y), placed: m.placed }
      floor = y + MARK + APART
    }
    setTops((was) => (JSON.stringify(was) === JSON.stringify(out) ? was : out))
    ranges.current = rs
    highlightFor(WASH, owner, [...rs.values()])
    paintActive()
  }, [owner, paintActive])

  useLayoutEffect(() => {
    measure()
  }, [list, src, recs, measure])

  useEffect(() => {
    const el = layer.current
    const body = el?.parentElement
    if (!el || !body || (!list.length && !recs)) return
    let frame = 0
    const soon = () => { cancelAnimationFrame(frame); frame = requestAnimationFrame(measure) }
    /* a change of shape: the column's width, an arrangement, a picture */
    const ro = new ResizeObserver(soon)
    ro.observe(body)
    const art = body.closest('.q2-post')
    if (art) ro.observe(art)
    /* the words redrawn at the same size (their nodes replaced) */
    const mo = new MutationObserver((ms) => { if (ms.some((m) => !el.contains(m.target))) soon() })
    mo.observe(body, { childList: true, subtree: true, characterData: true })
    window.addEventListener('resize', soon)
    void document.fonts?.ready.then(soon)
    return () => {
      cancelAnimationFrame(frame); ro.disconnect(); mo.disconnect()
      window.removeEventListener('resize', soon)
    }
  }, [list, recs, measure])

  useEffect(() => () => { highlightFor(WASH, owner, []); highlightFor(HERE, owner, []) }, [owner])
  useEffect(() => { paintActive() }, [open, hot, paintActive])

  /* WHAT THE CARD WILL SHOW is asked for with the anchors, in one batch, so
     a card does not open on a loading line (`loadPosts` asks only for what
     Fluid's store does not hold) */
  const commentKey = list.flatMap((a) => a.replies).join(',')
  useEffect(() => {
    if (commentKey) void store.loadPosts(commentKey.split(',')).catch(() => {})
  }, [commentKey])

  /* an annotation that no longer carries anything closes its card */
  const shown = open ? list.find((a) => a.anchor === open) ?? null : null
  const recordsOpen = open === RECORDS && recs > 0
  useEffect(() => { if (open && !shown && !recordsOpen) setOpen(null) }, [open, shown, recordsOpen])

  const marks = useRef(new Map<string, HTMLButtonElement>())
  const close = useCallback(() => {
    const at = open
    setOpen(null)
    if (at) marks.current.get(at)?.focus({ preventScroll: true })
  }, [open])

  return (
    <div ref={layer} className="q2m" data-src-skip="">
      {(list.length > 0 || recs > 0) && (
        <div className="q2m-marks" role="group" aria-label="Margin marks on this post">
          {held && recs > 0 && (() => {
            const at = tops[RECORDS]
            const label = markLabel(held)
            return (
              <button key={RECORDS} type="button" ref={(b) => { if (b) marks.current.set(RECORDS, b); else marks.current.delete(RECORDS) }}
                className={'q2m-mark q2e-mark' + (open === RECORDS ? ' on' : '')}
                style={{ top: (at?.y ?? 0) + 'px', visibility: at ? undefined : 'hidden' }}
                aria-expanded={open === RECORDS} aria-haspopup="dialog" aria-label={label} title={label}
                onClick={() => setOpen(open === RECORDS ? null : RECORDS)}>
                <span className="q2m-glyph">{RECORDS_GLYPH}</span>
                <span className="q2m-n" aria-hidden="true">{recs}</span>
              </button>
            )
          })()}
          {list.map((a) => {
            const { n } = lead(a)
            const at = tops[a.anchor]
            const label = `Annotation on ${onWords(a)}: ${tallyWords(a)}` + (at && !at.placed && a.selector.type !== 'version' ? ' (its passage is not in this version)' : '')
            return (
              <button key={a.anchor} type="button" ref={(b) => { if (b) marks.current.set(a.anchor, b); else marks.current.delete(a.anchor) }}
                className={'q2m-mark' + (open === a.anchor ? ' on' : '') + (at && !at.placed ? ' lost' : '')} data-anchor={a.anchor}
                style={{ top: (at?.y ?? 0) + 'px', visibility: at ? undefined : 'hidden' }}
                aria-expanded={open === a.anchor} aria-label={label} title={label}
                onPointerEnter={() => setHot(a.anchor)} onPointerLeave={() => setHot((h) => (h === a.anchor ? null : h))}
                onFocus={() => setHot(a.anchor)} onBlur={() => setHot((h) => (h === a.anchor ? null : h))}
                onClick={() => setOpen(open === a.anchor ? null : a.anchor)}>
                <span className="q2m-glyph">{glyphOf(a)}</span>
                {n > 1 && <span className="q2m-n" aria-hidden="true">{n}</span>}
              </button>
            )
          })}
        </div>
      )}
      {shown && (
        <Card key={shown.anchor} id={'q2m-card-' + shown.anchor} label={`Annotation on ${shown.selector.type === 'version' ? 'the whole post' : 'a passage'}`}
          mark={() => marks.current.get(shown.anchor) ?? null} onClose={close}>
          <AnchorCard a={shown} post={post} onClose={close} />
        </Card>
      )}
      {recordsOpen && held && (
        <Card key={RECORDS} id={'q2m-card-records-' + post.id} label="Records from this post" mark={() => marks.current.get(RECORDS) ?? null} onClose={close}>
          <RecordsPanel post={post.id} conversation={home} held={held} onClose={close} />
        </Card>
      )}
    </div>
  )
}

/* -- the card ---------------------------------------------------------------
   Opened on its mark: in the margin beside it where the margin has room,
   else under (or over) it inside the column, never under the composer, and
   always inside the window; what cannot fit scrolls inside the card. Esc, a
   press outside or × closes it, and the reading position stays where it is
   (focus moves with `preventScroll`). Drawn in the page's layer. It holds
   an annotation or the post's records: what is in it is its children. */
function Card({ id, label, mark, onClose, children }: { id: string; label: string; mark: () => HTMLElement | null; onClose: () => void; children: ReactNode }) {
  /* the card is drawn in the page's layer after this renders: it is set up
     once its element is there */
  const [el, setEl] = useState<HTMLDivElement | null>(null)
  const card = useRef<HTMLDivElement | null>(null)
  card.current = el
  const [at, setAt] = useState<AsidePlace | null>(null)
  /* the latest of each, so the card is set up once per opening */
  const given = useRef({ mark, onClose })
  given.current = { mark, onClose }
  const place = useCallback(() => {
    const m = given.current.mark(), c = card.current
    const col = m?.closest('.q2-col') ?? m?.closest('.q2-conv') ?? m?.closest('.q2-surface')
    if (!m || !c || !col) return
    /* the composer docked at the column's foot is not covered */
    const dock = col.querySelector('.q2-dock')?.getBoundingClientRect()
    const vh = dock && dock.height > 0 && dock.top < window.innerHeight ? Math.max(200, dock.top - 6) : window.innerHeight
    const drawnW = c.getBoundingClientRect().width || 1
    const drawnH = c.scrollHeight
    const next = placeAside(m.getBoundingClientRect(), col.getBoundingClientRect(), (w) => drawnH * Math.max(1, drawnW / w), WANT, window.innerWidth, vh)
    setAt((was) => (was && JSON.stringify(was) === JSON.stringify(next) ? was : next))
  }, [])
  useLayoutEffect(() => {
    if (!el) return
    place()
    const away = (e: PointerEvent) => {
      const t = e.target as Node
      if (!card.current?.contains(t) && !given.current.mark()?.contains(t)) given.current.onClose()
    }
    const esc = (e: KeyboardEvent) => {
      if (e.key !== 'Escape' || e.defaultPrevented) return
      const at = document.activeElement
      /* only while the reader is at the card or its mark, never an Escape meant elsewhere */
      if (at && at !== document.body && !at.closest('.q2m-card, .q2m')) return
      e.preventDefault(); given.current.onClose()
    }
    const ro = new ResizeObserver(() => place())
    ro.observe(el)
    window.addEventListener('resize', place); window.addEventListener('scroll', place, true)
    document.addEventListener('pointerdown', away); document.addEventListener('keydown', esc)
    return () => {
      ro.disconnect()
      window.removeEventListener('resize', place); window.removeEventListener('scroll', place, true)
      document.removeEventListener('pointerdown', away); document.removeEventListener('keydown', esc)
    }
  }, [el, place])
  /* the keyboard goes into the card once it is placed (a hidden element
     cannot take it), without scrolling anything */
  const focused = useRef(false)
  useEffect(() => {
    if (!el || !at || focused.current) return
    /* the layer draws what this card committed a moment later */
    const f = requestAnimationFrame(() => {
      el.focus({ preventScroll: true })
      focused.current = document.activeElement === el
    })
    return () => cancelAnimationFrame(f)
  }, [el, at])
  /* drawn in the page's layer, the card keeps the context of the post it is
     on: "In thread" from a working column opens there, not in the main column */
  const page = usePage()
  useLayer(
    <PageContext.Provider value={page}><div ref={setEl} id={id} className={'q2m-card' + (at ? ` ${at.mode}` : '')} role="dialog" aria-label={label}
      tabIndex={-1} data-src-skip=""
      style={at ? { left: at.left, top: at.top, width: at.width, maxHeight: at.maxHeight } : { left: 0, top: 0, width: WANT.beside, visibility: 'hidden' }}>
      {children}
    </div></PageContext.Provider>,
  )
  return null
}

function AnchorCard({ a, post, onClose }: { a: PostAnchor; post: PostT; onClose: () => void }) {
  const [me, setMe] = useState<Id | null>(store.me)
  useEffect(() => { if (!me && !READ_ONLY) void store.loadMe().then(setMe).catch(() => {}) }, [me])
  const [err, setErr] = useState<string | null>(null)
  const [, read] = useState(0)
  const current = a.history.filter((r) => r.current)
  const comments = commentsOldestFirst(a.replies, (id) => store.posts.get(id)?.at)
  useEffect(() => {
    let live = true
    if (a.replies.length) void store.loadPosts(a.replies).then(() => { if (live) read((n) => n + 1) }).catch(() => {})
    return () => { live = false }
  }, [a.replies])
  const who = nameOf(a.by) ?? a.history.find((r) => r.by === a.by)?.by_alias ?? null
  const withdraw = async (reaction: Id) => {
    if (READ_ONLY || !me) return
    setErr(null)
    try { await withdrawReaction(reaction, { by: me }); reread(post.id) } catch (x) { setErr(refusalWords(x)) }
  }
  return (
    <>
      <div className="q2m-head">
        <span className="q2m-what">{a.selector.type === 'version' ? 'On the whole post' : 'On this passage'}</span>
        <button type="button" className="q2m-x" aria-label="Close" title="Close (Esc)" onClick={onClose}>×</button>
      </div>
      {a.deleted ? <p className="q2m-faint"><i>{a.excerpt_withheld ?? 'The annotated words were deleted.'}</i></p>
        : a.selector.type !== 'version' && <blockquote className="q2m-excerpt">{repairText(a.excerpt ?? '')}</blockquote>}
      {!a.deleted && !a.version_is_current && <p className="q2m-faint">On an earlier version of this post.</p>}
      <p className="q2m-meta">{who ? <>Marked by {who.replace(/^@/, '')} · </> : null}<time dateTime={new Date(a.at * 1000).toISOString()} title={new Date(a.at * 1000).toLocaleString()}>{ago(a.at)}</time></p>
      {current.length > 0 && (
        <ul className="q2m-reactions" aria-label="reactions">
          {current.map((r) => (
            <li key={r.reaction}>
              <span className="q2m-token">{r.token ?? '·'}</span>
              <span className="q2m-by">{r.by_alias.replace(/^@/, '')}</span>
              <time title={new Date(r.at * 1000).toLocaleString()}>{ago(r.at)}</time>
              {!READ_ONLY && me && r.by === me && (
                <button type="button" className="q2m-withdraw" title="Withdraw your reaction" onClick={() => void withdraw(r.reaction)}>Withdraw</button>
              )}
            </li>
          ))}
        </ul>
      )}
      {comments.length > 0 && (
        <ol className="q2m-comments" aria-label={`${comments.length} ${comments.length === 1 ? 'comment' : 'comments'}, oldest first`}>
          {comments.map((c) => <Comment key={c} id={c} post={post} onClose={onClose} />)}
        </ol>
      )}
      {a.deep_dives.length > 0 && (
        <ul className="q2m-dives" aria-label="deep dives">
          {a.deep_dives.map((c) => (
            <li key={c}>
              {/* Mark 2's own address for a conversation, never Fluid's */}
              <a href={`${location.pathname}?c=${encodeURIComponent(c)}`}
                onClick={(e) => { if (e.button === 0 && !e.metaKey && !e.ctrlKey && !e.shiftKey) { e.preventDefault(); window.dispatchEvent(new CustomEvent('q2:open-conversation', { detail: c })) } }}>{DIVE}<span>{repairText(store.conversations.get(c)?.name ?? 'Deep dive')}</span></a>
            </li>
          ))}
        </ul>
      )}
      {err && <p className="q2m-err" role="alert">{err}</p>}
    </>
  )
}

/** One anchored comment: its author, when, and its words. A comment is a
 *  post (a record-only reply): read through Fluid's store. */
function Comment({ id, post, onClose }: { id: Id; post: PostT; onClose: () => void }) {
  const page = usePage()
  const c = usePost(id)
  const words = c && !c.deleted ? said(c).words : null
  /* the thread the annotated post is in, at the comment where it is held */
  const root = post.root ?? post.replyTo ?? post.id
  return (
    <li className="q2m-comment">
      <div className="q2m-comment-head">
        <span className="q2m-by">{c ? c.author_name.replace(/^@/, '') : 'Loading…'}</span>
        {c && <time title={new Date(c.at * 1000).toLocaleString()}>{ago(c.at)}</time>}
        {post.conversation && (
          <button type="button" className="q2m-open" title="Read this in the thread" onClick={() => { onClose(); page.onEnter(root, postOf(id) ? id : post.id) }}>In thread</button>
        )}
      </div>
      {c?.deleted ? <p className="q2m-faint"><i>Deleted</i></p>
        : words ? <div className="q2m-words"><Prose src={repairText(words)} scope={`q2m:${id}`} /></div>
          : <p className="q2m-faint" role="status">Loading…</p>}
    </li>
  )
}
