/* PACKAGE A owns this module: the global header, the conversation navigation
   and the welcome page. At P0 all three render exactly what Quiet rendered
   before the split -- the brand opens a popover listing conversations, and the
   work row's first cell is empty.

   WHAT A CHANGES, AND WHERE. §2 of the concept deletes the popover and reads
   recency along the left side instead: that is ConversationNav, whose mount is
   already in the work row's first cell, and A sets --qc-nav on `.qc` when it
   has lines to show there. The header's centre cell (.qc-cell-title) is where
   the conversation's title goes, so the reading column's column continues
   through the header; Heading.tsx is where that title is built today. None of
   that needs an edit to QuietChat.tsx or to layout.css. */
import { useEffect, useState } from 'react'
import { href } from '../model'
import { ReadState } from '../read'
import BackgroundControl from '../surface/BackgroundControl'
import type { ConversationsRead } from '../contract'
import type { Id } from '../../api'
import './chrome.css'

const matches = (c: { name: string; about: string }, query: string) =>
  (c.name + ' ' + c.about).toLowerCase().includes(query.toLowerCase())

export default function Chrome({ conversation, conversations }: {
  conversation: Id | null; conversations: ConversationsRead
}) {
  const [navigation, setNavigation] = useState(false)
  const [query, setQuery] = useState('')
  const choices = conversations.choices
  useEffect(() => { setNavigation(false) }, [conversation])
  useEffect(() => {
    if (!navigation) return
    const close = (e: KeyboardEvent) => { if (e.key === 'Escape') setNavigation(false) }
    window.addEventListener('keydown', close)
    return () => window.removeEventListener('keydown', close)
  }, [navigation])
  return <>
    <header className="qc-global">
      <button className="qc-brand" aria-expanded={navigation} aria-controls="qc-conversations"
        onClick={() => setNavigation(!navigation)}>MENTIS <span> / Quiet Chat</span> <span aria-hidden="true">⌄</span></button>
      <div className="qc-cell-title" />
      <div className="qc-aside"><BackgroundControl /><a className="qc-fluid" href="/fluid">Open Fluid ↗</a></div>
    </header>
    {navigation && <nav className="qc-navigation" id="qc-conversations" aria-label="Conversations">
      <div className="qc-nav-heading"><h2>Conversations</h2><button onClick={() => setNavigation(false)} aria-label="Close conversations">×</button></div>
      <input autoFocus type="search" aria-label="Find a conversation" placeholder="Find a conversation…"
        value={query} onChange={(e) => setQuery(e.target.value)} />
      <ReadState loading={conversations.loading} error={conversations.error} reload={conversations.reload} />
      {choices.filter((c) => matches(c, query)).map((c) =>
        <a key={c.id} href={href(c.id)} aria-current={c.id === conversation ? 'page' : undefined}>
          <strong>{c.name}</strong><span>{c.about || `${c.turns} posts · ${c.topics.length} topics`}</span>
          {!!c.live_executions && <small>{c.live_executions} running</small>}
        </a>)}
      {!choices.length && conversations.loaded && <p>No conversations yet. Create one in Fluid.</p>}
      {!!choices.length && !choices.some((c) => matches(c, query)) && <p>No matching conversations.</p>}
    </nav>}
  </>
}

/** Conversation navigation, in the work row's first cell. Nothing at P0: the
 *  popover above is still how conversations are reached until A lands. */
export function ConversationNav(_props: { conversation: Id | null; conversations: ConversationsRead }) {
  return null
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
