/* THE SELECTION'S TOOLBAR (annotation round, Builder A).
 *
 * Words selected in a post's body (`[data-post] .q2-body`, wherever the post
 * is drawn: the conversation, a working column, an entered thread, a reply)
 * bring a small floating bar beside them. Three icons, each with a tooltip
 * and an accessible name: Comment (an anchored, record-only reply, written in
 * CommentEditor, saved or sent to an agent), Capture (save for later, add to
 * a composer, send to an agent: SendToAgent.tsx) and Deep dive (a
 * conversation opened from the words). Reactions are not offered here: they
 * are attributed marks with no effect, and the ones already made still show
 * in the margin (Margin.tsx). Every act is one of Fluid's commands
 * (fluid/actions.ts), so the anchors read again and the margin redraws.
 *
 * The bar is above the selection's first line, else below its last line,
 * inside the window and the column the words are in, never over the words
 * nor over a post's header (byline, time, thread link, title, topics, the
 * "replying to" line) or the page's own bars (placeBar). The keyboard: with
 * words selected, Tab moves into the bar; arrows move along it; Escape
 * closes it and gives the keyboard back.
 *
 * On a read-only page nothing here is drawn: every button writes. */
import { useEffect, useLayoutEffect, useRef, useState, type JSX, type ReactNode } from 'react'
import { deepDive } from '../../fluid/actions'
import { reread, passageOf, sourceOf, type Source } from '../../fluid/conversation/annotated'
import { useLayer } from '../../fluid/frame/layer'
import { newOp, store, type Post as FluidPost } from '../../fluid/store'
import { highlightFor } from '../../surfaces/passage'
import { READ_ONLY } from '../live'
import { postOf, readThread, sourceOfPost } from '../real'
import { refusalWords } from '../refusal'
import CommentEditor from './CommentEditor'
import SendToAgent from './SendToAgent'
import { addToComposer, savePassage, targetComposer } from './passage'
import type { Box, Selected } from './types'
import './selection.css'

const EDGE = 8
const GAP = 8

/* -- icons: one stroke, one size, as Post.tsx draws them -------------------- */
const I = ({ d }: { d: ReactNode }) => (
  <svg width={17} height={17} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{d}</svg>
)
const ICON = {
  comment: <I d={<path d="M4 5h16v11H9l-5 4V5Z" />} />,
  dive: <I d={<><circle cx="11" cy="11" r="6" /><path d="m20 20-4.5-4.5" /><path d="M11 8v6M8 11h6" /></>} />,
  send: <I d={<><path d="M21 3 10 14" /><path d="M21 3l-7 18-4-7-7-4 18-7Z" /></>} />,
  capture: <I d={<><path d="M7 4h10v16l-5-3.6L7 20V4Z" /><path d="M10 9.5h4" /></>} />,
  save: <I d={<><path d="M7 4h10v16l-5-3.6L7 20V4Z" /></>} />,
  add: <I d={<><path d="M5 5h14v10H10l-5 4V5Z" /><path d="M12 8v4M10 10h4" /></>} />,
}

/* -- the selection, said as Mentis says a passage --------------------------- */

const boxOf = (r: DOMRect | Box): Box => ({ left: r.left, top: r.top, right: r.right, bottom: r.bottom })

/** The column the words are in, as it is visible in the window. */
function boundsOf(el: Element): Box {
  const col = el.closest('.q2-pane, .q2v') ?? el.closest('.q2-col, .q2-conv') ?? document.documentElement
  const b = col.getBoundingClientRect()
  const vw = document.documentElement.clientWidth, vh = window.innerHeight
  return { left: Math.max(b.left, 0), top: Math.max(b.top, 0), right: Math.min(b.right, vw), bottom: Math.min(b.bottom, vh) }
}

/** What the post's body draws, offset for offset: Mark 2 shows a post that
 *  opens with a `#`/`##` heading with that heading as its title, outside the
 *  body, so the heading is blanked like any block the body does not draw. */
