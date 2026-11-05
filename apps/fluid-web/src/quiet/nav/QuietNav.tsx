import { useApi } from '../../api'
import type { ConversationList, Id } from '../../api'
import './quiet-nav.css'

export interface QuietNavProps {
  selectedConversationId: Id | null
  selectedTopicId: Id | null
  onSelectConversation: (id: Id) => void
  onSelectTopic: (id: Id | null) => void
}

/** Conversation-specific navigation; the enclosing shell owns global navigation. */
export function QuietNav({ selectedConversationId, selectedTopicId, onSelectConversation, onSelectTopic }: QuietNavProps) {
  const { data, error, loading, reload } = useApi<ConversationList>('/api/conversations')
  const conversations = data?.conversations ?? []
  const selected = conversations.find((conversation) => conversation.id === selectedConversationId)

  return <nav className="quiet-nav" aria-label="Conversation navigation">
    <section aria-labelledby="quiet-conversations-heading">
      <h2 id="quiet-conversations-heading">Conversations</h2>
      {loading && !data && <p className="quiet-nav__notice" role="status">Loading conversations…</p>}
      {error && <p className="quiet-nav__notice" role="alert">Could not load conversations. <button type="button" onClick={reload}>Try again</button></p>}
      {data && conversations.length === 0 && <p className="quiet-nav__notice">No conversations yet.</p>}
      <ul className="quiet-nav__list">
        {conversations.map((conversation) => <li key={conversation.id}>
          <button type="button" className="quiet-nav__item" aria-current={conversation.id === selectedConversationId ? 'true' : undefined}
            onClick={() => onSelectConversation(conversation.id)}>{conversation.name || 'Untitled conversation'}</button>
        </li>)}
      </ul>
    </section>
    {selected && <section aria-labelledby="quiet-topics-heading" className="quiet-nav__topics">
      <h2 id="quiet-topics-heading">Topics <span>in {selected.name || 'this conversation'}</span></h2>
      <ul className="quiet-nav__list">
        <li><button type="button" className="quiet-nav__item" aria-current={selectedTopicId === null ? 'true' : undefined}
          onClick={() => onSelectTopic(null)}>All posts</button></li>
        {selected.topics.map((topic) => <li key={topic.id}>
          <button type="button" className="quiet-nav__item" aria-current={topic.id === selectedTopicId ? 'true' : undefined}
            onClick={() => onSelectTopic(topic.id)}>{topic.name}</button>
        </li>)}
      </ul>
      {selected.topics.length === 0 && <p className="quiet-nav__notice">No topics yet.</p>}
    </section>}
  </nav>
}
