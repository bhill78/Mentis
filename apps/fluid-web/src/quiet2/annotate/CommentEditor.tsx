/* THE COMMENT EDITOR (annotation round, Builder A).
 *
 * A small notepad beside the selected words: the words themselves as its
 * context, a field, Save. Saving is Fluid's `comment()` command: an anchored,
 * record-only comment on exactly that passage of that version. It is the
 * annotation saved, and it never asks an agent for anything.
 *
 * The same notepad asks why, for a Deep dive (Fluid's `deepDive()`), when
 * the toolbar gives it `save` for that.
 *
 * Plain Enter writes (Markdown); Ctrl/Cmd+Enter saves; Escape or Cancel
 * leaves it. Placed in the margin beside the post's words where the column
 * has room for it, otherwise above or below the words, never over them. */
import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { comment } from '../../fluid/actions'
import { commentEditorHeight, submitsComment } from '../../fluid/conversation/annotated'
import { newOp, store } from '../../fluid/store'
import { placeNear } from './Selection'
import type { Selected } from './types'

const W = 340
const GAP = 14

export default function CommentEditor({ sel, kind = 'comment', range, panelRef, save, onSaved, onClose }: {
  sel: Selected
  kind?: 'comment' | 'dive'
  /** the selection, live, for placing the notepad as the page moves */
  range?: Range
  panelRef?: React.MutableRefObject<HTMLElement | null>
  /** saves something other than a comment (a deep dive's reason); returns a short sentence */
  save?: (text: string) => Promise<string>
  onSaved: (said: string) => void
  onClose: () => void
}) {
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const [pos, setPos] = useState<{ left: number; top: number; width: number } | null>(null)
  const box = useRef<HTMLElement | null>(null)
  const field = useRef<HTMLTextAreaElement>(null)
  /* one operation key until it succeeds: a retry is the same comment */
  const op = useRef<string | null>(null)

  /* focused once placed: a hidden field cannot take the focus */
  const placed = pos !== null
  useEffect(() => { if (placed) field.current?.focus({ preventScroll: true }) }, [placed])
  useLayoutEffect(() => {
    const el = field.current
    if (!el) return
    el.style.height = '0px'
    el.style.height = Math.min(commentEditorHeight(el.scrollHeight), 220) + 'px'
  }, [text])

  /* beside the words where there is margin, else above or below them */
  useLayoutEffect(() => {
    const place = () => {
      const el = box.current
      if (!el) return
      const r = range?.getBoundingClientRect()
      const words = r && (r.width || r.height) ? { left: r.left, top: r.top, right: r.right, bottom: r.bottom } : sel.box
      const startEl = range?.startContainer.parentElement
      const col = startEl?.closest('.q2-pane, .q2v')?.getBoundingClientRect()
      const bounds = col ? { left: Math.max(col.left, 0), top: Math.max(col.top, 0), right: Math.min(col.right, document.documentElement.clientWidth), bottom: Math.min(col.bottom, window.innerHeight) } : sel.bounds
      const body = startEl?.closest('.q2-body')?.getBoundingClientRect()
      const vw = document.documentElement.clientWidth, vh = window.innerHeight
      const h = el.offsetHeight
      const room = body ? Math.min(bounds.right, vw) - body.right - 2 * GAP : 0
      if (body && room >= 260) {
        const width = Math.min(W, room)
        const top = Math.max(Math.max(bounds.top, 8), Math.min(words.top - 10, Math.min(bounds.bottom, vh) - 8 - h))
        setPos({ left: body.right + GAP, top, width })
        return
      }
      const width = Math.min(W + 60, bounds.right - bounds.left - 16, vw - 16)
      const at = placeNear(words, bounds, width, h, vw, vh)
      setPos({ left: at.left, top: at.top, width })
    }
    place()
    window.addEventListener('scroll', place, true)
    window.addEventListener('resize', place)
    return () => { window.removeEventListener('scroll', place, true); window.removeEventListener('resize', place) }
  }, [range, sel, err, text])

  const go = async () => {
    const said = text.trim()
    if (!said || busy) return
    setErr(null)
    setBusy(true)
    try {
      let out: string
      if (save) out = await save(said)
      else {
        const by = await store.loadMe()
        op.current ??= newOp()
        const got = await comment(sel.post, {
          by, text: said, version: sel.version, passage: sel.passage, op: op.current,
          ...(sel.conversation ? { conversation: sel.conversation } : {}),
        })
        op.current = null
        void store.posted(got.post, got.home, sel.post).catch(() => {})
        out = 'Comment saved'
      }
      onSaved(out)
    } catch (x) {
      setErr((x as Error).message)
    } finally { setBusy(false) }
  }

  const dive = kind === 'dive'
  const label = dive ? 'Why open a deep dive from these words?' : 'Comment on these words'
  return (
    <section ref={(el) => { box.current = el; if (panelRef) panelRef.current = el }} className="q2s-note" role="dialog" aria-label={label}
      data-q2s-note={kind}
      style={pos ? { left: pos.left, top: pos.top, width: pos.width } : { left: 0, top: 0, width: W, visibility: 'hidden' }}
      onKeyDown={(e) => {
        if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); onClose() }
        /* Tab goes round inside the notepad */
        if (e.key === 'Tab') {
          const all = Array.from(box.current?.querySelectorAll<HTMLElement>('textarea, button:not(:disabled)') ?? [])
          const i = all.indexOf(document.activeElement as HTMLElement)
          if (e.shiftKey && i <= 0) { e.preventDefault(); all[all.length - 1]?.focus() }
          else if (!e.shiftKey && i === all.length - 1) { e.preventDefault(); all[0]?.focus() }
        }
      }}>
      <blockquote className="q2s-context" title={sel.excerpt}>{sel.excerpt}</blockquote>
      <textarea ref={field} className="q2s-field" value={text} disabled={busy} aria-label={label}
        placeholder={dive ? 'Why open a deep dive?' : 'Write a comment…'} aria-keyshortcuts="Control+Enter Meta+Enter"
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => { if (submitsComment(e)) { e.preventDefault(); void go() } }} />
      <div className="q2s-note-foot">
        <span className="q2s-hint">{dive ? 'Opens a new conversation' : 'Saved to the record · no agent is asked'}</span>
        <button type="button" className="q2s-cancel" disabled={busy} onClick={onClose}>Cancel</button>
        <button type="button" className="q2s-save" disabled={!text.trim() || busy} onClick={() => void go()}
          title="Ctrl/⌘ + Enter">{busy ? 'Saving…' : dive ? 'Open deep dive' : 'Save'}</button>
      </div>
      {err && <div className="q2s-err" role="alert">{err}</div>}
    </section>
  )
}