function drawnBy(src: Source, titled: boolean): Source {
  if (!titled) return src
  const lead = /^\s*/.exec(src.drawn)![0].length
  const head = /^#{1,2} +.+\n/.exec(src.drawn.slice(lead))
  if (!head) return src
  const n = head[0].length - 1
  return { ...src, drawn: src.drawn.slice(0, lead) + ' '.repeat(n) + src.drawn.slice(lead + n) }
}

/** The post body a range is wholly inside, and its post's element. */
function bodyOf(range: Range): { article: HTMLElement; body: HTMLElement } | null {
  const at = (n: Node) => (n.nodeType === Node.ELEMENT_NODE ? (n as Element) : n.parentElement)
  const body = at(range.commonAncestorContainer)?.closest<HTMLElement>('.q2-body')
  const article = body?.closest<HTMLElement>('[data-post]')
  if (!body || !article || body.parentElement !== article) return null
  if (!body.contains(range.startContainer) || !body.contains(range.endContainer)) return null
  return { article, body }
}

type Read = { sel: Selected; range: Range } | { refused: string; range: Range }

/** The selection now, as `Selected`, or why it cannot be one; null where
 *  nothing of a post's words is selected. */
async function readSelection(): Promise<Read | null> {
  const s = window.getSelection()
  if (!s || s.rangeCount === 0 || s.isCollapsed) return null
  const range = s.getRangeAt(0).cloneRange()
  const where = bodyOf(range)
  if (!where) return null
  const id = where.article.dataset.post!
  const shown = postOf(id)
  /* a sample post is not in the Brain: there is nothing to annotate */
  if (!shown?.real) return null
  if (!store.posts.has(id)) {
    try { await store.loadPosts([id]) } catch { return { refused: 'this post could not be read just now', range } }
  }
  let post: FluidPost | undefined = store.posts.get(id)
  if (!post) return { refused: 'this post could not be read just now', range }
  /* the version named and the words placed must be the same read: where the
     page shows other words than the held post (an edit since), read it again */
  const shownSrc = sourceOfPost(id)
  if (shownSrc && sourceOf(post).text !== shownSrc.text) {
    try { await store.loadPosts([id], true) } catch { /* refused below if still apart */ }
    post = store.posts.get(id)
    if (!post || sourceOf(post).text !== shownSrc.text) return { refused: 'this post changed since it was shown: read it again to select from it', range }
  }
  if (post.deleted) return null
  /* the same stored words the margin places passages against (real.ts) */
  const got = passageOf(range, where.body, sourceOfPost(id) ?? drawnBy(sourceOf(post), !!shown.title))
  if ('refused' in got) return { refused: got.refused, range }
  return {
    range,
    sel: {
      post: id,
      conversation: shown.conversation ?? post.home ?? '',
      version: post.version,
      passage: got.ok,
      excerpt: got.ok.expected_excerpt,
      box: boxOf(range.getBoundingClientRect()),
      bounds: boundsOf(where.article),
    },
  }
}

/* -- placing what opens ------------------------------------------------------ */

/** Above the words (below where there is no room), inside the column and the
 *  window, never over the words. `w`, `h`: the thing placed. */
export function placeNear(words: Box, bounds: Box, w: number, h: number, vw: number, vh: number): { left: number; top: number; below: boolean } {
  const lo = Math.max(bounds.left, EDGE), hi = Math.min(bounds.right, vw - EDGE)
  const mid = (words.left + words.right) / 2
  const left = Math.max(lo, Math.min(hi - w, mid - w / 2))
  const top0 = Math.max(bounds.top, EDGE), bottom0 = Math.min(bounds.bottom, vh - EDGE)
  const above = words.top - GAP - h
  if (above >= top0) return { left, top: above, below: false }
  const below = words.bottom + GAP
  if (below + h <= bottom0) return { left, top: below, below: true }
  /* neither side holds it inside the column: the side with more window */
  return words.top - h - GAP >= EDGE
    ? { left, top: above, below: false }
    : { left, top: Math.min(below, vh - EDGE - h), below: true }
}

