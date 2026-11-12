/* THE COMPOSER, FLUID'S OWN, wherever a conversation or a thread is shown.
 *
 * EVERY DOCK HOLDS ITS OWN DESTINATION. Its conversation, the post it
 * replies to and the thread it writes in are given to it by the place it
 * sits in -- the reading column or one working surface -- and by nothing
 * else: not by which column was last focused, not by another surface, not by
 * a conversation opened elsewhere. Who is addressed is chosen in the
 * composer itself (`@`) and changes neither. Fluid's composer keeps each
 * draft by its own destination, so a draft is never carried to another.
 *
 * A reply chosen with a post's Reply is Fluid's `replyTo`; inside a thread it
 * is the thread's composer (`thread`), so what is posted lands under its
 * root. While a reply is being written its parent is marked wherever it is
 * shown (links.ts), until it is sent or let go.
 *
 * THE FOOT is one quiet line: who is working in this conversation now (from
 * Mentis's activity, presence.ts) on the left, the keyboard hint on the right. */
import { useEffect, useId, useState } from 'react'
import Composer from '../fluid/Composer'
import { loadDraft } from '../fluid/composer/drafts'
import { READ_ONLY, READ_ONLY_WHY } from './live'
import { Avatar } from '../fluid/identity/Who'
import { store } from '../fluid/store'
import { composingTo } from './links'
import type { Working } from './presence'
import type { Id, Post } from './sample'

export function WorkingLine({ working }: { working: Working[] }) {
  if (!working.length) return <span className="q2-foot-agents" />
  const shown = working.slice(0, 3)
  const more = working.length - shown.length
  const names = working.map((w) => w.alias.replace(/^@/, ''))
  return (
    <span className="q2-foot-agents" role="status" aria-label={`Working now: ${names.join(', ')}`}>
      {shown.map((w) => (
        <span key={w.key} className="q2-foot-agent" title={[w.alias, w.doing, w.simulated ? 'sample: simulated' : null].filter(Boolean).join(' · ')}>
          <span className="q2-pulse"><Avatar id={w.participant} name={w.alias} size={16} runtime={w.runtime ?? undefined} /></span>
          <span className="q2-foot-name">{w.alias.replace(/^@/, '')}</span>
        </span>
      ))}
      {more > 0 && <span className="q2-foot-more">+{more}</span>}
      <span className="q2-foot-verb">working</span>
    </span>
  )
}

export default function Dock({ conversation, thread, replyTo, onClearReply, onPosted, working, why, dockRef }: {
  /** where a new post here belongs; null: there is none to write to (why) */
  conversation: Id | null
  thread?: Id
  /** the post a reply here answers, chosen in this place only */
  replyTo: Post | null
  onClearReply: () => void
  /** after a post is made here: read again whatever shows it */
  onPosted: (root: Id | null) => void
  working: Working[]
  why?: string
  dockRef?: React.Ref<HTMLDivElement>
}) {
  const me = useId()
  const [, setLoaded] = useState(0)
  const want = replyTo?.real ? replyTo.id : null
  /* the target is given at once (a quick send is still a reply); Fluid's
     store is read so the composer can name what it answers */
  useEffect(() => {
    const ids = [want, thread].filter((x): x is Id => !!x)
    if (!ids.length) return
    let live = true
    void store.loadPosts(ids).then(() => { if (live) setLoaded((n) => n + 1) }, () => {})
    return () => { live = false }
  }, [want, thread])
  /* the parent being answered, marked wherever it is shown, while this dock
     writes to it (an explicit reply, or the post a surface shows) */
  const [writing, setWriting] = useState(false)
  /* exactly what Fluid's composer will answer: its reply, else (while it is
     being written in) the thread's own post; a sample post is never one */
  const answering = want ?? (writing ? thread ?? null : null)
  useEffect(() => { composingTo(me, answering); return () => composingTo(me, null) }, [me, answering])
  /* Fluid's composer clears its reply after every post it makes, and also
     when its × lets the reply go. A post has already emptied the draft of
     this place (drafts.ts); a × leaves the words where they are, so the
     writer is still writing and nothing new needs reading. */
  const place = conversation ? (thread ? `thread:${conversation}:${thread}` : `conversation:${conversation}`) : null
  const cleared = () => {
    const sent = !place || !loadDraft(place).text.trim()
    onClearReply()
    if (!sent) return
    setWriting(false)
    const root = thread ?? (replyTo?.real ? replyTo.root ?? replyTo.id : null)
    onPosted(root)
  }
  return (
    <div className="q2-dock" ref={dockRef}
      onFocus={() => setWriting(true)}
      onBlur={(e) => { if (!e.currentTarget.contains(e.relatedTarget as Node) && !e.currentTarget.querySelector('textarea')?.value) setWriting(false) }}
      data-destination={conversation ?? ''} data-thread={thread ?? ''} data-reply-to={want ?? ''}>
      {replyTo && !replyTo.real && (
        <p className="q2-dock-reply">“{replyTo.by.name.replace(/^@/, '')}” is a sample post: a reply can only be posted to a real one.
          <button className="q2-link" onClick={onClearReply}>Dismiss</button></p>
      )}
      {READ_ONLY
        ? <p className="q2-dock-reply q2-readonly-note">{READ_ONLY_WHY}</p>
        : conversation
        ? <Composer key={`${conversation}:${thread ?? ''}`} conversation={conversation} thread={thread}
            replyTo={want ?? thread ?? null} onClearReply={cleared} operations collapsible />
        : <p className="q2-dock-reply">{why ?? 'Reading the Brain…'}</p>}
      <div className="q2-dock-foot">
        <WorkingLine working={working} />
        {!READ_ONLY && <span className="q2-foot-hint">Shift+Enter · New line</span>}
      </div>
    </div>
  )
}
