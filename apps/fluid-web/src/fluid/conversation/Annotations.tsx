/* ANNOTATIONS ON A POST CARD: reactions, comments and deep dives, on the
 * whole post or on a passage of it (Classic's Anchored Interaction,
 * `surfaces/Anchors.tsx` and `Interact.tsx`, drawn the Fluid way).
 *
 * WHERE THEY ARE. A Fluid column is a post's own measure -- there is no
 * margin beside it, as Classic's reading column has -- so the marks sit in
 * the card's own right gutter, which an annotated card widens a little:
 *
 *     Plan first. The sentence repeats.        ❤️2
 *     Then the next step.
 *
 * one small mark per anchor, level with its passage (a whole-post one level
 * with the post's head), the leading reaction and how many things are there.
 * The passage itself carries a faint lasting wash, plainer while its mark or
 * the passage is pointed at. Nothing is inserted in the words: the card reads
 * and wraps as before, and at rest the gutter is the only thing added.
 *
 * WHAT CAN BE DONE, and how:
 *   - a mark, or the annotated words, opens the anchor in a sheet: what it is
 *     on, the reactions as history (one's own can be withdrawn), each comment
 *     (opened in the post's thread), each deep dive (opened), and the same
 *     react / Comment / Deep dive to answer it;
 *   - selecting words in the post brings a small bar beside the selection:
 *     react, Comment, and Deep dive under ⋯ (Tab moves into it, Escape leaves);
 *   - the post's own toolbar has one entry, Annotate, for the whole post.
 *
 * Every act is one of Fluid's commands (actions.ts), which run the operation
 * Classic's anchors run: the anchor is found or made from the place, and
 * nothing names it. A refusal is said in the server's words. */

import { useEffect, useId, useLayoutEffect, useMemo, useRef, useState, type ReactNode, type RefObject } from 'react'
import { ago } from '../../api'
import { Prose } from '../../prose'
import { highlightFor } from '../../surfaces/passage'
import { turnPartScope } from '../../experimental/renderable'
import { comment, deepDive, reactAs, withdrawReaction, type Passage, type Place, type PostAnchor } from '../actions'
import * as nav from '../nav'
import { closeSheet, openSheet, Sheet, useOpenSheet, useSheetEscape } from '../frame/Sheet'
import { useLayer } from '../frame/layer'
import { newOp, store, type Id, type Post } from '../store'
import { usePost } from './hooks'
import { useActions } from './PostCard'
import { carries, commentEditorHeight, commentsOldestFirst, drawnRange, inTextOrder, lead, passageOf, reread, sourceOf, submitsComment, tallyWords, useAnchors, type Source } from './annotated'
import { said } from './text'
import './annotations.css'

/** The few common reactions, as Classic offers them. */
const TOKENS = ['👍', '❤️', '🤔', '❓']
const MARK_H = 20

/* -- acting --------------------------------------------------------------- */

/** The place an anchor already is, said as a command takes it. */
function placeOf(a: PostAnchor): Place {
  const s = a.selector
  if (s.type === 'version') return { version: s.version }
  const passage: Passage = a.utf16
    ? { part: s.part ?? 0, start: a.utf16.start, end: a.utf16.end, unit: 'utf16', expected_excerpt: a.excerpt ?? '' }
    : { part: s.part ?? 0, start: s.start ?? 0, end: s.end ?? 0, unit: 'codepoint', expected_excerpt: a.excerpt ?? '' }
  return { version: s.version, passage }
}

/** One pending act's operation key, kept until it succeeds: a retry of a
 *  request whose answer was lost is the same operation (Classic's useKeyed). */
function useKeyed() {
  const pending = useRef<Record<string, string>>({})
  return async <T,>(what: string, fn: (op: string) => Promise<T>): Promise<T> => {
    const op = (pending.current[what] ??= newOp())
    const got = await fn(op)
    if (pending.current[what] === op) delete pending.current[what]
    return got
  }
}

/** React, comment and dive on one place of one post. Each returns a short
 *  sentence, and throws the server's own words. */
