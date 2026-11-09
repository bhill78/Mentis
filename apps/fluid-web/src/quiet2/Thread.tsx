/* REPLIES, AS PRESENTATIONS OF THE SAME POSTS (round 2).
 *
 * A reply is a post that answers another; nothing here holds one of its own.
 * Every view below reads the one store (real.ts) by id:
 *
 *  - In the flow, a post with replies ends in a quiet three-dot divider
 *    saying how many, which unfolds them in place and folds them away.
 *  - A thread entered in the reading column is its post, the divider, and
 *    every reply in full, nested as the record nests them.
 *  - A working surface shows the same thread, or one post, beside the
 *    conversation; its replies can be chosen one at a time.
 *
 * While a thread is open in a surface, its post in the flow says so instead
 * of unfolding a second copy beside it. */
import { useState } from 'react'
import Post, { usePage } from './Post'
import { childrenOf, postOf, threadSize, usePosts, useThread } from './real'
import type { Id, Post as PostT } from './sample'

/** How deep replies are drawn nested; deeper ones are drawn at this depth,
 *  each saying what it answers. */
const DEEPEST = 3

function replyingToOf(p: PostT) {
  if (!p.replyTo) return undefined
  const to = postOf(p.replyTo)
  if (to) return { name: to.by.name, title: to.title }
  return p.replyNumber ? { name: `#${p.replyNumber}` } : undefined
}

/** The posts under `parent`, each in full, nested as the record has them. */
export function ReplyTree({ parent, depth = 1, selected, onSelect }: {
  parent: Id; depth?: number; selected?: Id | null; onSelect?: (id: Id) => void
}) {
  usePosts()
  const page = usePage()
  const elsewhere = page.openElsewhere
  const kids = childrenOf(parent)
  if (!kids.length) return null
  return (
    <ol className={'q2-replies' + (depth > 1 ? ' nested' : '')} data-depth={Math.min(depth, DEEPEST)}>
      {kids.map((r) => elsewhere(r.id) ? (
        <li key={r.id} className="q2-reply">
          <p className="q2-elsewhere-line">{r.by.name.replace(/^@/, '')}'s reply{threadSize(r.id) ? ` and ${threadSize(r.id)} under it` : ''} · open in {elsewhere(r.id)}</p>
        </li>
      ) : (
        <li key={r.id} className="q2-reply">
          <Post post={r} replyingTo={depth > 1 || r.replyTo !== parent ? replyingToOf(r) : undefined}
            selected={selected === r.id} onSelect={onSelect ? () => onSelect(r.id) : undefined} />
          <ReplyTree parent={r.id} depth={depth + 1} selected={selected} onSelect={onSelect} />
        </li>
      ))}
    </ol>
  )
}

/** The divider between a post and its replies: · · · and what lies beyond. */
function Divider({ children }: { children: React.ReactNode }) {
  return (
    <div className="q2-divider-dots" role="presentation">
      <span className="q2-dots" aria-hidden="true">· · ·</span>
      <span className="q2-dots-words">{children}</span>
    </div>
  )
}

/** Under a post in the flow: how many replies, unfolded on request. */
export function ReplyFold({ root }: { root: Id }) {
  usePosts()
  const page = usePage()
  const [open, setOpen] = useState(false)
  const n = threadSize(root)
  const state = useThread(open ? root : null)
  if (n === 0) return null
  const elsewhere = page.openElsewhere(root)
  const words = `${n} ${n === 1 ? 'reply' : 'replies'}`
  if (elsewhere) return (
    <Divider>
      <span className="q2-elsewhere">{words} · open in {elsewhere}</span>
    </Divider>
  )
  return (
    <div className={'q2-fold' + (open ? ' open' : '')}>
      <Divider>
        <button className="q2-fold-toggle" aria-expanded={open} onClick={() => setOpen(!open)}>
          {open ? `Hide ${words}` : words} <span aria-hidden="true">{open ? '▴' : '▾'}</span>
        </button>
        <span className="q2-fold-more">
          <button className="q2-link-quiet" onClick={() => page.onEnter(root)}>Read the thread</button>
          {page.onBeside && <> · <button className="q2-link-quiet" onClick={() => page.onBeside!({ kind: 'thread', root })}>Open beside</button></>}
        </span>
      </Divider>
      {open && (
        state.error ? <p className="q2-folded" role="alert">Could not read the replies: {state.error}</p>
          : state.loading && !childrenOf(root).length ? <p className="q2-folded">Reading the replies…</p>
          : <ReplyTree parent={root} />
      )}
    </div>
  )
}

/** A whole thread: its post, the divider, every reply in full. */
export function ThreadView({ root, selected, onSelect }: { root: Id; selected?: Id | null; onSelect?: (id: Id) => void }) {
  usePosts()
  const state = useThread(root)
  const p = postOf(root)
  if (!p) return <p className="q2-folded">{state.error ? `Could not read this thread: ${state.error}` : 'Reading the thread…'}</p>
  const n = threadSize(root)
  return (
    <div className="q2-thread">
      <Post post={p} replyingTo={replyingToOf(p)} selected={selected === p.id} onSelect={onSelect ? () => onSelect(p.id) : undefined} />
      <Divider>{n ? `${n} ${n === 1 ? 'reply' : 'replies'}` : 'No replies yet'}</Divider>
      {state.error && <p className="q2-folded" role="alert">Could not read every reply: {state.error}</p>}
      <ReplyTree parent={root} selected={selected} onSelect={onSelect} />
    </div>
  )
}
