/* WHAT A POST CARRIES, SHOWN RICHLY BUT QUIETLY (#568 3.5, 3.1).
 *
 * It was one text pill, "table · 2 charts → This post". Now: each kind's
 * mark with its count, still one press to This post; the post's pictures as
 * a strip of small plates; and, on hover or focus, open and ◆ keep on each
 * thing. ◆ keep is the workspace's own chooser (workspace/keep.tsx, stream
 * A's `askKeep`): here, in another zone, on a page, on a new page -- kept
 * from the post as from a card, as /lab kept it from every object chip.
 *
 * Nothing is read until it is asked for: the plates come from the post's own
 * parts, and the post's objects (their live addresses, which open and keep
 * need) are read on the first hover, focus or press. */

import { useState } from 'react'
import * as nav from '../nav'
import { inspect } from '../present'
import { store, type Id, type Post, type PostObjectEntry } from '../store'
import { titleOf } from '../workspace/hooks'
import { askKeep, DRAG } from '../workspace/keep'
import { Opt, Sec, Sheet } from '../frame/Sheet'
import { usePostObjects } from './hooks'
import { kindsLabel } from './text'
import { kindOf } from '../../experimental/objectkinds'
import { showWorkspaceContent } from './threads'

/** Each kind's mark: the workspace's own (present/Present.tsx). */
const MARK: Record<string, string> = {
  table: '▦', chart: '▥', checklist: '☑', diagram: '◇', timeline: '┄', image: '▣', doc: '¶', note: '✎',
  reference: '↗', file: '▤', video: '▶', audio: '♪', panel: '▣', text: '¶', link: '⛓',
}
const markOf = (k: string) => MARK[k] ?? '▤'
const kindLabel = (k: string, n: number) => `${n} ${k}${n === 1 ? '' : 's'}`

const PICTURE = /\.(png|jpe?g|gif|webp|svg)$/i
/** The post's own pictures, from its parts: drawn without reading anything. */
export function picturesOf(post: Post): { ref: string; name: string }[] {
  return post.parts
    .filter((p) => p.ref && p.type !== 'text' && !['turn', 'topic', 'conversation', 'acquired'].includes(p.type))
    .filter((p) => p.type === 'image' || String((p as { media_type?: string }).media_type ?? '').startsWith('image/') || PICTURE.test(String(p.name ?? '')))
    .map((p) => ({ ref: String(p.ref), name: String(p.alt ?? p.name ?? 'picture') }))
}

/** The post's objects, read once when first wanted. */
function objectsOf(root: Id): PostObjectEntry[] {
  const held = store.postObjects.get(root)
  return (held?.addresses ?? []).map((a) => store.objects.get(a)).flatMap((st) => (st && 'object' in st && st.object.parent === null && st.object.kind !== 'post-text' ? [st.object] : []))
}
const want = (root: Id) => { if (!store.postObjects.has(root)) void store.loadObjects(root).catch(() => {}) }
async function objectFor(root: Id, ref: string): Promise<PostObjectEntry | null> {
  await store.loadObjects(root).catch(() => {})
  return objectsOf(root).find((o) => o.ref === ref || o.artifact?.ref === ref) ?? null
}