function useActs(post: Post) {
  const a = useActions()
  const keyed = useKeyed()
  const where = (p: Place) => JSON.stringify(p)
  return {
    react: async (p: Place, token: string) => {
      const by = await store.loadMe()
      const got = await keyed(`react:${where(p)}:${token}`, (op) => reactAs(post.id, { by, token, version: p.version ?? post.version, passage: p.passage, op }))
      reread(post.id)
      return got.already ? `${token} is already yours` : got.changes ? `changed to ${token}` : `${token} recorded`
    },
    comment: async (p: Place, text: string) => {
      const by = await store.loadMe()
      const got = await keyed(`comment:${where(p)}:${text}`, (op) => comment(post.id, { ...p, by, text, conversation: a.here ?? undefined, op }))
      reread(post.id)
      void store.posted(got.post, got.home, post.id).catch(() => {})
      return 'comment posted'
    },
    dive: async (p: Place, why: string) => {
      const by = await store.loadMe()
      const got = await keyed(`dive:${where(p)}:${why}`, (op) => deepDive(post.id, { ...p, by, why, op }))
      reread(post.id)
      closeSheet()
      a.goHome(got.conversation, got.opening_turn)
      return 'deep dive opened'
    },
  }
}

/** A Markdown composer which grows to a useful maximum. Plain Enter writes;
 * Ctrl/Cmd+Enter submits, and Escape or Cancel leaves it. */
function SayBox({ kind, send, onDone, onCancel }: {
  kind: 'comment' | 'dive'
  send: (said: string) => Promise<string>
  onDone: (said: string) => void
  onCancel: () => void
}) {
  const [text, setText] = useState('')
  const [err, setErr] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const field = useRef<HTMLTextAreaElement>(null)
  useEffect(() => field.current?.focus(), [])
  useLayoutEffect(() => {
    const el = field.current
    if (!el) return
    el.style.height = '0px'
    el.style.height = commentEditorHeight(el.scrollHeight) + 'px'
  }, [text])
  const go = async () => {
    const said = text.trim()
    if (!said || busy) return
    setErr(null)
    setBusy(true)
    try { onDone(await send(said)) } catch (x) { setErr((x as Error).message) } finally { setBusy(false) }
  }
  const ask = kind === 'comment' ? 'Comment' : 'Why open a deep dive?'
  const submit = kind === 'comment' ? 'Submit comment' : 'Open deep dive'
  return (
    <div className="fa-say" data-say={kind}>
      <label className="fa-say-label" htmlFor={`fa-${kind}-field`}>{ask} <span>Markdown supported</span></label>
      <textarea id={`fa-${kind}-field`} ref={field} className="fa-field" placeholder={ask} value={text}
        aria-keyshortcuts="Control+Enter Meta+Enter" disabled={busy}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); onCancel() }
          else if (submitsComment(e)) { e.preventDefault(); void go() }
        }} />
      <div className="fa-say-actions">
        <span className="fa-shortcut">Ctrl/⌘ + Enter</span>
        <button type="button" className="fa-cancel" disabled={busy} onClick={onCancel}>Cancel</button>
        <button type="button" className="fa-go" disabled={!text.trim() || busy} onClick={() => void go()}>{busy ? 'Submitting…' : submit}</button>
      </div>
      {err && <div className="fa-err" role="alert">{err}</div>}
    </div>
  )
}

/** The answer to a place: 👍 ❤️ 🤔 ❓ │ Comment ⋯ (Deep dive), or the
 *  composer it grows into. `mine`: the reader's own current token there. */
