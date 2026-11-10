/* SEND TO AGENT: a selected passage and an instruction, sent as an ordinary
 * reply to the post it is in, through Fluid's own composer (Builder C).
 *
 * NOTHING NEW IS EXECUTED HERE. The editor is Fluid's real `Composer`, with
 * the selected post as both its thread and its reply: addressing with `@`,
 * the split send button, and Mentis's own posting, authorization and
 * execution all apply unchanged. What it adds is only how the passage
 * travels, by mechanisms Mentis already has:
 *
 *   1. a BARE ANCHOR for the exact passage (`POST /api/anchors`,
 *      `anchors.create_anchor`). An anchor asserts nothing, and Fluid hides
 *      an anchor that carries nothing, so a send that is let go leaves
 *      nothing anybody sees. No reaction and no comment is written.
 *   2. the composer's draft for its place (`thread:<conversation>:<post>`)
 *      is seeded with ONE reference, `{type: 'anchor', ref}`. References are
 *      written as parts only when the draft is sent (`refParts`), so the post
 *      is `[text…, anchor]` replying to the anchored Turn: Mentis's anchored
 *      reply, which `anchors.check_parts` accepts because it answers exactly
 *      the Turn the anchor is in, in a conversation that Turn is in.
 *
 * THE CHIP'S WORDS DO NOT COPY THE PASSAGE. The part is stored as sent, and
 * Mentis never stores an anchored excerpt (it is read from the version every
 * time, and withheld once the Turn is deleted), so the reference's `text`
 * names the place, not its words; the words are shown above, read live.
 *
 * DRAFT SAFETY. A place's draft belongs to whoever wrote it. If that place
 * already holds unsent words, addressees, topics or references, the editor
 * does not open over it and creates nothing: it says so, and the words stay
 * exactly as they were. Otherwise, letting the editor go (Cancel, Escape, or
 * the toolbar closing it) puts the place's draft back exactly as it was before
 * it opened; if something was typed, Cancel asks once before discarding it. */
import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import Composer from '../../fluid/Composer'
import { loadDraft, saveDraft } from '../../fluid/composer/drafts'
import type { Draft, DraftRef } from '../../composer/draft'
import { store, type Id } from '../../fluid/store'
import { fluidFetch } from '../../fluid/http'
import { readAnchors } from '../../fluid/actions'
import { CLIENT_HEADERS } from '../../api'
import { READ_ONLY, READ_ONLY_WHY } from '../live'
import type { Box, SendProps } from './types'
import './send.css'

type Phase = 'anchoring' | 'ready' | 'held' | 'shared' | 'readonly' | 'failed' | 'sent'

/** Anything somebody put in a draft that is theirs to keep. */
const holds = (d: Draft) =>
  !!(d.text.trim() || d.to.length || d.topics.length || d.marks.length || d.refs?.length || d.use?.governed.length || d.attached.length)

const GAP = 8
const EDGE = 8
const WIDE = 440

/** Where the editor goes: beside the passage, inside the viewport and the
 *  column (`bounds`), and never over a conversation's own composer. */
function place(box: Box, bounds: Box, height: number) {
  const vw = window.innerWidth
  const vh = window.innerHeight
  const L = Math.max(EDGE, bounds.left)
  const R = Math.min(vw - EDGE, bounds.right)
  const T = Math.max(EDGE, bounds.top)
  let B = Math.min(vh - EDGE, bounds.bottom)
  for (const el of document.querySelectorAll<HTMLElement>('.q2-dock')) {
    if (el.closest('.q2s-send')) continue
    const r = el.getBoundingClientRect()
    if (r.width && r.right > L && r.left < R && r.top > box.bottom && r.top < B) B = r.top - GAP
  }
  const width = Math.max(240, Math.min(WIDE, R - L))
  const left = Math.max(L, Math.min(box.left, R - width))
  const below = B - (box.bottom + GAP)
  const above = box.top - GAP - T
  if (below >= height || below >= above) return { left, width, top: box.bottom + GAP, maxHeight: Math.max(160, below) }
  const h = Math.min(height, above)
  return { left, width, top: Math.max(T, box.top - GAP - h), maxHeight: Math.max(160, above) }
}

