/* PACKAGE C owns this module: the one composer. It is mounted once, in the
   dock below the stream, so it is outside the region that scrolls and is on
   screen wherever the reader is -- that is what §4 asks for, and it is why the
   mount moved out of Flow and Thread at P0 rather than later.

   WHAT C CHANGES. A textarea that starts shorter than 110px and grows with
   content to a cap; the runtime / model / effort cascade
   (`composer/Settings.tsx`) reachable for an `ask-participant` dispatch, with
   the chosen values arriving in the posting body exactly as Fluid sends them;
   and each posting action stating in words what it does with runtime --
   including that Ask Mentis deliberately carries none (`ACTION_WHY`).

   THE POSTING SEMANTICS DO NOT CHANGE. The body for an Ask Mentis post with
   no dispatch must stay identical, field for field, to today's; the settling
   key must stay the one `model.ts` computes. */
import { useEffect, useRef, useState } from 'react'
import { post, type Id, type Turn } from '../../api'
import type { Draft, SetDraft } from '../contract'
import { message, postingBody, settlingKey, submissionKey, type PostingAction } from '../model'
import { newDraft } from './drafts'
import './composer.css'

export default function Composer({ conversation, topic, me, reply, draft, setDraft, onPosted }: {
  conversation: Id; topic: Id | null; me: Id | null; reply: Turn | null
  draft: Draft; setDraft: SetDraft; onPosted: (id: Id) => void
}) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const submitting = useRef(false)
  const active = useRef(true)
  const latestOp = useRef(draft.op)
  latestOp.current = draft.op
  useEffect(() => {
    active.current = true
    return () => { active.current = false }
  }, [])
  const send = async () => {
    if (!me || !draft.text.trim() || submitting.current) return
    submitting.current = true
    setBusy(true)
    setError(null)
    // The same submission asks with the key it already used (`settlingKey`).
    const submission = submissionKey(draft.text, draft.action, reply)
    const op = settlingKey(submission, draft.op, draft.sent)
    try {
      const result = await post<{ post: Id }>('/fluid/api/posts', postingBody(draft.text, draft.action, me, conversation, topic, reply, op))
      setDraft(newDraft(), draft.op)
      if (active.current && latestOp.current === draft.op) onPosted(result.post)
    } catch (e) {
      // Remember what was asked, so typing these words away and back asks
      // once. Guarded on this draft's key: a newer draft is the reader's.
      setDraft({ ...draft, sent: { submission, op } }, draft.op)
      if (active.current) setError(message(e))
    }
    finally { submitting.current = false; if (active.current) setBusy(false) }
  }
  return <form className="qc-composer" onSubmit={(e) => { e.preventDefault(); void send() }}>
    <label htmlFor="qc-compose">{reply ? `Replying to #${reply.number} · ${reply.author_alias}` : 'Continue the conversation'}</label>
    <textarea id="qc-compose" rows={4} placeholder={reply ? 'Write a reply…' : 'A thought, a question, a next step…'}
      value={draft.text} disabled={busy} onChange={(e) => setDraft({ ...draft, text: e.target.value, op: crypto.randomUUID() })}
      onKeyDown={(e) => { if (e.key === 'Enter' && (e.ctrlKey || e.metaKey) && !e.nativeEvent.isComposing) { e.preventDefault(); void send() } }} />
    <div className="qc-compose-actions"><span className="qc-muted">Ctrl / ⌘ Enter to send</span>
      <select aria-label="Posting action" value={draft.action} disabled={busy}
        onChange={(e) => setDraft({ ...draft, action: e.target.value as PostingAction, op: crypto.randomUUID() })}>
        <option value="ask-mentis">Ask Mentis</option><option value="record-only">Post only</option>
      </select><button type="submit" disabled={busy || !me || !draft.text.trim()}>{busy ? 'Sending…' : draft.action === 'ask-mentis' ? 'Ask Mentis ↑' : 'Post ↑'}</button></div>
    {!me && <p className="qc-muted">The author must be available before posting.</p>}
    {error && <p role="alert" className="qc-error">{error} Your draft is still here.</p>}
  </form>
}
