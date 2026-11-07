/* Track 2: one conversation selector, using Mark III spine rows and hover names. */
import { useRef, useState } from 'react'
import type { CSSProperties } from 'react'
import { href } from '../model'
import { ReadState } from '../read'
import BackgroundControl from '../surface/BackgroundControl'
import HeaderMenu from './HeaderMenu'
import type { ConversationsRead } from '../contract'
import type { ConversationSummary, Id } from '../../api'
import './chrome.css'

const matches = (c: { name: string; about: string }, query: string) =>
  (c.name + ' ' + c.about).toLowerCase().includes(query.toLowerCase())

/** HOW HEAVY A MARK READS. Rises with everything that makes a conversation
 *  busy -- turns, what is awaiting an answer, and live work -- and never
 *  falls as any one of those three rises on its own, so a conversation with
 *  more live executions never reads as quieter than one with fewer. */
export function markWeight(c: Pick<ConversationSummary, 'turns' | 'awaiting' | 'live_executions'>): number {
  const score = c.turns + c.awaiting * 4 + c.live_executions * 6
  return 2 + Math.min(score, 40) / 40 * 4
}

export default function Chrome(_props: {
  conversation: Id | null; conversations: ConversationsRead
}) {
  return <>
    <header className="qc-global">
      <div className="qc-brand-group">
        <a className="qc-brand" href="/quiet">MENTIS <span> / Quiet Chat</span></a>
      </div>
      <div className="qc-cell-title qc-menu-cell">
        <HeaderMenu />
      </div>
      <div className="qc-aside">
        <BackgroundControl />
      </div>
    </header>
  </>
}

/** Conversation navigation, in the work row's first cell. */
export function ConversationNav({ conversation, conversations }: {
  conversation: Id | null; conversations: ConversationsRead
}) {
  const [searching, setSearching] = useState(false)
  const [query, setQuery] = useState('')
  const [all, setAll] = useState(false)
  const searchButton = useRef<HTMLButtonElement>(null)
  const sorted = [...conversations.choices].sort((a, b) => b.last_activity - a.last_activity)
  const filtered = query ? sorted.filter((c) => matches(c, query)) : sorted
  const shown = all || query ? filtered : filtered.slice(0, 5)
  const rest = filtered.length - shown.length

  return <nav className="qc-nav" aria-label="Conversations by recency">
    <div className="qc-nav-tools">
      <button type="button" ref={searchButton} className="qc-nav-search" aria-expanded={searching} aria-controls="qc-nav-query"
        aria-label="Find a conversation" onClick={() => { setSearching((s) => !s); setQuery('') }}>⌕</button>
      {searching && <input id="qc-nav-query" type="search" aria-label="Find a conversation"
        placeholder="Find…" autoFocus value={query} onChange={(e) => setQuery(e.target.value)}
        onKeyDown={(e) => { if (e.key === 'Escape') { setQuery(''); setSearching(false); searchButton.current?.focus() } }} />}
    </div>
    <ReadState loading={conversations.loading} error={conversations.error} reload={conversations.reload} />
    <ol className="qc-nav-marks">
      {shown.map((c, i) => <li key={c.id}>
        <a className="qc-nav-mark" href={href(c.id)} aria-label={c.name} title={c.name}
          aria-current={c.id === conversation ? 'page' : undefined}
          style={{
            '--qc-mark-weight': `${markWeight(c)}px`,
            '--qc-mark-recency': shown.length > 1 ? String(1 - i / (shown.length - 1)) : '1',
          } as CSSProperties}>
          <span className="qc-nav-mark-bar" aria-hidden="true" />
          <span className="qc-nav-mark-label">{c.name}</span>
        </a>
      </li>)}
    </ol>
    {!all && !query && rest > 0 &&
      <button type="button" className="qc-nav-more" onClick={() => setAll(true)}>{rest} more…</button>}
    {all && !query && <button type="button" className="qc-nav-more" onClick={() => setAll(false)}>Show fewer</button>}
    {conversations.loaded && !filtered.length && <p className="qc-muted">No conversations found.</p>}
  </nav>
}

export function Welcome({ conversations }: { conversations: ConversationsRead }) {
  return <main className="qc-welcome" id="qc-reading" tabIndex={-1}>
    <p className="qc-eyebrow">A little room to think</p><h1>Quiet Chat</h1>
    <p>Pick a conversation. Follow a thought.</p>
    <ReadState loading={conversations.loading} error={conversations.error} reload={conversations.reload} />
    <nav aria-label="Choose a conversation">{conversations.choices.map((c) => <a key={c.id} href={href(c.id)}>
      <strong>{c.name}</strong><span>{c.about || `${c.turns} posts · ${c.topics.length} topics`}</span>
    </a>)}</nav>
  </main>
}
