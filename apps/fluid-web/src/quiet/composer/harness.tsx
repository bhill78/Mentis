import { useState } from 'react'
import { createRoot } from 'react-dom/client'
import { QuietComposer } from './QuietComposer'

function Harness() {
  const [conversation, setConversation] = useState('')
  const [reply, setReply] = useState('')
  const [posted, setPosted] = useState('')
  return <main style={{ maxWidth: 680, margin: '3rem auto', fontFamily: 'system-ui' }}>
    <h1>Quiet composer demonstration</h1>
    <p>Use a disposable development Brain. Sending writes to the selected conversation.</p>
    <p><label>Conversation ID <input value={conversation} onChange={e => setConversation(e.target.value)} /></label></p>
    <p><label>Reply to post ID (optional) <input value={reply} onChange={e => setReply(e.target.value)} /></label></p>
    <QuietComposer conversationId={conversation.trim() || null} replyToPostId={reply.trim() || null} onPosted={id => setPosted(id)} />
    {posted && <p>Posted: {posted}</p>}
  </main>
}

createRoot(document.getElementById('root')!).render(<Harness />)