/* What the bar must never cover: a post's header (the byline with its time
   and thread link, the title, the topics, the "replying to" and "about these
   words" lines) and the page's own bars. */
const POST_HEADS = '.q2-byline, .q2-thread-link, .q2-title, .q2-title-small, .q2-topics, .q2-replying, .q2-anchored'
const PAGE_HEADS = '.q2-top, .q2-conv-head, .q2-back-bar'

const meets = (a: Box, b: Box) => a.left < b.right && b.left < a.right && a.top < b.bottom && b.top < a.bottom

/** The headers drawn between `top` and `bottom` (viewport pixels) in the
 *  column the words are in, and the page's bars. */
function headsNear(from: Element, top: number, bottom: number): Box[] {
  const scope = from.closest('.q2-pane, .q2v') ?? from.closest('.q2-col, .q2-conv') ?? document
  const out: Box[] = []
  const take = (el: Element) => {
    const r = el.getBoundingClientRect()
    if (r.width > 0 && r.height > 0 && r.bottom > top && r.top < bottom) out.push(boxOf(r))
  }
  scope.querySelectorAll(POST_HEADS).forEach(take)
  document.querySelectorAll(PAGE_HEADS).forEach(take)
  return out
}

/** Where the bar goes: above the selection's first line, else below its last
 *  line; a side that would cover a header or the words is passed over, and
 *  only when both are blocked is a side tried again just past what blocks
 *  it; inside the column
 *  and the window. `words` is the whole selection, `first`/`last` its first
 *  and last lines; `avoid` what must stay visible; `w`, `h` the bar. */
export function placeBar(words: Box, first: Box, last: Box, bounds: Box, avoid: Box[], w: number, h: number, vw: number, vh: number): { left: number; top: number; below: boolean } {
  const lo = Math.max(bounds.left, EDGE), hi = Math.min(bounds.right, vw - EDGE)
  const xAt = (line: Box) => {
    const mid = (line.left + line.right) / 2
    /* inside the column where it fits; always inside the window */
    const l = Math.max(lo, Math.min(hi - w, mid - w / 2))
    return Math.max(EDGE, Math.min(vw - EDGE - w, l))
  }
  const top0 = Math.max(bounds.top, EDGE), bottom0 = Math.min(bounds.bottom, vh - EDGE)
  const blocks = [words, ...avoid]
  const hits = (b: Box) => blocks.filter((a) => meets(a, b))
  /* first right beside the words, above then below; only then a step or
     a few past whatever is in the way, never back toward the words */
  for (const steps of [1, 6]) for (const below of [false, true]) {
    let top = below ? words.bottom + GAP : words.top - GAP - h
    const left = xAt(below ? last : first)
    for (let i = 0; i < steps; i++) {
      if (top < top0 || top + h > bottom0) break
      const hit = hits({ left, top, right: left + w, bottom: top + h })
      if (!hit.length) return { left, top, below }
      top = below ? Math.max(...hit.map((a) => a.bottom)) + GAP / 2 : Math.min(...hit.map((a) => a.top)) - GAP / 2 - h
    }
  }
  /* nowhere clean: the side with more room, inside the window, off the words */
  const roomAbove = words.top - top0, roomBelow = bottom0 - words.bottom
  const inside = (t: number) => Math.max(top0, Math.min(bottom0 - h, t))
  if (roomAbove >= h + GAP) return { left: xAt(first), top: inside(words.top - GAP - h), below: false }
  if (roomBelow >= h + GAP) return { left: xAt(last), top: inside(words.bottom + GAP), below: true }
  /* the words fill the column: the bar waits at the column's foot, over the words but under nothing else */
  return { left: xAt(last), top: inside(bottom0 - h), below: true }
}

