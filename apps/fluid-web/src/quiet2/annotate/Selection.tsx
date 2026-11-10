/* THE SELECTION'S TOOLBAR (annotation round, Builder A).
 *
 * Words selected in a post's body (`[data-post] .q2-body`, wherever the post
 * is drawn: the conversation, a working column, an entered thread, a reply)
 * bring a small floating bar beside them. Icons only, each with a tooltip and
 * an accessible name:
 *
 *     👍 ❤️ 🤔 ❓ │ 💬 ↗ ✈
 *
 * the four reactions Mentis has, Comment (an anchored, record-only reply,
 * written in CommentEditor), Deep dive (a conversation opened from the words)
 * and Send to Agent (SendToAgent.tsx). Every act is one of Fluid's commands
 * (fluid/actions.ts), so the anchors read again and the margin redraws.
 *
 * The bar is above the selection (below where there is no room), inside the
 * window and inside the column the words are in, never over the words. The
 * keyboard: with words selected, Tab moves into the bar; arrows move along
 * it; Escape closes it and gives the keyboard back.
 *
 * On a read-only page nothing here is drawn: every button writes. */
import { useEffect, useLayoutEffect, useRef, useState, type JSX, type ReactNode } from 'react'
import { anchorAt, deepDive, mineOn, reactAs } from '../../fluid/actions'
import { reread, passageOf, sourceOf, useAnchors, type Source } from '../../fluid/conversation/annotated'
import { useLayer } from '../../fluid/frame/layer'
import { newOp, store, type Id, type Post as FluidPost } from '../../fluid/store'
import { highlightFor } from '../../surfaces/passage'
import { READ_ONLY } from '../live'
import { postOf, readThread, sourceOfPost } from '../real'
import CommentEditor from './CommentEditor'
import SendToAgent from './SendToAgent'
import { addToComposer, savePassage, targetComposer } from './passage'
import type { Box, Selected } from './types'
import './selection.css'

export const TOKENS = ['👍', '❤️', '🤔', '❓']
const TOKEN_NAME: Record<string, string> = { '👍': 'Agree', '❤️': 'Love', '🤔': 'Thinking', '❓': 'Question' }
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
  react: <I d={<><circle cx="12" cy="12" r="8.5" /><path d="M8.8 14.2a4.2 4.2 0 0 0 6.4 0" /><path d="M9.3 9.8h.01M14.7 9.8h.01" /></>} />,
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
  const anchors = useAnchors(sel.post)
  const [me, setMe] = useState<Id | null>(store.me)
  useEffect(() => { if (!me) void store.loadMe().then(setMe, () => {}) }, [me])
  const mine = me ? mineOn(anchorAt(anchors, sel.version, sel.passage), me)?.token ?? null : null
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const [pos, setPos] = useState<{ left: number; top: number } | null>(null)
  /* one operation key per pending act: a retry is the same operation */
  const ops = useRef<Record<string, string>>({})
  /* the reaction choice or the capture choices, opened from the bar */
  const [open, setOpen] = useState<null | 'react' | 'capture'>(null)
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
    try { onDone(await fn()) } catch (x) { setErr((x as Error).message) } finally { setBusy(false) }
  }

  useLayoutEffect(() => {
    const place = () => {
      const el = barRef.current
      const r = range.getBoundingClientRect()
      if (!el || (r.width === 0 && r.height === 0)) return
      const first = range.getClientRects()[0] ?? r
      /* centred on the selection's first line, above its top */
      const words = { left: first.left, right: first.right, top: r.top, bottom: r.bottom }
      const at = placeNear(words, boundsOf(range.startContainer.parentElement ?? document.body), el.offsetWidth, el.offsetHeight, document.documentElement.clientWidth, window.innerHeight)
      setPos((p) => (p && p.left === at.left && p.top === at.top ? p : { left: at.left, top: at.top }))
    }
    place()
    window.addEventListener('scroll', place, true)
    window.addEventListener('resize', place)
    return () => { window.removeEventListener('scroll', place, true); window.removeEventListener('resize', place) }
  }, [range, err, barRef, open])

  const react = async (token: string, btn: HTMLButtonElement) => {
    if (busy) return
    setErr(null)
    setBusy(true)
    try {
      const by = await store.loadMe()
      const key = `${token}:${JSON.stringify(sel.passage)}`
      const op = (ops.current[key] ??= newOp())
      const got = await reactAs(sel.post, { by, token, version: sel.version, passage: sel.passage, op })
      delete ops.current[key]
      reread(sel.post)
      onDone(got.already ? `${token} is already yours` : got.changes ? `Changed to ${token}` : `${token} recorded`)
    } catch (x) {
      setErr((x as Error).message)
      if (btn.isConnected) btn.focus()
    } finally { setBusy(false) }
  }

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
      onKeyDown={keys} style={pos ? { left: pos.left, top: pos.top } : { left: 0, top: 0, visibility: 'hidden' }}>
      <div className="q2s-row">
        {/* ONE REACTION CONTROL: Mentis's reactions are attributed marks with no
            effect on anything (anchors.py; worker.py says so to agents), so the
            four tokens are one choice, opened here, not four permanent icons */}
        <button type="button" className={'q2s-btn' + (mine ? ' q2s-mine' : '')} data-q2s="react" onMouseDown={hold}
          aria-haspopup="menu" aria-expanded={open === 'react'} aria-pressed={!!mine}
          aria-label={mine ? `Your reaction here: ${mine} (${TOKEN_NAME[mine]}). Change it` : 'React to these words'}
          title={mine ? `Your reaction: ${mine}` : 'React'} onClick={() => setOpen(open === 'react' ? null : 'react')}>
          {mine ? <span className="q2s-mine-token" aria-hidden="true">{mine}</span> : ICON.react}
        </button>
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
      {open === 'react' && (
        <div className="q2s-menu q2s-tokens" role="menu" aria-label="React with">
          {TOKENS.map((t) => (
            <button key={t} type="button" role="menuitemradio" className="q2s-btn q2s-token" data-token={t} disabled={busy} onMouseDown={hold}
              aria-checked={mine === t} aria-label={`${TOKEN_NAME[t]} ${t}`}
              title={mine === t ? `${t} is your reaction here` : `${TOKEN_NAME[t]}`}
              onClick={(e) => { setOpen(null); void react(t, e.currentTarget) }}>
              <span aria-hidden="true">{t}</span>
            </button>
          ))}
        </div>
      )}
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
  const [pos, setPos] = useState<{ left: number; top: number } | null>(null)
  useLayoutEffect(() => {
    const el = barRef.current
    const r = range.getBoundingClientRect()
    if (!el) return
    const at = placeNear(boxOf(r), boundsOf(range.startContainer.parentElement ?? document.body), el.offsetWidth, el.offsetHeight, document.documentElement.clientWidth, window.innerHeight)
    setPos({ left: at.left, top: at.top })
  }, [range, barRef])
  return (
    <div ref={barRef} className="q2s-bar q2s-refused" role="status" style={pos ? { left: pos.left, top: pos.top } : { left: 0, top: 0, visibility: 'hidden' }}>
      Can't annotate this selection: {why}
    </div>
  )
}
