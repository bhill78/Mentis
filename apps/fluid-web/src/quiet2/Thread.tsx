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
import { useLayoutEffect, useRef, useState, useEffect } from 'react'
import Post, { usePage } from './Post'
import { childrenOf, postOf, threadSize, usePosts, useThread } from './real'
import { pointAt, pointedAt, useLink } from './links'
import { useWorkRoots, workUnder } from './presence'
import { Avatar } from '../fluid/identity/Who'
import type { Id, Post as PostT } from './sample'
import './thread.css'

/** How deep replies are drawn nested: replies to the root at one level,
 *  replies to those at a second; deeper ones are drawn at the second level,
 *  each saying what it answers. Only the drawing is flattened; every reply
 *  keeps its real parent in the record and in the store. */
const DEEPEST = 3

function replyingToOf(p: PostT) {
  if (!p.replyTo) return undefined
  const to = postOf(p.replyTo)
  if (to) return { name: to.by.name, title: to.title }
  return p.replyNumber ? { name: `#${p.replyNumber}` } : undefined
}

/** In the tree: "replying to <name> · #<number>", the number being the
 *  parent's own (the record's, else the one the reply carries). */
function treeReplyingTo(p: PostT) {
  if (!p.replyTo) return undefined
  const to = postOf(p.replyTo)
  const n = to?.number ?? p.replyNumber
  if (to) return { name: to.by.name, title: n ? `#${n}` : to.title }
  return n ? { name: `#${n}` } : undefined
}

/** Where a post's avatar centre sits across its column: the spine of the
 *  replies under it is drawn there. */
const spineOf = (id: Id) => (postOf(id)?.weight === 'article' ? 18 : 13)

/** One reply in the tree: its post, its connector, the replies under it. */
function ReplyItem({ r, depth, flat, selected, onSelect }: {
  r: PostT; depth: number; flat: boolean; selected?: Id | null; onSelect?: (id: Id) => void
}) {
  const page = usePage()
  const link = useLink(r.id)
  const li = useRef<HTMLLIElement>(null)
  const self = useRef<HTMLDivElement>(null)
  const elsewhere = page.openElsewhere(r.id)
  /* the connector ends at the avatar's centre, wherever the label, topics
     or title put it */
  useLayoutEffect(() => {
    const box = li.current, own = self.current
    if (!box || !own) return
    const place = () => {
      const face = own.querySelector(':scope > .q2-post > .q2-byline > .avatar') as HTMLElement | null
      const top = box.getBoundingClientRect().top
      const y = face ? face.getBoundingClientRect().top + face.offsetHeight / 2 - top : 22
      box.style.setProperty('--q2-ay', `${Math.round(y)}px`)
      box.style.setProperty('--q2-ah', `${face ? face.offsetHeight : 0}px`)
    }
    place()
    const ro = new ResizeObserver(place)
    ro.observe(own)
    return () => ro.disconnect()
  }, [elsewhere])
  const point = () => { if (r.replyTo) pointAt(r.id, r.replyTo) }
  const leave = () => pointAt(null)
  /* gone while pointed at (a view changed): let go of the emphasis */
  useEffect(() => () => { if (pointedAt() === r.id) pointAt(null) }, [r.id])
  const cls = 'q2-reply' + (flat ? ' q2-tree-flat' : ' q2-tree-level')
    + (link.replyHot ? ' q2-tree-hot' : '') + (link.parentHot ? ' q2-tree-parent' : '')
    + (link.answering ? ' q2-tree-answering' : '')
  return (
    <li ref={li} className={cls}>
      {link.answering && <span className="q2-tree-mark" aria-hidden="true" />}
      <div ref={self} className="q2-reply-self" onPointerEnter={point} onPointerLeave={leave} onFocus={point} onBlur={leave}>
        {elsewhere ? (
          <p className="q2-elsewhere-line">{r.by.name.replace(/^@/, '')}'s reply{threadSize(r.id) ? ` and ${threadSize(r.id)} under it` : ''} · open in {elsewhere}</p>
        ) : (
          <Post post={r} replyingTo={depth > 1 ? treeReplyingTo(r) : undefined}
            selected={selected === r.id} onSelect={onSelect ? () => onSelect(r.id) : undefined} />
        )}
      </div>
      {!elsewhere && <ReplyTree parent={r.id} depth={depth + 1} selected={selected} onSelect={onSelect} />}
    </li>
  )
}

/** The posts under `parent`, each in full. Two levels are indented, joined
 *  to their parents by a spine and an elbow; deeper replies are drawn at
 *  the second level with a quieter, dashed connector and their label. */
export function ReplyTree({ parent, depth = 1, selected, onSelect }: {
  parent: Id; depth?: number; selected?: Id | null; onSelect?: (id: Id) => void
}) {
  usePosts()
  const kids = childrenOf(parent)
  if (!kids.length) return null
  const flat = depth >= DEEPEST
  return (
    <ol className={'q2-replies' + (depth > 1 ? ' nested' : '') + (flat ? ' q2-tree-flat' : ' q2-tree-level')}
      data-depth={Math.min(depth, DEEPEST)} style={flat ? undefined : { ['--q2-spine' as string]: `${spineOf(parent)}px` }}>
      {kids.map((r) => <ReplyItem key={r.id} r={r} depth={depth} flat={flat} selected={selected} onSelect={onSelect} />)}
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
/* WORK SOMEWHERE IN THIS THREAD, beside its top-level post while the
   replies are folded: who is working, and on which reply -- never drawn as
   if the top-level post were the work's own post (a small "in the thread"
   hook, not the post's own mark). Activating it reads the thread there. */
function ThreadWork({ root }: { root: Id }) {
  const page = usePage()
  const roots = useWorkRoots(page.working)
  const under = workUnder(page.working, roots, root)
  if (!under.length) return null
  const on = (w: (typeof under)[number]) => {
    const p = w.post ? postOf(w.post) : undefined
    const n = p?.number ?? w.number
    const target = n ? `#${n}` : p ? `${p.by.name.replace(/^@/, '')}'s reply` : 'a reply'
    return `${w.alias.replace(/^@/, '')} is working on ${target} in this thread`
  }
  const said = under.map(on).join('; ')
  return (
    <button className="q2-thread-work" title={said + (under.some((w) => w.simulated) ? ' (sample: simulated)' : '')}
      aria-label={`${said}. Read the thread there`}
      onClick={() => page.onEnter(root, under[0].post ?? undefined)}>
      <span className="q2-thread-work-hook" aria-hidden="true">↳</span>
      {under.slice(0, 2).map((w) => (
        <span key={w.key} className="q2-pulse"><Avatar id={w.participant} name={w.alias} size={18} runtime={w.runtime ?? undefined} /></span>
      ))}
      {under.length > 2 && <span className="q2-work-more">+{under.length - 2}</span>}
    </button>
  )
}

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
    <>
      <ThreadWork root={root} />
      <Divider>
        <span className="q2-elsewhere">{words} · open in {elsewhere}</span>
      </Divider>
    </>
  )
  return (
    <div className={'q2-fold' + (open ? ' open' : '')}>
      {/* unfolded, each working reply carries its own mark: no aggregate */}
      {!open && <ThreadWork root={root} />}
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
