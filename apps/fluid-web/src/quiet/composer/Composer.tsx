/* Quiet's one composer, mounted through the existing dock seam. Its compact
   presentation keeps the existing drafts, postingBody/settlingKey and Fluid's
   bodyOf and Settings component. Runtime/model/effort, Persona, authority and
   consent choices continue to be made by that shared component. */
import { useEffect, useRef, useState } from 'react'
import { post, useApi, type Conversation, type Id, type Turn } from '../../api'
import { ACTION_WHY, bodyOf, emptyDraft, type Addressee } from '../../composer/draft'
import { useCapacity, useExecution } from '../../composer/execution'
import Settings from '../../fluid/composer/Settings'
import { tokenOf } from '../../fluid/composer/words'
import type { Draft, SetDraft } from '../contract'
import { message, postingBody, settlingKey, submissionKey, type PostingAction } from '../model'
import { newDraft } from './drafts'
import './composer.css'

/** THE SAME BODY FLUID'S OWN COMPOSER WOULD SEND, for one addressee marked
 *  for work. `bodyOf` reads `to` and decides `ask-participant` for itself
 *  (`record-only`, chosen explicitly, still dominates -- the same rule Fluid
 *  reads), so the dispatch array it returns carries the addressee's runtime,
 *  model and effort exactly as Fluid's cascade set them. */