export default function Carries({ post, kinds, readIn, selecting, onRead }: {
  post: Post
  kinds: [string, number][]
  readIn: Id
  selecting: boolean
  /** the card reads its post (so This post shows it) */
  onRead: () => void
}) {
  const pics = picturesOf(post)
  const [menu, setMenu] = useState<HTMLElement | null>(null)
  if (!kinds.length && !pics.length) return null
  const stop = (fn: (e: React.MouseEvent<HTMLElement>) => void) => (e: React.MouseEvent<HTMLElement>) => { e.stopPropagation(); if (!selecting) fn(e) }
  const num = post.number != null ? `#${post.number}` : 'this post'
  const toThisPost = () => { onRead(); nav.showPage('this-post'); showWorkspaceContent() }
  const openPic = async (ref: string, from: HTMLElement) => {
    const o = await objectFor(post.id, ref)
    if (o) inspect(o.address.live, from)
    else window.open(`/api/artifacts/${ref}`, '_blank', 'noopener')
  }
  const keepPic = async (ref: string, from: HTMLElement) => {
    const o = await objectFor(post.id, ref)
    if (o) askKeep({ address: o.address.live }, from)
  }
  return (
    <span className="fx-carries" onPointerEnter={() => want(post.id)} onFocus={() => want(post.id)}>
      {kinds.length > 0 && (
        <button className="fx-kinds" data-act="show" title={`${kindsLabel(kinds)}: show in This post`}
          aria-label={`${kindsLabel(kinds)}: show in This post`} onClick={stop(toThisPost)}>
          {kinds.map(([k, n]) => (
            <span key={k} className="fx-kind" data-kind={k} title={kindLabel(k, n)}>
              <span className="fx-kind-mark" aria-hidden="true">{markOf(k)}</span>{n > 1 && <span className="fx-kind-n">{n}</span>}
            </span>
          ))}
          <span className="fx-kinds-go" aria-hidden="true">→</span>
        </button>
      )}
      {pics.length > 0 && (
        <span className="fx-plates" role="group" aria-label={`pictures in ${num}`}>
          {pics.slice(0, 4).map((p, i) => (
            <span key={p.ref + i} className="fx-plate" draggable={!selecting}
              /* DRAGGED OUT OF THE POST (D1): onto a zone it is kept there;
                 onto a composer it is attached, as Mentis already holds it. */
              onDragStart={(e) => {
                e.dataTransfer.setData('text/uri-list', new URL(`/api/artifacts/${p.ref}`, location.href).href)
                const o = objectsOf(post.id).find((x) => x.ref === p.ref || x.artifact?.ref === p.ref)
                if (o) e.dataTransfer.setData(DRAG, JSON.stringify({ address: o.address.live }))
                e.dataTransfer.effectAllowed = 'copyMove'
              }}>
              <button className="fx-plate-open" title={`${p.name}: open`} aria-label={`Open ${p.name}`}
                onClick={stop((e) => void openPic(p.ref, e.currentTarget))}>
                <img src={`/api/artifacts/${p.ref}`} alt="" loading="lazy" decoding="async" />
              </button>
              <button className="fx-plate-keep" title={`Keep ${p.name}: choose where it stays`} aria-label={`Keep ${p.name}`}
                onClick={stop((e) => void keepPic(p.ref, e.currentTarget))}>◆</button>
            </span>
          ))}
          {pics.length > 4 && (
            <button className="fx-plate-more" title={`${pics.length - 4} more pictures: open the post full screen`}
              onClick={stop(() => nav.openDetail({ kind: 'full', of: 'post', id: post.id, anchor: { kind: 'post', id: post.id }, mode: 'over' }))}>+{pics.length - 4}</button>
          )}
        </span>
      )}
      <button className="fx-keep-from" data-act="keep" title={`Open or keep what ${num} carries`} aria-label={`Open or keep what ${num} carries`}
        aria-expanded={!!menu} onClick={stop((e) => { want(post.id); setMenu(e.currentTarget) })}>◆</button>
      {menu && <Contents post={post} anchor={menu} readIn={readIn} onClose={() => setMenu(null)} />}
    </span>
  )
}

/** Everything the post carries, each with Open and ◆ Keep. */
function Contents({ post, anchor, onClose }: { post: Post; anchor: HTMLElement; readIn: Id; onClose: () => void }) {
  const listed = usePostObjects(post.id)
  const objs = listed ? objectsOf(post.id) : []
  const num = post.number != null ? `#${post.number}` : 'this post'
  return (
    <Sheet anchor={anchor} onClose={onClose} label={`what ${num} carries`}>
      <Sec>In {num}</Sec>
      {!listed && <p className="fx-faint fx-none">Reading what it carries…</p>}
      {listed && objs.length === 0 && <p className="fx-faint fx-none">{listed.why_not ?? 'Nothing here to keep apart from its words.'}</p>}
      {objs.map((o) => (
        <div key={o.address.live} className="fx-carried" data-object={o.address.live}>
          <Opt onPick={() => { onClose(); inspect(o.address.live, anchor) }}>
            <span className="fx-kind-mark" aria-hidden="true">{markOf(kindOf(o).chip ?? kindOf(o).word)}</span> {titleOf(o)}
          </Opt>
          <button className="fx-carried-keep" title={`Keep ${titleOf(o)}: choose where it stays`} aria-label={`Keep ${titleOf(o)}`}
            onClick={() => { onClose(); askKeep({ address: o.address.live }, anchor) }}>◆ Keep</button>
        </div>
      ))}
    </Sheet>
  )
}