/** Places a bar `el` beside the live selection `range`. */
function placeFor(range: Range, el: HTMLElement): { left: number; top: number; below: boolean } | null {
  const r = range.getBoundingClientRect()
  if (r.width === 0 && r.height === 0) return null
  const lines = Array.from(range.getClientRects()).filter((x) => x.width > 0 && x.height > 0)
  const first = boxOf(lines[0] ?? r), last = boxOf(lines[lines.length - 1] ?? r)
  const from = range.startContainer.parentElement ?? document.body
  const w = el.offsetWidth, h = el.offsetHeight
  const vw = document.documentElement.clientWidth, vh = window.innerHeight
  const avoid = headsNear(from, r.top - 2 * h - 4 * GAP, r.bottom + 2 * h + 4 * GAP)
  return placeBar(boxOf(r), first, last, boundsOf(from), avoid, w, h, vw, vh)
}

/** Keeps a bar placed as the page scrolls and resizes, and as the bar itself
 *  changes size (a menu opening or closing, an error said). */
function usePlaced(range: Range, barRef: React.MutableRefObject<HTMLDivElement | null>, deps: unknown[]) {
  const [pos, setPos] = useState<{ left: number; top: number; below: boolean } | null>(null)
  useLayoutEffect(() => {
    const place = () => {
      const el = barRef.current
      if (!el) return
      const at = placeFor(range, el)
      if (!at) return
      setPos((p) => (p && p.left === at.left && p.top === at.top && p.below === at.below ? p : at))
    }
    place()
    let frame = 0
    const soon = () => { cancelAnimationFrame(frame); frame = requestAnimationFrame(place) }
    window.addEventListener('scroll', soon, true)
    window.addEventListener('resize', soon)
    const watch = typeof ResizeObserver === 'function' && barRef.current ? new ResizeObserver(soon) : null
    if (watch && barRef.current) watch.observe(barRef.current)
    return () => {
      cancelAnimationFrame(frame)
      window.removeEventListener('scroll', soon, true)
      window.removeEventListener('resize', soon)
      watch?.disconnect()
    }
  }, [range, barRef, ...deps])
  return pos
}

/* -- the bar ----------------------------------------------------------------- */

type Mode = 'bar' | 'comment' | 'dive' | 'send'

