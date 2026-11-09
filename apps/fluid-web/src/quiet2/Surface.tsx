/* A WORKING SURFACE: one column of the workspace, holding whatever it was
 * given -- a whole conversation (live, with its own composer), a thread, one
 * post, a picture or file, or one table/code block of a post. Each is the
 * same Mentis content the conversation holds, read from the same store or
 * the same artifact; nothing is copied.
 *
 * ITS HEADER SAYS WHAT IT HOLDS: the conversation's name first, then what in
 * it (thread #702 by brian, a picture from #710, ...), so three surfaces of
 * three conversations can be told apart without counting columns. Opening a
 * thread or a post from inside a surface goes forward within that surface;
 * Back returns. Closing it changes nothing in the conversation.
 *
 * Its composer is its own (Dock.tsx): the conversation, thread and reply
 * target of what this surface shows, never another column's. */
import { useContext, useEffect, useState } from 'react'
import { store } from '../fluid/store'
import { ViewerBody } from '../quiet/media/MediaLayer'
import Dock from './Dock'
import Post, { PageContext, TextBlock, type PostPage, type SurfaceView } from './Post'
import { workingIn, type Working } from './presence'
import { postOf, usePosts, useRealFlow } from './real'
import type { Id, Post as PostT } from './sample'
import { repairText } from './text'
import { FoldedWork, ReplyFold, ThreadView } from './Thread'

/** A conversation's name, as this Brain gives it. */
export function useConversationName(id: Id | null | undefined): string | null {
  const [, redraw] = useState(0)
  const known = id ? store.conversations.get(id)?.name : undefined
  useEffect(() => {
    if (!id || known) return
    let live = true
    void store.loadConversations([id]).then(() => { if (live) redraw((n) => n + 1) }, () => {})
    return () => { live = false }
  }, [id, known])
  return known ? repairText(known) : null
}

const who = (p: PostT | undefined) => p ? p.by.name.replace(/^@/, '') : ''
const num = (p: PostT | undefined) => p?.number ? `#${p.number}` : ''

/** What a view is, in words: [conversation, what in it, kind]. */
function useIdentity(view: SurfaceView): { conversation: string; what: string; kind: string } {
  usePosts()
  const post = view.kind === 'thread' ? postOf(view.root) : view.kind === 'conversation' ? undefined : postOf(view.kind === 'post' ? view.id : view.post)
  const conv = view.kind === 'conversation' ? view.conversation : post?.conversation
  const name = useConversationName(conv) ?? (post && !post.real ? 'Sample conversation' : 'Reading…')
  switch (view.kind) {
    case 'conversation': return { conversation: name, what: 'the whole conversation', kind: 'Conversation' }
    case 'thread': return { conversation: name, what: [post?.title ?? `Thread ${num(post)}`.trim(), `by ${who(post)}`].join(' · '), kind: 'Thread' }
    case 'post': return { conversation: name, what: [post?.title ?? `Post ${num(post)}`.trim(), `by ${who(post)}`].join(' · '), kind: post?.replyTo ? 'Reply' : 'Post' }
    case 'media': return { conversation: name, what: `${view.item.name} · from ${num(post) || 'a post'} by ${who(post)}`, kind: view.item.kind === 'image' ? 'Picture' : 'File' }
    case 'block': return { conversation: name, what: `${view.label} · from ${num(post) || 'a post'} by ${who(post)}`, kind: view.label }
  }
}

/** One whole conversation, live: its latest threads and its own composer. */
function ConversationView({ conversation, working, onPosted, replyTo, setReplyTo }: {
  conversation: Id; working: Working[]; onPosted: (root: Id | null) => void
  /** this view's reply target, kept by the surface with the view itself */
  replyTo: PostT | null; setReplyTo: (p: PostT | null) => void
}) {
  usePosts()
  const [reread, setReread] = useState(0)
  const flow = useRealFlow('real', conversation, reread)
  const name = useConversationName(conversation) ?? flow.read?.name ?? 'Reading…'
  const outer = useContextPage()
  const here: PostPage = { ...outer, onReply: (p) => setReplyTo(p), who: null, topic: null, onWho: () => {}, onTopic: () => {} }
  return (
    <PageContext.Provider value={here}>
      <header className="q2-conv-head q2-surface-conv-head">
        <h1>{name}</h1>
        <p className="q2-conv-meta">{flow.read ? `${flow.read.total} posts · the latest threads` : flow.error ? `Could not read it: ${flow.error}` : 'Reading…'}</p>
      </header>
      <div className="q2-stream">
        {(flow.read?.top ?? []).map((id) => postOf(id)).filter((p): p is PostT => !!p).map((p) => (
          <div key={p.id} className="q2-flow-item"><Post post={p} threadMarks={<FoldedWork root={p.id} />} /><ReplyFold root={p.id} /></div>
        ))}
      </div>
      <Dock conversation={conversation} replyTo={replyTo} onClearReply={() => setReplyTo(null)}
        onPosted={(root) => { onPosted(root); if (!root) setReread((n) => n + 1) }}
        working={workingIn(working, conversation)} />
    </PageContext.Provider>
  )
}

const useContextPage = () => useContext(PageContext)!