function Answer({ post, place, mine, onDone, onSaying, keepSelection }: {
  post: Post
  place: Place
  mine?: string | null
  onDone: (said: string) => void
  onSaying?: (saying: boolean) => void
  /** in the selection's bar: a press must not take the selection away */
  keepSelection?: boolean
}) {
  const acts = useActs(post)
  const [say, setSayNow] = useState<null | 'comment' | 'dive'>(null)
  const [more, setMore] = useState(false)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const row = useRef<HTMLDivElement>(null)
  /* a composer left (Escape) or sent gives the keyboard back to its button */
  const left = useRef<null | 'comment' | 'dive'>(null)
  const setSay = (s: null | 'comment' | 'dive') => { if (!s && say) left.current = say; setSayNow(s); onSaying?.(s !== null) }
  useEffect(() => { if (more) row.current?.querySelector<HTMLButtonElement>('[data-fa="dive"]')?.focus() }, [more])
  useEffect(() => {
    if (say || !left.current) return
    row.current?.querySelector<HTMLButtonElement>(`[data-fa="${left.current}"]`)?.focus()
    left.current = null
  }, [say])
  /* a reaction's button is disabled while it is sent, which drops the
     keyboard to the page; once sent, it is given back to that button */
  const pressed = useRef<HTMLButtonElement | null>(null)
  useEffect(() => {
    if (busy || !pressed.current) return
    const a = document.activeElement
    if ((!a || a === document.body) && pressed.current.isConnected) pressed.current.focus()
    pressed.current = null
  }, [busy])
  /* inside a sheet, the first Esc leaves the composer, not the sheet */
  useSheetEscape(useMemo(() => (say ? () => { setSay(null); return true } : null), [say])) // eslint-disable-line react-hooks/exhaustive-deps
  const hold = keepSelection ? (e: React.MouseEvent) => e.preventDefault() : undefined
  if (say)
    return (
      <SayBox kind={say} send={(t) => (say === 'comment' ? acts.comment(place, t) : acts.dive(place, t))}
        onDone={(s) => { setSay(null); onDone(s) }} onCancel={() => setSay(null)} />
    )
  /* arrows move along the row, as along a toolbar */
  const arrows = (e: React.KeyboardEvent) => {
    if (e.key !== 'ArrowRight' && e.key !== 'ArrowLeft') return
    const all = Array.from(row.current?.querySelectorAll<HTMLButtonElement>('button:not(:disabled)') ?? [])
    const i = all.indexOf(document.activeElement as HTMLButtonElement)
    if (i < 0) return
    e.preventDefault()
    all[(i + (e.key === 'ArrowRight' ? 1 : all.length - 1)) % all.length]?.focus()
  }
  return (
    <>
      <div ref={row} className="fa-answer" role="group" aria-label="react or comment" onKeyDown={arrows}>
        {TOKENS.map((t) => (
          <button key={t} className={'fa-token' + (mine === t ? ' mine' : '')} data-token={t} aria-label={`react ${t}`}
            aria-pressed={mine === t} disabled={busy} onMouseDown={hold}
            onClick={async (e) => {
              pressed.current = e.currentTarget
              setErr(null)
              setBusy(true)
              try { onDone(await acts.react(place, t)) } catch (x) { setErr((x as Error).message) } finally { setBusy(false) }
            }}>
            {t}
          </button>
        ))}
        <span className="fa-sep" aria-hidden="true" />
        <button className="fa-act" data-fa="comment" onMouseDown={hold} onClick={() => setSay('comment')}>Comment</button>
        {more
          ? <button className="fa-act fa-secondary" data-fa="dive" title="Open a deep dive from here" onMouseDown={hold} onClick={() => setSay('dive')}>↗ Deep dive</button>
          : <button className="fa-token fa-moremark" data-fa="more" title="More: deep dive" aria-label="More" onMouseDown={hold} onClick={() => setMore(true)}>⋯</button>}
      </div>
      {err && <div className="fa-err" role="alert">{err}</div>}
    </>
  )
}

/* THE KEYBOARD GOES INTO AN OPENED SHEET and comes back out where it was
 * (item 16). A sheet is drawn in the frame's layer, far from the mark or the
 * toolbar that opened it, so without this the next Tab went on to the next
 * post while the sheet stayed open over other words. Opened, the keyboard is
 * on its first reaction; Tab goes round inside it; closed (Escape, a choice,
 * a click outside onto nothing that takes the focus), it is back on `back`. */
