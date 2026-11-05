import { useEffect, useState } from 'react'
import { createRoot } from 'react-dom/client'
import { NOWHERE, readAddress, writeAddress } from '../../address'
import { QuietNav } from './QuietNav'

function Demo() {
  const [address, setAddress] = useState(() => readAddress())
  useEffect(() => {
    const changed = () => setAddress(readAddress())
    window.addEventListener('hashchange', changed)
    return () => window.removeEventListener('hashchange', changed)
  }, [])
  const navigate = (conversation: string | null, topic: string | null) => {
    window.location.hash = writeAddress({ ...NOWHERE, conversation, topic })
    setAddress(readAddress())
  }
  return <main style={{ display: 'flex', minHeight: '100vh', fontFamily: 'system-ui, sans-serif', background: '#f8f8f4' }}>
    <aside style={{ width: 280, flexShrink: 0, background: '#f0f2ed' }}>
      <QuietNav selectedConversationId={address.conversation} selectedTopicId={address.topic}
        onSelectConversation={(id) => navigate(id, null)} onSelectTopic={(id) => navigate(address.conversation, id)} />
    </aside>
    <div style={{ padding: '2rem', color: '#687375' }}><h1>Navigation demonstration</h1>
      <p>Choose a conversation and topic in the rail.</p><p>Conversation: {address.conversation ?? 'none'}<br />Topic: {address.topic ?? 'all posts'}</p></div>
  </main>
}

createRoot(document.getElementById('root')!).render(<Demo />)