export default function SendToAgent({ sel, onClose, onSent }: SendProps) {
  const where = `thread:${sel.conversation}:${sel.post}`
  const [phase, setPhase] = useState<Phase>(READ_ONLY ? 'readonly' : 'anchoring')
  const [err, setErr] = useState<string | null>(null)
  const [held, setHeld] = useState<Draft | null>(null)
  const [confirming, setConfirming] = useState(false)
  const [, setLoaded] = useState(0)
  const [pos, setPos] = useState<ReturnType<typeof place> | null>(null)
  const panel = useRef<HTMLDivElement>(null)
  /* what the place held before, while the seeded reference is ours to take back */
  const before = useRef<Draft | null>(null)
  const sent = useRef(false)
  const anchor = useRef<Id | null>(null)

  const restore = () => {
    if (before.current && !sent.current) saveDraft(where, before.current)
    before.current = null
  }

  /* The bare anchor, then the seeded draft; the composer is shown only after,
     so it reads the draft with the reference already in it. */
  useEffect(() => {
    if (READ_ONLY) return
    sent.current = false
    /* ANOTHER COMPOSER WRITES TO THIS PLACE NOW (the thread's own, below):
       two composers on one draft place overwrite each other, so Send is not
       opened over it */
    if (document.querySelector(`.fx-composer[data-where="${CSS.escape(where)}"]`)) { setPhase('shared'); return }
    const had = loadDraft(where)
    if (holds(had)) { setHeld(had); setPhase('held'); return }
    let live = true
    void store.loadPosts([sel.post]).then(() => live && setLoaded((n) => n + 1), () => {})
    void store.loadConversations([sel.conversation]).then(() => live && setLoaded((n) => n + 1), () => {})
    void (async () => {
      const me = await store.loadMe()
      const res = await fluidFetch('/api/anchors', {
        method: 'POST',
        headers: { ...CLIENT_HEADERS, 'Content-Type': 'application/json' },
        body: JSON.stringify({
          author: me,
          version: sel.version,
          type: 'text-range',
          part: sel.passage.part,
          start: sel.passage.start,
          end: sel.passage.end,
          unit: sel.passage.unit ?? 'utf16',
          expected_excerpt: sel.passage.expected_excerpt,
        }),
      })
      const got = await res.json().catch(() => null)
      if (!res.ok || !got || got.error) throw new Error(got?.error ?? res.statusText)
      if (!live) return
      /* asked again now: somebody may have written here while it was made */
      const now = loadDraft(where)
      if (holds(now)) { setHeld(now); setPhase('held'); return }
      const n = store.posts.get(sel.post)?.number
      const ref = { part: { type: 'anchor', ref: got.anchor as Id, text: n != null ? `the selected passage of #${n}` : 'the selected passage' } } as unknown as DraftRef
      before.current = now
      anchor.current = got.anchor
      saveDraft(where, { ...now, refs: [ref] })
      setPhase('ready')
    })().catch((e) => { if (live) { setErr((e as Error).message); setPhase('failed') } })
    return () => { live = false; restore() }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [where, sel.version, sel.passage.part, sel.passage.start, sel.passage.end, sel.passage.expected_excerpt])

  /* placed beside the passage, and again whenever it changes size */
  useLayoutEffect(() => {
    const el = panel.current
    if (!el) return
    const again = () => setPos(place(sel.box, sel.bounds, el.scrollHeight))
    again()
    const ro = new ResizeObserver(again)
    ro.observe(el)
    window.addEventListener('resize', again)
    return () => { ro.disconnect(); window.removeEventListener('resize', again) }
  }, [sel.box, sel.bounds, phase])

  const close = (force = false) => {
    if (!force && phase === 'ready' && !confirming && loadDraft(where).text.trim()) { setConfirming(true); return }
    restore()
    onClose()
  }

  /* Fluid's composer clears its reply after every post it makes: it was sent. */
  const cleared = () => {
    sent.current = true
    before.current = null
    setPhase('sent')
    const aid = anchor.current
    void readAnchors(sel.post)
      .then((r) => { const a = r.anchors.find((x) => x.anchor === aid); return a?.replies.length ? a.replies[a.replies.length - 1] : null })
      .catch(() => null)
      .then((post) => { onSent?.(post); onClose() })
  }

  const post = store.posts.get(sel.post)
  const conv = store.conversations.get(sel.conversation)
  const by = post?.author_name?.replace(/^@/, '')
  const num = post?.number != null ? `#${post.number}` : 'the selected post'

  const body = (
    <div ref={panel} className="q2s-send" role="dialog" aria-label="Send this passage to an agent"
      style={pos ? { left: pos.left, top: pos.top, width: pos.width } : { visibility: 'hidden' }}
      onKeyDown={(e) => {
        if (e.key !== 'Escape' || e.defaultPrevented) return
        /* the composer's own menus (@, the send choices) take Escape first */
        if ((e.target as HTMLElement).closest('.fx-composer') && document.querySelector('.fx-float, .fc-menu, .fw-send-menu')) return
        e.stopPropagation()
        close()
      }}>
      <div className="q2s-head">
        <b>Send to agent</b>
        <button type="button" className="q2s-x" aria-label="cancel, nothing is sent" title="Cancel: nothing is sent" onClick={() => close()}>×</button>
      </div>
      <blockquote className="q2s-passage" aria-label="the selected passage">{sel.excerpt}</blockquote>
      <p className="q2s-dest" data-destination={sel.conversation} data-reply-to={sel.post}>
        In <b>{conv?.name ?? 'this conversation'}</b>, reply to <b>{num}</b>{by ? <> by <b>{by}</b></> : null}
      </p>
      {phase === 'readonly' && <p className="q2s-note">{READ_ONLY_WHY}</p>}
      {phase === 'anchoring' && <p className="q2s-note">Marking the passage…</p>}
      {phase === 'failed' && <p className="q2s-note q2s-err">The passage could not be marked: {err}. Nothing was sent.</p>}
      {phase === 'shared' && (
        <p className="q2s-note">This thread's own composer is open below, and it writes to the same place. Address the agent there (type <kbd>@</kbd>), or close the thread and send from here. Nothing was changed.</p>
      )}
      {phase === 'held' && (
        <div className="q2s-note">
          <p>There is already an unsent reply here{held?.text.trim() ? <>: “{held.text.trim().slice(0, 140)}{held.text.trim().length > 140 ? '…' : ''}”</> : ''}. It was left exactly as it is; send or clear it in the thread's own composer, then try again.</p>
        </div>
      )}
      {phase === 'ready' && (
        <>
          <p className="q2s-hint">Replies record only until you choose: type <kbd>@</kbd> for the agent, then pick the action on the send button.</p>
          <div className="q2s-composer">
            <Composer conversation={sel.conversation} thread={sel.post} replyTo={sel.post} onClearReply={cleared} autoFocus />
          </div>
          {confirming && (
            <p className="q2s-note q2s-confirm">Discard what you wrote?
              <button type="button" className="q2-link" onClick={() => close(true)}>Discard</button>
              <button type="button" className="q2-link" onClick={() => setConfirming(false)}>Keep writing</button></p>
          )}
        </>
      )}
      {phase === 'sent' && <p className="q2s-note">Sent.</p>}
    </div>
  )
  const root = document.querySelector('.q2.fx') ?? document.body
  return createPortal(body, root)
}
