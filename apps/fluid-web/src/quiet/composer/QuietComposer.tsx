import { useRef, useState, type FormEvent } from 'react'
import { post, read } from '../../api'
import { bodyOf, emptyDraft, type Action } from '../../composer/draft'
import './composer.css'

export interface QuietComposerProps {
  conversationId: string | null
  replyToPostId?: string | null
  onPosted?: (postId: string, conversationId: string, replyToPostId: string | null) => void
}

const newOp = () => `quiet-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`

/** A single draft for the selected destination; the server remains the authority on writes. */
export function QuietComposer({ conversationId, replyToPostId = null, onPosted }: QuietComposerProps) {
  const [text, setText] = useState('')
  const [action, setAction] = useState<Action | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const op = useRef(newOp())
  const signature = useRef('')
  const inFlight = useRef(false)
  const current = useRef({ conversationId, replyToPostId, text })
  current.current = { conversationId, replyToPostId, text }
  const chosen = action ?? (replyToPostId ? 'record-only' : 'ask-mentis')

  async function send(event: FormEvent) {
    event.preventDefault()
    if (inFlight.current || !conversationId || !text.trim()) return
    inFlight.current = true
    setBusy(true)
    setError('')
    const destination = conversationId
    const reply = replyToPostId
    const submitted = text
    const nextSignature = JSON.stringify([destination, reply, submitted, chosen])
    if (signature.current !== nextSignature) { op.current = newOp(); signature.current = nextSignature }
    try {
      const people = await read<{ me: string | null; participants: { id: string }[] }>('/fluid/api/participants?limit=1')
      const author = people.me ?? people.participants[0]?.id
      if (!author) throw new Error('No current participant found')
      const built = bodyOf({ ...emptyDraft(), text: submitted, action: chosen }, author, [], chosen)
      if (reply) {
        const result = await read<{ posts: { id: string; author?: string; error?: string }[] }>(`/fluid/api/posts?ids=${encodeURIComponent(reply)}`)
        const parent = result.posts.find(p => p.id === reply && !p.error)
        if (!parent) throw new Error('Could not find the post being replied to')
        if (parent.author && parent.author !== author) built.addressed_to = [parent.author]
      }
      const result = await post<{ post: string }>('/fluid/api/posts', {
        ...built, conversation: destination, ...(reply ? { replies_to: reply } : {}), op: op.current,
      })
      op.current = newOp()
      if (current.current.conversationId === destination && current.current.replyToPostId === reply && current.current.text === submitted) setText('')
      onPosted?.(result.post, destination, reply)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not send message')
    } finally {
      inFlight.current = false
      setBusy(false)
    }
  }

  return <form className="quiet-composer" onSubmit={send}>
    <label htmlFor="quiet-message">{replyToPostId ? 'Reply in thread' : 'Message'}</label>
    <textarea id="quiet-message" value={text} disabled={!conversationId || busy} placeholder={conversationId ? 'Write a message…' : 'Select a conversation'} onChange={e => { setText(e.target.value); op.current = newOp() }} />
    <div className="quiet-composer-actions">
      <label>Send as <select value={chosen} disabled={busy} onChange={e => { setAction(e.target.value as Action); op.current = newOp() }}>
        <option value="ask-mentis">Ask Mentis</option><option value="record-only">Record only</option>
      </select></label>
      <button disabled={!conversationId || !text.trim() || busy} type="submit">{busy ? 'Sending…' : chosen === 'ask-mentis' ? 'Ask Mentis' : 'Record'}</button>
    </div>
    {error && <p role="alert">{error}</p>}
  </form>
}