function Bar({ sel, range, onMode, onDone, onClose, barRef }: {
  sel: Selected
  range: Range
  onMode: (m: Mode) => void
  onDone: (said: string) => void
  onClose: () => void
  barRef: React.MutableRefObject<HTMLDivElement | null>
}) {
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  /* the capture choices, opened from the bar */
  const [open, setOpen] = useState<null | 'capture'>(null)
  /* a new selection starts with its menus closed */
  useEffect(() => { setOpen(null) }, [sel.post, sel.passage.start, sel.passage.end])
  /* an opened menu takes the keyboard to its first choice */
  useEffect(() => {
    if (!open) return
    barRef.current?.querySelector<HTMLButtonElement>('.q2s-menu button:not(:disabled)')?.focus({ preventScroll: true })
  }, [open, barRef])
  const target = open === 'capture' ? targetComposer() : null
  const act = async (fn: () => Promise<string>) => {
    if (busy) return
    setErr(null); setBusy(true)
    try { onDone(await fn()) } catch (x) { setErr(refusalWords(x)) } finally { setBusy(false) }
  }

  /* placed again whenever the bar changes size: a menu, an error */
  const pos = usePlaced(range, barRef, [err, open])

  /* arrows move along the bar, as along a toolbar */
  const keys = (e: React.KeyboardEvent) => {
    if (e.key === 'Escape' && open) {
      e.preventDefault(); e.stopPropagation()
      const was = open
      setOpen(null)
      barRef.current?.querySelector<HTMLButtonElement>(`[data-q2s="${was}"]`)?.focus()
      return
    }
    /* inside a menu, up and down (and left and right) move among its choices only */
    const menu = (document.activeElement as HTMLElement | null)?.closest('.q2s-menu')
    if (menu && ['ArrowDown', 'ArrowUp', 'ArrowLeft', 'ArrowRight'].includes(e.key)) {
      const items = Array.from(menu.querySelectorAll<HTMLButtonElement>('button:not(:disabled)'))
      const i = items.indexOf(document.activeElement as HTMLButtonElement)
      const step = e.key === 'ArrowDown' || e.key === 'ArrowRight' ? 1 : -1
      e.preventDefault()
      items[(i + step + items.length) % items.length]?.focus()
      return
    }
    const all = Array.from(barRef.current?.querySelectorAll<HTMLButtonElement>('.q2s-row button:not(:disabled)') ?? [])
    const i = all.indexOf(document.activeElement as HTMLButtonElement)
    if (i < 0) return
    const to = e.key === 'ArrowRight' ? (i + 1) % all.length : e.key === 'ArrowLeft' ? (i + all.length - 1) % all.length
      : e.key === 'Home' ? 0 : e.key === 'End' ? all.length - 1 : -1
    if (to < 0) return
    e.preventDefault()
    all[to].focus()
  }
  /* a press must not take the selection away */
  const hold = (e: React.MouseEvent) => e.preventDefault()

  return (
    <div ref={barRef} className="q2s-bar" role="toolbar" aria-label="Act on the selected words" data-q2s-bar={sel.post}
      data-side={pos?.below ? 'below' : 'above'} aria-orientation="horizontal"
      onKeyDown={keys} style={pos ? { left: pos.left, top: pos.top } : { left: 0, top: 0, visibility: 'hidden' }}>
      <div className="q2s-row">
        <button type="button" className="q2s-btn" data-q2s="comment" onMouseDown={hold}
          aria-label="Comment on these words" title="Comment: write about these words, then save it or send it to an agent"
          onClick={() => onMode('comment')}>{ICON.comment}</button>
        <button type="button" className="q2s-btn" data-q2s="capture" onMouseDown={hold}
          aria-haspopup="menu" aria-expanded={open === 'capture'}
          aria-label="Capture these words" title="Capture: save for later, add to a composer, or send to an agent"
          onClick={() => setOpen(open === 'capture' ? null : 'capture')}>{ICON.capture}</button>
        <button type="button" className="q2s-btn" data-q2s="dive" onMouseDown={hold}
          aria-label="Deep dive from these words" title="Deep dive: open a new conversation from these words (no agent is asked)"
          onClick={() => onMode('dive')}>{ICON.dive}</button>
      </div>
      {open === 'capture' && (
        <div className="q2s-menu q2s-capture" role="menu" aria-label="Capture these words">
          <button type="button" role="menuitem" className="q2s-item" data-capture="save" disabled={busy} onMouseDown={hold}
            title="Keep the exact words and where they are, to come back to (nothing is asked of anyone)"
            onClick={() => void act(async () => { await savePassage(sel); return 'Saved for later' })}>
            {ICON.save}<span>Save for later</span></button>
          <button type="button" role="menuitem" className="q2s-item" data-capture="add" disabled={busy || !target} onMouseDown={hold}
            title={target ? `Quote these words, with a reference to their post, in ${target.label}; nothing is sent` : 'No composer is open on this page'}
            onClick={() => void act(async () => `Added to ${await addToComposer(sel)}`)}>
            {ICON.add}<span>Add to composer{target ? <small> · {target.label}</small> : null}</span></button>
          <button type="button" role="menuitem" className="q2s-item" data-capture="send" onMouseDown={hold}
            title="Write an instruction and send it with these words to an agent"
            onClick={() => onMode('send')}>{ICON.send}<span>Send to agent</span></button>
        </div>
      )}
      {err && <div className="q2s-err" role="alert">{err}<button type="button" className="q2s-x" aria-label="Close" title="Close" onClick={onClose}>×</button></div>}
    </div>
  )
}

/* -- the whole: one per page --------------------------------------------------- */

