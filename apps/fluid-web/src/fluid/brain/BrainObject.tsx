/* ONE THING FROM THE BRAIN, OPENED OVER IT (BrainPlace.tsx).
 *
 * Read through what already reads it, not a second inspector: a Turn is a
 * post, drawn by the post renderer full screen uses (render/post.tsx, the
 * shared Markdown renderers); anything else is the record inspector
 * (surfaces/EntryInspect.tsx), read only -- what may be done to a thing is
 * done where it lives, through the doors that already exist.
 *
 * WHAT IT IS AND WHERE IT IS FROM stay in view above it: its kind, its
 * Conversation, its entry id, and the way to where it lives. */

import { useEffect } from 'react'
import EntryInspect from '../../surfaces/EntryInspect'
import { store } from '../store'
import { usePost } from '../conversation/hooks'
import { PostView } from '../render/post'
import { brainRef, isTurn } from './address'
import { ObjectActions } from '../objects/ObjectActions'
import type { Shown } from './overlays'

type Entry = Extract<Shown, { type: 'entry' }>

export default function BrainObject({ shows, conversationName, onGoHome, onOpenConversation, onOpenEntry }: {
  shows: Entry
  conversationName: string | null
  /** go where it lives; absent where the record places it nowhere */
  onGoHome?: () => void
  /** its Conversation, opened over the Brain beside it */
  onOpenConversation?: () => void
  /** another entry, opened over the Brain beside this one */
  onOpenEntry: (entry: string) => void
}) {
  const turn = isTurn(shows)
  return (
    <div className="bz-object" data-entry={shows.entry} data-kind={shows.kind}>
      <p className="bz-where">
        <span className="bz-kind">{turn ? 'turn' : shows.kind}</span>
        {shows.kind !== 'conversation' && conversationName && <> · <span className="bz-conv">{conversationName}</span></>}
        <code className="bz-id" title="Its entry in the record">{shows.entry}</code>
        {onGoHome && (
          <button type="button" className="bz-home" onClick={onGoHome}
            title={turn ? 'Read it in its Conversation' : shows.kind === 'conversation' ? 'Enter this Conversation' : 'Go to the Conversation it is in'}>
            {turn ? 'Read in its Conversation' : shows.kind === 'conversation' ? 'Enter' : 'Go to its Conversation'} →
          </button>
        )}
        {/* THE ONE ACTION ROW (objects/actions.ts); this is its Open already.
            A Turn is acted on as the post it is. */}
        <ObjectActions compact only={['peek', 'float', 'keep', 'primary', 'focus']}
          target={{ address: turn ? 'post:' + shows.entry : brainRef(shows.entry), kind: turn ? 'post' : 'brain', title: shows.title || shows.entry, from: 'the 3D Brain' }} />
        {onOpenConversation && (
          <button type="button" className="bz-home bz-over" onClick={onOpenConversation}
            title="Open its Conversation over the Brain, staying here">Open over the Brain</button>
        )}
      </p>
      <div className="bz-read">
        {turn
          ? <TurnRead id={shows.entry} />
          : <EntryInspect id={shows.entry} readOnly conversation={shows.conversation} conversationName={conversationName}
              onOpenEntry={onOpenEntry} />}
      </div>
    </div>
  )
}

function TurnRead({ id }: { id: string }) {
  const post = usePost(id)
  useEffect(() => { if (!store.posts.has(id)) void store.loadPosts([id]).catch(() => {}) }, [id])
  return (
    <article className="fx-full-post bz-post">
      {post ? <PostView post={post} context="full" here={null} /> : <div className="fw-pending" aria-busy="true" />}
    </article>
  )
}
