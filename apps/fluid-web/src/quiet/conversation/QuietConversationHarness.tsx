import { useState } from 'react'
import { useApi, type ConversationList, type Id } from '../../api'
import { QuietConversationView } from './QuietConversationView'

/** Stands in for the shell's `content` slot (Track A) until it exists, so
 *  this track's component is viewable and demonstrable on its own: pick a
 *  real Conversation from the Brain and read it. Lives in `quiet/conversation/`
 *  (not `quiet/shell/`) and is wired up by its own dev-only entry
 *  (`quiet-postview.html`), not by anything in Fluid or the real shell. */
export function QuietConversationHarness() {
  const list = useApi<ConversationList>('/api/conversations')
  const [picked, setPicked] = useState<Id | null>(null)
  const [lastReply, setLastReply] = useState<Id | null>(null)
  const conversations = list.data?.conversations ?? []

  if (!picked) {
    return (
      <div style={{ maxWidth: '40rem', margin: '2rem auto', padding: '0 1rem', fontFamily: 'system-ui, sans-serif' }}>
        <h2>Quiet Chat -- conversation &amp; reply-chain harness</h2>
        <p>Track A's shell is not built yet, so this stands in for it. Pick a real Conversation to read:</p>
        {list.loading && <p>Reading the Brain's conversations…</p>}
        {list.error && <p>Could not read /api/conversations: {list.error}</p>}
        <ul style={{ listStyle: 'none', padding: 0 }}>
          {conversations.map((c) => (
            <li key={c.id} style={{ margin: '0.4rem 0' }}>
              <button
                type="button"
                onClick={() => setPicked(c.id)}
                style={{ background: 'none', border: 'none', padding: 0, font: 'inherit', textDecoration: 'underline', cursor: 'pointer' }}
              >
                {c.name || c.id} -- {c.turns} posts, {c.participants} people
              </button>
            </li>
          ))}
        </ul>
      </div>
    )
  }

  return (
    <div>
      <div style={{ maxWidth: '46rem', margin: '0 auto', padding: '0.5rem 1.25rem 0', fontFamily: 'system-ui, sans-serif', fontSize: '0.85rem' }}>
        <button type="button" onClick={() => setPicked(null)} style={{ background: 'none', border: 'none', padding: 0, cursor: 'pointer', textDecoration: 'underline' }}>
          &larr; choose another conversation
        </button>
        {lastReply && <span style={{ marginLeft: '1rem', opacity: 0.7 }}>onReply called with post {lastReply} (Track D's composer would open here)</span>}
      </div>
      <QuietConversationView conversationId={picked} onReply={setLastReply} />
    </div>
  )
}