/** The floating toolbar over a selection in any post's words; mounted once. */
export default function SelectionToolbar(): JSX.Element | null {
  const [now, setNow] = useState<Read | null>(null)
  const [mode, setMode] = useState<Mode>('bar')
  /* words written in the comment editor, carried to Send to Agent and back */
  const [carried, setCarried] = useState('')
  const [fromComment, setFromComment] = useState(false)
  /* set by a send, read by the close that follows it in the same tick */
  const sentRef = useRef(false)
  const [said, setSaid] = useState<{ text: string; at: { left: number; top: number } } | null>(null)
  const bar = useRef<HTMLDivElement | null>(null)
  const panel = useRef<HTMLElement | null>(null)
  /* where the keyboard was before it came into the bar */
  const back = useRef<HTMLElement | null>(null)
  const live = useRef({ mode, now })
  live.current = { mode, now }
  const readOnly = READ_ONLY

  const close = (collapse = true) => {
    setNow(null)
    setMode('bar')
    const b = back.current
    back.current = null
    if (collapse) {
      const s = window.getSelection()
      if (s && s.rangeCount && !s.isCollapsed) s.collapseToEnd()
    }
    if (b?.isConnected) b.focus({ preventScroll: true })
  }
  const closer = useRef(close)
  closer.current = close

  /* READ WHEN THE SELECTION SETTLES: after the pointer is up, or a moment
     after the keyboard stops; not while something opened has the focus */
  useEffect(() => {
    if (readOnly) return
    let timer = 0
    let seq = 0
    let pointer = false
    const inside = (n: Node | null) => !!n && (!!bar.current?.contains(n) || !!panel.current?.contains(n))
    const read = async () => {
      if (live.current.mode !== 'bar' || inside(document.activeElement)) return
      const mine = ++seq
      const got = await readSelection()
      if (mine !== seq || live.current.mode !== 'bar') return
      setNow(got)
    }
    const settle = () => {
      window.clearTimeout(timer)
      if (pointer) return
      timer = window.setTimeout(() => void read(), 120)
    }
    const down = (e: PointerEvent) => {
      if (inside(e.target as Node)) return
      /* anything opened is left by pointing elsewhere, unless words are written in it */
      const { mode } = live.current
      if (mode === 'send') return
      if (mode !== 'bar' && panel.current?.querySelector<HTMLTextAreaElement>('textarea')?.value.trim()) return
      pointer = true
      if (mode !== 'bar') closer.current(false)
    }
    const up = (e: PointerEvent) => {
      if (!pointer) return
      pointer = false
      if (!inside(e.target as Node)) settle()
    }
    document.addEventListener('selectionchange', settle)
    document.addEventListener('pointerdown', down, true)
    document.addEventListener('pointerup', up, true)
    return () => {
      window.clearTimeout(timer)
      document.removeEventListener('selectionchange', settle)
      document.removeEventListener('pointerdown', down, true)
      document.removeEventListener('pointerup', up, true)
    }
  }, [readOnly])

  /* TAB INTO THE BAR while words are selected; ESCAPE out of it */
  useEffect(() => {
    if (!now || mode !== 'bar') return
    const key = (e: KeyboardEvent) => {
      const inBar = !!bar.current?.contains(document.activeElement)
      if (e.key === 'Escape') {
        /* the bar's Escape only: not one meant for the dock, a viewer or a composer menu */
        const at = document.activeElement
        if (e.defaultPrevented || (at && at !== document.body && !at.closest('.q2s-bar, .q2-body'))) return
        /* a menu open in the bar closes first, by the bar's own key handling */
        if (bar.current?.querySelector('.q2s-menu')) return
        e.preventDefault(); e.stopPropagation(); closer.current(); return
      }
      if (e.key === 'Tab' && !e.shiftKey && !inBar) {
        const first = bar.current?.querySelector<HTMLButtonElement>('button:not(:disabled)')
        if (first) {
          e.preventDefault()
          const a = document.activeElement as HTMLElement | null
          back.current = a && a !== document.body ? a : null
          first.focus()
        }
      }
    }
    document.addEventListener('keydown', key, true)
    return () => document.removeEventListener('keydown', key, true)
  }, [now, mode])

  /* the passage stays marked while something opened from it has the focus */
  const sel = now && 'sel' in now ? now.sel : null
  useEffect(() => {
    if (!now || mode === 'bar') return
    highlightFor('q2-sel', 'q2s', [now.range])
    return () => highlightFor('q2-sel', 'q2s', [])
  }, [now, mode])

  /* a short word on what was done, where the bar was, then nothing */
  useEffect(() => {
    if (!said) return
    const t = window.setTimeout(() => setSaid(null), 1600)
    return () => window.clearTimeout(t)
  }, [said])

  const done = (text: string) => {
    const r = bar.current?.getBoundingClientRect() ?? panel.current?.getBoundingClientRect()
    if (now) {
      highlightFor('q2-flash', 'q2s', [now.range])
      window.setTimeout(() => highlightFor('q2-flash', 'q2s', []), 1200)
    }
    setSaid({ text, at: { left: r?.left ?? EDGE, top: r?.top ?? EDGE } })
    close()
  }

  /* the comment, a reply in the post's thread: that thread is read again */
  const rereadThread = (s: Selected) => {
    reread(s.post)
    const p = postOf(s.post)
    if (p?.conversation) void readThread(p.conversation, p.root ?? p.id).catch(() => {})
  }

  /* one deep dive's operation key, kept until it succeeds (a retry is the same act) */
  const diveOp = useRef<string | null>(null)
  useLayer(readOnly ? null : (
    <>
      {now && mode === 'bar' && ('sel' in now
        ? <Bar sel={now.sel} range={now.range} barRef={bar} onClose={() => close()} onDone={done}
            onMode={setMode} />
        : <Refused why={now.refused} range={now.range} barRef={bar} />)}
      {sel && (mode === 'comment' || mode === 'dive') && (
        <CommentEditor sel={sel} kind={mode} panelRef={panel} range={now!.range} initial={mode === 'comment' ? carried : ''}
          onSend={mode === 'comment' ? (text) => { setCarried(text); setFromComment(true); setMode('send') } : undefined}
          onClose={() => { setCarried(''); setFromComment(false); close(false) }}
          save={mode === 'comment' ? undefined : async (why) => {
            const by = await store.loadMe()
            const got = await deepDive(sel.post, { by, why, version: sel.version, passage: sel.passage, op: (diveOp.current ??= newOp()) })
            diveOp.current = null
            reread(sel.post)
            /* the new conversation is read where this page reads one */
            window.dispatchEvent(new CustomEvent('q2:open-conversation', { detail: got.conversation }))
            return 'Deep dive opened'
          }}
          onSaved={(text) => { rereadThread(sel); done(text) }} />
      )}
      {sel && mode === 'send' && (
        <SendToAgent sel={sel} text={fromComment ? carried : undefined}
          onClose={(written) => {
            if (sentRef.current) { sentRef.current = false; setCarried(''); setFromComment(false); close(false); return }
            if (fromComment) { if (written !== undefined) setCarried(written); setMode('comment'); setFromComment(false) } else close(false)
          }}
          onSent={() => { sentRef.current = true; rereadThread(sel) }} />
      )}
      {said && <div className="q2s-said" role="status" style={{ left: said.at.left, top: said.at.top }}>{said.text}</div>}
    </>
  ))
  return null
}

/** A selection that cannot be a passage: said quietly, beside it. */
function Refused({ why, range, barRef }: { why: string; range: Range; barRef: React.MutableRefObject<HTMLDivElement | null> }) {
  const pos = usePlaced(range, barRef, [why])
  return (
    <div ref={barRef} className="q2s-bar q2s-refused" role="status" style={pos ? { left: pos.left, top: pos.top } : { left: 0, top: 0, visibility: 'hidden' }}>
      Can't annotate this selection: {why}
    </div>
  )
}
