/* WHERE AN OBJECT CAME FROM: its caption "from #N . @who", which traces it
 * back to its post (spec 5.2, 7). Every presentation draws it under an
 * object (present/Present.tsx), and an object's detail in its head. */

import { useEffect } from 'react'
import * as nav from '../nav'
import { store, type Id } from '../store'
import { usePost } from './hooks'
import { Who } from '../identity/Who'

/** "from #N . @who", which traces the object back to its post. */
export function From({ post: id, kept, className }: { post: Id; kept?: boolean; className?: string }) {
  const post = usePost(id)
  useEffect(() => { if (!post) void store.loadPosts([id]).catch(() => {}) }, [post, id])
  if (!post) return null
  return (
    <button className={'wk-from' + (kept ? ' fw-origin' : '') + (className ? ' ' + className : '')} data-act="from"
      onClick={(e) => { e.stopPropagation(); trace(id) }}>
      {kept ? 'kept from' : 'from'} {post.number != null ? `#${post.number}` : 'a post'}{post.author_name ? <> · <Who id={post.author} name={post.author_name} show="line" size={14} /></> : ''}
      {post.home && post.home !== nav.snapshot().conversation && post.home_name ? ` · ${post.home_name}` : ''}
    </button>
  )
}

/** "from #N" tracing (spec 7): read the post; a reply opens its thread, the
 *  reply being read inside it -- ONE step, so one Back returns to where the
 *  reader was and closes the thread (F6 fix round). A rail gives room first. */
export function trace(id: Id) {
  const post = store.posts.get(id)
  if (!post) return
  const conversation = post.home ?? nav.snapshot().conversation
  if (!conversation) return
  nav.openRail()
  let root = post
  for (let up = store.posts.get(root.reply_to ?? ''); up; up = store.posts.get(up.reply_to ?? '')) root = up
  if (root.id === id) {
    nav.read(conversation, id, post.number)
    return
  }
  nav.openDetail({ kind: 'replies', root: root.id, anchor: { kind: 'post', id: root.id }, mode: 'aside' },
    { read: { conversation, post: id, number: post.number } })
}