export function SurfacePane({ n, view: first, onClose, page, onPosted, working }: {
  n: number; view: SurfaceView; onClose: () => void; page: PostPage
  onPosted: (root: Id | null) => void; working: Working[]
}) {
  usePosts()
  /* what this surface has shown, most recent last: Back walks it */
  const [stack, setStack] = useState<SurfaceView[]>([first])
  const view = stack[stack.length - 1]
  const go = (v: SurfaceView) => setStack((s) => [...s, v])
  /* WHAT EACH VIEW WAS ANSWERING stays with that view: going forward and
     coming Back finds the draft's target where it was left (Fluid keeps
     the draft's words by destination; this keeps its parent) */
  const [held, setHeld] = useState<Record<number, { selected: Id | null; replyTo: PostT | null }>>({})
  const at = stack.length - 1
  const selected = held[at]?.selected ?? null
  const replyTo = held[at]?.replyTo ?? null
  const setSelected = (id: Id | null) => setHeld((h) => ({ ...h, [at]: { selected: id, replyTo: h[at]?.replyTo ?? null } }))
  const setReplyTo = (p: PostT | null) => setHeld((h) => ({ ...h, [at]: { selected: h[at]?.selected ?? null, replyTo: p } }))
  const setBoth = (id: Id | null, p: PostT | null) => setHeld((h) => ({ ...h, [at]: { selected: id, replyTo: p } }))
  const back = () => { setHeld((h) => { const n = { ...h }; delete n[at]; return n }); setStack((s) => s.slice(0, -1)) }
  const id = useIdentity(view)
  const shownPost = view.kind === 'thread' ? postOf(view.root) : view.kind === 'post' ? postOf(view.id) : undefined
  const here: PostPage = {
    ...page,
    onReply: (post) => setBoth(post.id, post),
    /* inside a surface, reading a thread or opening anything goes forward
       here: it never replaces another surface, and Back returns */
    onEnter: (root) => go({ kind: 'thread', root }),
    onBeside: (v) => go(v),
    onView: page.onView,
    openElsewhere: () => null,
  }
  const conversationOf = shownPost?.real ? shownPost.conversation ?? null : null
  const threadHere = view.kind === 'thread' ? view.root : view.kind === 'post' ? view.id : undefined
  return (
    <PageContext.Provider value={here}>
      <div className="q2-surface-view" data-surface={n}>
        <header className="q2-surface-head">
          {stack.length > 1 && <button className="q2-surface-back" onClick={back} aria-label="back" title="Back to what this surface showed before">←</button>}
          <div className="q2-surface-id">
            <span className="q2-surface-name" title={id.conversation}>{id.conversation}</span>
            <span className="q2-surface-what" title={id.what}><span className="q2-surface-kind">{id.kind}</span>{view.kind === 'conversation' ? null : ` · ${id.what}`}</span>
          </div>
          {selected && selected !== threadHere && view.kind === 'thread' && (
            <button className="q2-link-quiet" onClick={() => go({ kind: 'post', id: selected })}>Open the chosen reply alone</button>
          )}
          <button className="q2-surface-close" onClick={onClose} aria-label={`close surface ${n}: ${id.conversation}`} title="Close this surface (nothing in the conversation changes)">×</button>
        </header>
        <div className={'q2-col q2-surface-col' + (view.kind === 'media' || view.kind === 'block' ? ' q2-surface-content' : '')}>
          {view.kind === 'conversation' && <ConversationView conversation={view.conversation} working={working} onPosted={onPosted}
            replyTo={replyTo} setReplyTo={setReplyTo} />}
          {view.kind === 'thread' && <ThreadView root={view.root} selected={selected} onSelect={setSelected} />}
          {view.kind === 'post' && (shownPost ? <><Post post={shownPost} threadMarks={<FoldedWork root={shownPost.id} />} /><ReplyFold root={shownPost.id} /></> : <p className="q2-folded">Reading…</p>)}
          {view.kind === 'media' && (
            <figure className="q2-surface-media">
              <ViewerBody item={view.item} />
              <figcaption>
                <button className="q2-link-quiet" onClick={() => go({ kind: 'post', id: view.post })}>Show the post it is from</button>
                {' · '}<a className="q2-link-quiet" href={view.item.url} download={view.item.name}>Download</a>
              </figcaption>
            </figure>
          )}
          {view.kind === 'block' && (() => {
            const p = postOf(view.post)
            const b = p?.blocks[view.block]
            return b?.kind === 'text'
              ? <div className="q2-surface-block"><TextBlock md={b.md} scope={`q2s:${p!.id}:${view.block}`} focus={view.element} />
                  <p className="q2-surface-from"><button className="q2-link-quiet" onClick={() => go({ kind: 'post', id: view.post })}>Show the post it is from</button></p></div>
              : <p className="q2-folded">That content is no longer held here.</p>
          })()}
          {(view.kind === 'thread' || view.kind === 'post') && conversationOf && (
            <Dock conversation={conversationOf} thread={threadHere} replyTo={replyTo ?? (selected ? postOf(selected) ?? null : null)}
              onClearReply={() => setBoth(null, null)} onPosted={onPosted}
              working={workingIn(working, conversationOf)} />
          )}
        </div>
      </div>
    </PageContext.Provider>
  )
}