const TABBABLE = 'button:not(:disabled), input:not(:disabled), a[href], [tabindex]:not([tabindex="-1"])'

function Held({ back, children }: { back: () => HTMLElement | null | undefined; children: ReactNode }) {
  const box = useRef<HTMLDivElement>(null)
  const to = useRef(back)
  to.current = back
  useEffect(() => {
    const el = box.current
    if (!el) return
    const opener = to.current()
    ;(el.querySelector<HTMLElement>('.fa-answer button:not(:disabled)') ?? el.querySelector<HTMLElement>(TABBABLE) ?? el).focus({ preventScroll: true })
    return () => {
      const now = document.activeElement
      if (now && now !== document.body && !el.contains(now)) return
      const b = opener?.isConnected ? opener : to.current()
      b?.focus({ preventScroll: true })
    }
  }, [])
  const round = (e: React.KeyboardEvent) => {
    if (e.key !== 'Tab') return
    const all = Array.from(box.current?.querySelectorAll<HTMLElement>(TABBABLE) ?? [])
    if (!all.length) { e.preventDefault(); return }
    const i = all.indexOf(document.activeElement as HTMLElement)
    if (e.shiftKey && i <= 0) { e.preventDefault(); all[all.length - 1].focus() }
    else if (!e.shiftKey && i === all.length - 1) { e.preventDefault(); all[0].focus() }
  }
  return <div ref={box} className="fa-held" tabIndex={-1} onKeyDown={round}>{children}</div>
}

/* -- one anchor, opened --------------------------------------------------- */

/** One complete comment in the history, rendered as posts render Markdown. */
function CommentLine({ id, root }: { id: Id; root: Post }) {
  const c = usePost(id)
  const words = c && !c.deleted ? said(c).words : null
  return (
    <li className="fa-comment" data-comment={id}>
      <div className="fa-comment-head">
        <span className="fa-by">{c ? `@${c.author_name.replace(/^@/, '')}` : 'Loading comment…'}</span>
        {c && <time dateTime={new Date(c.at * 1000).toISOString()} title={new Date(c.at * 1000).toLocaleString()}>{ago(c.at)}</time>}
        <button className="fa-comment-open" title="Open this comment in the post's thread" aria-label="Open this comment in the post's thread"
        onClick={() => {
          closeSheet()
          nav.openDetail({ kind: 'replies', root: root.id, anchor: { kind: 'post', id: root.id }, mode: 'aside' },
            c ? { read: { post: id, number: c.number } } : undefined)
        }}>Open in thread</button>
      </div>
      {c?.deleted ? <p className="fa-comment-deleted"><i>Deleted{c.deleted.because ? `: ${c.deleted.because}` : ''}</i></p>
        : words ? <div className="fa-comment-words turn-body fx-text"><Prose src={words} scope={turnPartScope(id, 0)} /></div>
          : <div className="fa-comment-loading" role="status">Loading…</div>}
    </li>
  )
}

