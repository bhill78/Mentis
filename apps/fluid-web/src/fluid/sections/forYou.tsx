/* -- Section: For you ------------------------------------------------------ */

import { useEffect } from 'react'
import { ago } from '../../api'
import { Who } from '../identity/Who'
import { store, type Id } from '../store'
import { registerSection, type SectionBodyProps } from './registry'
import { READING, useKey } from './shared'

function ForYouCard({ id, onOpenPost }: { id: Id; onOpenPost: (c: Id, p: Id) => void }) {
  const post = useKey('post:' + id, () => store.posts.get(id))
  if (!post) {
    return <div className="fw-for-you-card fw-home-item fw-pending" data-post={id} aria-busy="true">Loading post…</div>
  }

  const textPart = post.parts.find((p) => p.type === 'text')
  const text = (textPart?.text ?? '').trim()
  const excerpt = text.length > 180 ? text.slice(0, 180) + '…' : text
  const targetConv = post.home ?? (post.memberships && post.memberships[0]?.conversation) ?? ''

  return (
    <article
      className="fw-for-you-card fw-home-item"
      data-post={post.id}
      onClick={() => onOpenPost(targetConv, post.id)}
    >
      {excerpt && <p className="fw-for-you-excerpt">{excerpt}</p>}
      <header className="fw-for-you-card-head fw-item-meta">
        <Who id={post.author} name={post.author_name} show="line" size={18} live className="fw-author" />
        <span className="fw-where">
          {post.home_name ? `${post.home_name} · ` : ''}
          {post.number != null ? `#${post.number}` : ''}
        </span>
        <time className="fw-time">{ago(post.at)}</time>
      </header>
    </article>
  )
}

function ForYouZone({ onOpenPost, chrome }: SectionBodyProps) {
  const data = useKey('coll:home:for-you', () => store.homeForYou)

  useEffect(() => {
    void store.loadHomeForYou()
  }, [])

  const items = data?.items ?? []

  return chrome({
    count: items.length,
    children: !data ? READING : items.length === 0 ? (
      <p className="fw-empty">No recent posts for you.</p>
    ) : (
      <div className="fw-for-you-list fw-home-items">
        {items.map((id) => (
          <ForYouCard key={id} id={id} onOpenPost={onOpenPost} />
        ))}
      </div>
    ),
  })
}

registerSection({ show: 'for-you', name: 'For you', body: ForYouZone })