export function dispatchBody(text: string, to: Addressee, action: PostingAction, author: Id,
  conversation: Id, topic: Id | null, reply: Turn | null, op: string) {
  const draft = { ...emptyDraft(), text, to: [to], action: action === 'record-only' ? ('record-only' as const) : undefined }
  const body = bodyOf(draft, author, topic ? [topic] : [])
  if (reply && !body.addressed_to.length && reply.author !== author) body.addressed_to = [reply.author]
  return { ...body, conversation, ...(reply ? { replies_to: reply.id } : {}), op }
}

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

  /* ASKING SOMEBODY TO WORK, reachable from the composer and nowhere persisted:
     a runtime chosen for one message is not a fact about the place, the way
     the typed words are -- so this is ordinary state, reset whenever the
     place being written to changes, never the module-level store drafts.ts
     keeps the text in. */
  const [addressee, setAddressee] = useState<Addressee | null>(null)
  const [picking, setPicking] = useState(false)
  const [settingsOpen, setSettingsOpen] = useState(false)
  const settingsButton = useRef<HTMLButtonElement>(null)
  const closeSettings = () => { setSettingsOpen(false); settingsButton.current?.focus() }
  useEffect(() => { setAddressee(null); setPicking(false); setSettingsOpen(false) }, [conversation, topic, reply?.id])

  /* The conversation's participants, asked for only once the picker is
     reachable -- never on every mount (the same discipline execution.ts
     states for runtimes and capacity, just below). */
  const wantWho = picking || !!addressee
  const who = useApi<Conversation>(wantWho ? `/api/conversations/${encodeURIComponent(conversation)}?batch=0` : null)
  const declared = who.data?.participants ?? []
  const choices = declared.filter((p) => p.participant !== me)

  const wantRuntimes = settingsOpen
  const ex = useExecution(wantRuntimes)
  const cap = useCapacity(wantRuntimes)

  const send = async () => {
    if (!me || !draft.text.trim() || submitting.current) return
    submitting.current = true
    setBusy(true)
    setError(null)
    // The same submission asks with the key it already used (`settlingKey`).
    const plainSubmission = submissionKey(draft.text, draft.action, reply)
    const dispatch = addressee ? dispatchBody(draft.text, addressee, draft.action, me, conversation, topic, reply, '') : null
    const submission = dispatch ? JSON.stringify([plainSubmission, dispatch]) : plainSubmission
    const candidate = draft.sent && draft.sent.submission !== submission && draft.sent.op === draft.op
      ? crypto.randomUUID() : draft.op
    const op = settlingKey(submission, candidate, draft.sent)
    try {
      const body = addressee
        ? dispatchBody(draft.text, addressee, draft.action, me, conversation, topic, reply, op)
        : postingBody(draft.text, draft.action, me, conversation, topic, reply, op)
      const result = await post<{ post: Id }>('/fluid/api/posts', body)
      setDraft(newDraft(), draft.op)
      setAddressee(null)
      if (active.current && latestOp.current === draft.op) onPosted(result.post)
    } catch (e) {
      // Remember what was asked, so typing these words away and back asks
      // once. Guarded on this draft's key: a newer draft is the reader's.
      setDraft({ ...draft, sent: { submission, op } }, draft.op)
      if (active.current) setError(message(e))
    }
    finally { submitting.current = false; if (active.current) setBusy(false) }
  }
  const box = useRef<HTMLTextAreaElement>(null)
  useEffect(() => {
    const el = box.current
    if (!el) return
    el.style.height = '0px'
    el.style.height = Math.min(el.scrollHeight, 320) + 'px'
  }, [draft.text])
  const sendLabel = busy ? 'Sending\u2026' : draft.action === 'record-only' ? 'Post \u2191' : addressee?.dispatch ? `Ask ${addressee.alias} \u2191` : 'Ask Mentis \u2191'
  /* A PLAIN DIV, NOT A FORM. `Settings.tsx` draws its own buttons with no
     `type="button"` -- it is Fluid's own, always opened in a Float outside
     any form, where a bare <button> submitting nothing is harmless. Wrapping
     it in a <form> here would make every one of its buttons a submit button
     by the HTML default, firing `send()` the moment a runtime was picked
     (found while testing the cascade: clicking "claude" posted the draft on
     the spot). Sending is one explicit click or Ctrl/⌘ Enter, never implicit. */
  return <div className={'qc-composer' + (draft.text || addressee ? ' qc-composer-writing' : '')}>
    <label htmlFor="qc-compose">{reply ? `Replying to #${reply.number} · ${reply.author_alias}` : 'Continue the conversation'}</label>
    {/* Readable, not only a `title` tooltip nobody opened -- same text, kept
        off-screen so a sighted reader keeps the compact row the owner asked
        for, and a screen reader still gets it. */}
    <p className="qc-sr-only" aria-label="what each way of sending does">
      Ask Mentis — {ACTION_WHY['ask-mentis']} Ask someone — {ACTION_WHY['ask-participant']} Post only — {ACTION_WHY['record-only']}
    </p>
    <textarea ref={box} id="qc-compose" placeholder={reply ? 'Write a reply…' : 'A thought, a question, a next step…'}
      value={draft.text} disabled={busy} onChange={(e) => setDraft({ ...draft, text: e.target.value, op: crypto.randomUUID() })}
      onKeyDown={(e) => { if (e.key === 'Enter' && (e.ctrlKey || e.metaKey) && !e.nativeEvent.isComposing) { e.preventDefault(); void send() } }} />
    <div className="qc-compose-actions"><span className="qc-compose-hint">Ctrl / ⌘ Enter</span>
      {addressee ? (
        <span className="qc-compose-to">
          <button ref={settingsButton} type="button" aria-expanded={settingsOpen} aria-controls="qc-compose-settings"
            title="Will be asked to work: open to choose runtime, model and effort"
            onClick={() => setSettingsOpen((s) => !s)}>
            <span>{addressee.alias} ▾</span><small>{tokenOf(addressee, declared)}</small>
          </button>
          <button type="button" aria-label={`not asking ${addressee.alias} to work`}
            onClick={() => { setAddressee(null); setSettingsOpen(false) }}>×</button>
        </span>
      ) : (
        <select aria-label="Ask someone to work" value="" disabled={busy}
          onFocus={() => setPicking(true)}
          onChange={(e) => {
            const p = choices.find((c) => c.participant === e.target.value)
            if (p) setAddressee({ participant: p.participant, alias: p.alias, dispatch: true })
          }}>
          <option value="">Ask someone to work…</option>
          {choices.map((p) => <option key={p.participant} value={p.participant}>{p.alias}</option>)}
        </select>
      )}
      <select aria-label="Posting action" value={draft.action} disabled={busy} title={ACTION_WHY[draft.action]}
        onChange={(e) => setDraft({ ...draft, action: e.target.value as PostingAction, op: crypto.randomUUID() })}>
        <option value="ask-mentis">Ask Mentis</option><option value="record-only">Post only</option>
      </select><button type="button" className="qc-compose-send" title={ACTION_WHY[draft.action === 'record-only' ? 'record-only' : addressee?.dispatch ? 'ask-participant' : 'ask-mentis']}
        disabled={busy || !me || !draft.text.trim()} onClick={() => void send()}>{sendLabel}</button></div>
    {settingsOpen && addressee && (
      <section id="qc-compose-settings" className="qc-compose-settings" aria-label="Participant settings"
        onKeyDown={(e) => { if (e.key === 'Escape') { e.stopPropagation(); closeSettings() } }}>
        <div className="qc-compose-settings-head"><span>Participant settings</span>
          <button type="button" aria-label="Close participant settings" onClick={closeSettings}>×</button>
        </div>
        <Settings who={addressee} declared={declared} execution={ex} capacity={cap}
          onChange={(next) => setAddressee(next)} />
      </section>
    )}
    {!me && <p className="qc-muted">The author must be available before posting.</p>}
    {error && <p role="alert" className="qc-error">{error} Your draft is still here.</p>}
  </div>
}