function AnchorDetail({ post, a }: { post: Post; a: PostAnchor }) {
  const [me, setMe] = useState<Id | null>(store.me)
  useEffect(() => { if (!me) void store.loadMe().then(setMe).catch(() => {}) }, [me])
  const [err, setErr] = useState<string | null>(null)
  const [saidNow, setSaidNow] = useState<string | null>(null)
  const [, commentsRead] = useState(0)
  const mine = a.history.find((r) => r.current && r.by === me)
  const replies = commentsOldestFirst(a.replies, (id) => store.posts.get(id)?.at)
  const replyKey = a.replies.join('\n')
  useEffect(() => {
    let live = true
    void store.loadPosts(a.replies).then(() => { if (live) commentsRead((n) => n + 1) }).catch(() => {})
    return () => { live = false }
    // IDs, not the array identity, determine whether this history changed.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [replyKey])
  const withdraw = async (reaction: Id) => {
    setErr(null)
    try {
      await withdrawReaction(reaction, { by: await store.loadMe() })
      reread(post.id)
    } catch (x) { setErr((x as Error).message) }
  }
  return (
    <div className="fa-detail" data-anchor={a.anchor}>
      <div className="fa-on">
        {a.deleted ? <i>{a.excerpt_withheld ?? 'the annotated words were deleted'}</i>
          : a.selector.type === 'version' ? <>on the whole post</>
          : <q title={a.excerpt ?? ''}>{a.excerpt}</q>}
        {!a.deleted && !a.version_is_current && <span className="fa-faint"> · on an earlier version</span>}
      </div>
      {a.history.length > 0 && (
        <ol className="fa-history" aria-label="reactions, as history">
          {a.history.map((r) => (
            <li key={r.reaction} data-reaction={r.reaction} className={r.current ? 'current' : 'past'}>
              {r.token ?? <span title={r.token_withheld}>(withheld)</span>} <span className="fa-by">{r.by_alias}</span>
              {r.withdrawn ? ' · withdrawn' : r.deleted ? ` · deleted by ${r.deleted_by_alias}` : r.changed_to ? ' · changed'
                : r.replaced_by.length > 0 ? ` · replaced by ${r.replaced_by.map((x) => x.by_alias).join(', ')}` : ''}
              {r === mine && (
                <button className="fa-withdraw" data-withdraw={r.reaction} title="Withdraw your reaction" onClick={() => void withdraw(r.reaction)}>
                  withdraw
                </button>
              )}
            </li>
          ))}
        </ol>
      )}
      {a.replies.length > 0 && (
        <section className="fa-comment-history" aria-label={`${a.replies.length} ${a.replies.length === 1 ? 'comment' : 'comments'}, oldest first`}>
          <h3>Comments <span>{a.replies.length}</span></h3>
          <ol className="fa-comments">
            {replies.map((c) => <CommentLine key={c} id={c} root={post} />)}
          </ol>
        </section>
      )}
      {a.deep_dives.length > 0 && (
        <div className="fa-dives">
          {a.deep_dives.map((c) => (
            <button key={c} className="fa-dive" data-dive={c} onClick={() => { closeSheet(); nav.enter(c) }}>
              ↗ {store.conversations.get(c)?.name ?? 'deep dive'}
            </button>
          ))}
        </div>
      )}
      {err && <div className="fa-err" role="alert">{err}</div>}
      {!a.deleted && !post.deleted && (
        <div className="fa-foot">
          <Answer post={post} place={placeOf(a)} mine={mine?.token} onDone={setSaidNow} />
        </div>
      )}
      {saidNow && <div className="fa-said" role="status">{saidNow}. It appears in the comments above.</div>}
    </div>
  )
}

/* -- the whole post, from its toolbar -------------------------------------- */

export const annotateSheet = (post: Id, mount: string) => 'post-annotate:' + post + ':' + mount

/** The toolbar's one entry: react, comment or dive on the whole post. */
export function Annotate({ post }: { post: Post }) {
  const mount = useId()
  const id = annotateSheet(post.id, mount)
  const now = useOpenSheet()
  const [said, setSaid] = useState<string | null>(null)
  const button = useRef<HTMLButtonElement>(null)
  const anchors = useAnchors(post.id)
  const me = store.me
  const whole = anchors.find((x) => x.selector.type === 'version' && x.version_is_current)
  const mine = whole?.history.find((r) => r.current && r.by === me)?.token
  if (post.deleted) return null
  const num = post.number != null ? `#${post.number}` : 'this post'
  return (
    <>
      <button ref={button} className="fx-chip more fx-act fa-annotate" data-act="annotate" aria-label={`React to or comment on ${num}`}
        title="Annotate: react, comment, or open a deep dive" aria-expanded={now?.id === id}
        onClick={(e) => { e.stopPropagation(); setSaid(null); openSheet(id, e.currentTarget) }}>
        <span className="fx-act-glyph" aria-hidden="true">☺</span><span className="fx-act-label">Annotate</span>
      </button>
      {now?.id === id && (
        <Sheet id={id} label={`annotate ${num}`} className="fa-pop">
          <Held back={() => button.current}>
            <div className="fa-detail">
              <div className="fa-on">on {num}, the whole post</div>
              {whole ? <AnchorDetail post={post} a={whole} /> : <div className="fa-foot">
                <Answer post={post} place={{ version: post.version }} mine={mine} onDone={(s) => setSaid(s)} />
              </div>}
              {said && <div className="fa-said" role="status">{said}</div>}
            </div>
          </Held>
        </Sheet>
      )}
    </>
  )
}

/* -- the marks, the wash, and the selection --------------------------------- */

export default function Annotations({ post, card }: { post: Post; card: RefObject<HTMLElement | null> }) {
  const mount = useId()
  const anchors = useAnchors(post.id)
  const src = useMemo(() => sourceOf(post), [post])
  const list = useMemo(() => inTextOrder(anchors), [anchors])
  const [tops, setTops] = useState<Record<Id, number>>({})
  const [hot, setHot] = useState<Id | null>(null)
  const [opened, setOpened] = useState<Id | null>(null)
  const now = useOpenSheet()
  const sheet = 'post-anchor:' + post.id + ':' + mount
  const isOpen = now?.id === sheet
  const marks = useRef<HTMLDivElement>(null)
  const bodyOf = () => card.current?.querySelector<HTMLElement>(':scope > .fw-body') ?? null

  /* where each mark goes: level with its passage, never on another */
  const live = useRef({ list, src })
  live.current = { list, src }
  useLayoutEffect(() => {
    const el = card.current
    if (!el || !list.length) return
    const measure = () => {
      const c = el.getBoundingClientRect()
      const head = el.querySelector('.fx-head')?.getBoundingClientRect()
      const y0 = head ? head.top + head.height / 2 - c.top - MARK_H / 2 : 10
      const body = bodyOf()
      const ys = live.current.list.map((a) => {
        const line = drawnRange(a, body, live.current.src)?.getClientRects()[0]
        return [a.anchor, line ? line.top + line.height / 2 - c.top - MARK_H / 2 : y0] as const
      }).sort((x, y) => x[1] - y[1])
      const out: Record<Id, number> = {}
      let floor = -Infinity
      for (const [id, y] of ys) { out[id] = Math.max(y, floor); floor = out[id] + MARK_H + 2 }
      setTops((t) => (JSON.stringify(t) === JSON.stringify(out) ? t : out))
    }
    measure()
    const ro = new ResizeObserver(measure)
    ro.observe(el)
    return () => ro.disconnect()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [list, src, card])

  /* the wash on every annotated passage, plainer on the one pointed at or open */
  useEffect(() => {
    const body = bodyOf()
    highlightFor('fa-on', mount, list.map((a) => drawnRange(a, body, src)).filter((r): r is Range => !!r))
    return () => highlightFor('fa-on', mount, [])
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [list, src, tops])
  const strong = (isOpen && opened) || hot
  useEffect(() => {
    const a = strong ? list.find((x) => x.anchor === strong) : null
    const r = a ? drawnRange(a, bodyOf(), src) : null
    highlightFor('fa-here', mount, r ? [r] : [])
    return () => highlightFor('fa-here', mount, [])
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [strong, list, src])

  const open = (id: Id) => {
    const m = marks.current?.querySelector<HTMLElement>(`[data-mark="${CSS.escape(id)}"]`)
    if (!m) return
    setOpened(id)
    openSheet(sheet, m, 'end')
  }

  /* POINTING AT ANNOTATED WORDS lights them and their mark; a click on them
     (not a drag that selects, not a link) opens what is there. Where
     passages overlap, the shortest under the pointer is meant. */
  const opener = useRef(open)
  opener.current = open
  useEffect(() => {
    const body = bodyOf()
    if (!body || !list.length) return
    const at = (x: number, y: number): Id | null => {
      let best: { id: Id; n: number } | null = null
      for (const a of live.current.list) {
        const r = drawnRange(a, body, live.current.src)
        if (!r) continue
        if (!Array.from(r.getClientRects()).some((q) => x >= q.left && x <= q.right && y >= q.top && y <= q.bottom)) continue
        const n = r.toString().length
        if (!best || n < best.n) best = { id: a.anchor, n }
      }
      return best?.id ?? null
    }
    let frame = 0
    const move = (e: PointerEvent) => {
      if (e.pointerType !== 'mouse') return
      cancelAnimationFrame(frame)
      frame = requestAnimationFrame(() => {
        const id = at(e.clientX, e.clientY)
        setHot(id)
        body.style.cursor = id ? 'pointer' : ''
      })
    }
    const out = () => { cancelAnimationFrame(frame); setHot(null); body.style.cursor = '' }
    const click = (e: MouseEvent) => {
      if (!window.getSelection()?.isCollapsed) return
      if ((e.target as Element).closest?.('a, button, input, textarea')) return
      const id = at(e.clientX, e.clientY)
      if (!id) return
      e.stopPropagation()
      opener.current(id)
    }
    body.addEventListener('pointermove', move)
    body.addEventListener('pointerleave', out)
    body.addEventListener('click', click)
    return () => {
      cancelAnimationFrame(frame)
      body.removeEventListener('pointermove', move)
      body.removeEventListener('pointerleave', out)
      body.removeEventListener('click', click)
      body.style.cursor = ''
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [list.length, post])

  const shown = isOpen && opened ? list.find((a) => a.anchor === opened) : null
  return (
    <>
      {list.length > 0 && (
        <div ref={marks} className="fa-marks" aria-label="annotations" role="group">
          {list.map((a) => {
            const { glyph, n } = lead(a)
            const on = a.selector.type === 'version' ? 'the whole post' : `“${a.excerpt ?? ''}”`
            return (
              <button key={a.anchor} className={'fa-mark' + (carries(a) ? '' : ' fa-empty')} data-mark={a.anchor}
                style={{ top: tops[a.anchor] ?? 10 }} data-hot={hot === a.anchor ? '' : undefined}
                aria-expanded={isOpen && opened === a.anchor}
                aria-label={`Annotation on ${on}: ${tallyWords(a)}`} title={`${tallyWords(a)} · on ${on}`}
                onPointerEnter={() => setHot(a.anchor)} onPointerLeave={() => setHot(null)}
                onClick={(e) => { e.stopPropagation(); if (isOpen && opened === a.anchor) closeSheet(); else open(a.anchor) }}>
                <span className="fa-glyph" aria-hidden="true">{glyph}</span>
                {n > 1 && <span className="fa-n" aria-hidden="true">{n}</span>}
              </button>
            )
          })}
        </div>
      )}
      {shown && (
        <Sheet id={sheet} label="annotation: reactions, comments and deep dives" className="fa-pop">
          {/* opened from the words or from its mark, the keyboard comes back to the mark */}
          <Held back={() => marks.current?.querySelector<HTMLElement>(`[data-mark="${CSS.escape(shown.anchor)}"]`)}>
            <AnchorDetail post={post} a={shown} />
          </Held>
        </Sheet>
      )}
      {!post.deleted && <SelectionBar post={post} src={src} body={bodyOf} />}
    </>
  )
}

/* THE SMALL BAR BESIDE A SELECTION in the post's words (Classic's
 * SelectionBar): react, Comment, and Deep dive behind ⋯. Read once when the
 * selection settles, so the passage does not move under a composer that has
 * the focus. Tab moves into it; Escape leaves the composer, then the bar. */
function SelectionBar({ post, src, body }: { post: Post; src: Source; body: () => HTMLElement | null }) {
  const [at, setAt] = useState<{ passage: Passage | null; refused?: string; range: Range } | null>(null)
  const [saying, setSaying] = useState(false)
  const [pos, setPos] = useState<{ left: number; top: number } | null>(null)
  const [said, setSaid] = useState<string | null>(null)
  const bar = useRef<HTMLDivElement | null>(null)
  const pointerDown = useRef(false)
  const close = (clear = true) => {
    setAt(null)
    setSaying(false)
    setPos(null)
    if (clear) window.getSelection()?.removeAllRanges()
  }
  const live = useRef({ post, src, saying })
  live.current = { post, src, saying }

  useEffect(() => {
    let timer = 0
    const readNow = () => {
      const { src, saying } = live.current
      if (saying || bar.current?.contains(document.activeElement)) return
      const sel = window.getSelection()
      const root = body()
      if (!sel || sel.rangeCount === 0 || sel.isCollapsed || !root) { setAt(null); return }
      const range = sel.getRangeAt(0)
      if (!root.contains(range.startContainer) || !root.contains(range.endContainer)) { setAt(null); return }
      const got = passageOf(range, root, src)
      setSaid(null)
      setAt('ok' in got ? { passage: got.ok, range: range.cloneRange() } : { passage: null, refused: got.refused, range: range.cloneRange() })
    }
    const settle = () => {
      window.clearTimeout(timer)
      if (pointerDown.current) return
      timer = window.setTimeout(readNow, 120)
    }
    const down = (e: PointerEvent) => {
      if (bar.current?.contains(e.target as Node)) return
      pointerDown.current = true
      /* a composer is left by pointing elsewhere, unless something is written in it */
      if (live.current.saying && !bar.current?.querySelector<HTMLTextAreaElement>('.fa-field')?.value) close(false)
    }
    const up = (e: PointerEvent) => {
      pointerDown.current = false
      if (bar.current?.contains(e.target as Node)) return
      settle()
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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  /* while a composer has the focus, the passage stays marked */
  useEffect(() => {
    if (!at || !saying) return
    highlightFor('fa-sel', post.id, [at.range])
    return () => highlightFor('fa-sel', post.id, [])
  }, [at, saying, post.id])

  /* beside the selection, above it (below when there is no room), in the window */
  useLayoutEffect(() => {
    if (!at) return
    const place = () => {
      const r = at.range.getBoundingClientRect()
      if (r.width === 0 && r.height === 0) return
      const w = bar.current?.offsetWidth ?? 240
      const h = bar.current?.offsetHeight ?? 36
      const vw = document.documentElement.clientWidth
      const left = Math.max(8, Math.min(vw - 8 - w, r.left + r.width / 2 - w / 2))
      setPos({ left, top: r.top - h - 8 < 8 ? r.bottom + 8 : r.top - h - 8 })
    }
    place()
    window.addEventListener('scroll', place, true)
    window.addEventListener('resize', place)
    return () => { window.removeEventListener('scroll', place, true); window.removeEventListener('resize', place) }
  }, [at, saying, said])

  /* Tab into the bar while words are selected; Escape out of it */
  useEffect(() => {
    if (!at) return
    const key = (e: KeyboardEvent) => {
      const inBar = bar.current?.contains(document.activeElement)
      if (e.key === 'Escape' && (inBar || !saying)) { e.preventDefault(); e.stopPropagation(); close(); return }
      if (e.key === 'Tab' && !e.shiftKey && !inBar && !saying) {
        const first = bar.current?.querySelector<HTMLButtonElement>('button:not(:disabled)')
        if (first) { e.preventDefault(); first.focus() }
      }
    }
    document.addEventListener('keydown', key, true)
    return () => document.removeEventListener('keydown', key, true)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [at, saying])

  useLayer(!at ? null : (
    <div ref={bar} className={'fa-bar' + (saying ? ' saying' : '')} data-fa-bar={post.id} role="toolbar" aria-label="Act on the selected words"
      style={pos ? { left: pos.left, top: pos.top } : { visibility: 'hidden', left: 0, top: 0 }}>
      {!at.passage ? <div className="fa-note" role="status">{at.refused}</div>
        : said ? <div className="fa-note" role="status">{said}</div>
        : <Answer post={post} place={{ version: post.version, passage: at.passage }} keepSelection onSaying={setSaying}
            onDone={(s) => {
              setSaid(s)
              const r = at.range
              highlightFor('fa-flash', post.id, [r])
              window.setTimeout(() => { highlightFor('fa-flash', post.id, []); close() }, 1200)
            }} />}
    </div>
  ))
  return null
}
