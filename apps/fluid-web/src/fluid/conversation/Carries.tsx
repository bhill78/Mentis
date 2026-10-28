/* Rich-content discovery where the reader already is: the post card. */
import { useEffect, useMemo, useRef, useState } from 'react'
import { act } from '../objects/actions'
import { ObjectActions } from '../objects/ObjectActions'
import { store, type Id, type Post, type PostObjectEntry } from '../store'
import { usePostObjects } from './hooks'
import { kindOf } from '../../experimental/objectkinds'
import { Sec, Sheet } from '../frame/Sheet'
import { navigatorIndex, objectRow, type DiscoveryRow } from './discovery'
import { kindsLabel } from './text'

const MARK: Record<string, string> = {
  table: '▦', chart: '▥', checklist: '☑', diagram: '◇', timeline: '┄', image: '▣', doc: '¶', note: '✎',
  reference: '↗', file: '▤', video: '▶', audio: '♪', panel: '▣', text: '¶', link: '⛓',
}
const markOf = (k: string) => MARK[k] ?? '▤'
const PICTURE = /\.(png|jpe?g|gif|webp|svg)$/i

export function picturesOf(post: Post): { ref: string; name: string }[] {
  return post.parts
    .filter((p) => p.ref && p.type !== 'text' && !['turn', 'topic', 'conversation', 'acquired'].includes(p.type))
    .filter((p) => p.type === 'image' || String((p as { media_type?: string }).media_type ?? '').startsWith('image/') || PICTURE.test(String(p.name ?? '')))
    .map((p) => ({ ref: String(p.ref), name: String(p.alt ?? p.name ?? 'picture') }))
}

function objectsOf(post: Id): PostObjectEntry[] {
  return (store.postObjects.get(post)?.addresses ?? []).flatMap((a) => {
    const st = store.objects.get(a)
    return st && 'object' in st && st.object.parent === null && st.object.kind !== 'post-text' ? [st.object] : []
  })
}

function rowsOf(posts: Id[]): DiscoveryRow[] {
  return posts.flatMap((id) => {
    const p = store.posts.get(id)
    return objectsOf(id).map((o) => objectRow(o, p?.number ?? null, p?.reply_to_number ?? null))
  })
}

function Line({ row, siblings, fresh }: { row: DiscoveryRow; siblings: string[]; fresh?: boolean }) {
  const ref = useRef<HTMLDivElement | null>(null)
  const timer = useRef<number | null>(null)
  const post = store.posts.get(row.post)
  const state = store.objects.get(row.address)
  const object = state && 'object' in state ? state.object : null
  const image = !!object && kindOf(object).filter === 'image' && !!(object.artifact?.url ?? object.ref)
  const target = {
    address: row.address, title: row.title, kind: row.kind,
    from: `#${row.number ?? '?'}${row.replyTo != null ? ` · reply to #${row.replyTo}` : ''}`,
    siblings, anchor: ref.current,
  }
  const cancel = () => { if (timer.current !== null) window.clearTimeout(timer.current); timer.current = null }
  const later = () => { cancel(); timer.current = window.setTimeout(() => act.peek({ ...target, anchor: ref.current }), 280) }
  useEffect(() => cancel, [])
  return (
    <div ref={ref} className={'fx-object-line' + (fresh ? ' new' : '')} data-address={row.address}
      onPointerEnter={later} onPointerLeave={cancel} onFocus={later} onBlur={cancel}
      onKeyDown={(e) => {
        const lines = [...(e.currentTarget.closest('.fx-object-list')?.querySelectorAll<HTMLElement>('.fx-object-line') ?? [])]
        const next = navigatorIndex(lines.indexOf(e.currentTarget), e.key, lines.length)
        if (next !== null) { e.preventDefault(); lines[next]?.focus() }
        if (e.key === 'Enter' && e.target === e.currentTarget) { e.preventDefault(); cancel(); act.peek({ ...target, anchor: ref.current }) }
      }} tabIndex={0} role="listitem">
      <button className={'fx-object-open' + (image ? ' plate' : '')}
        onClick={(e) => { e.stopPropagation(); cancel(); act.peek({ ...target, anchor: e.currentTarget }) }}>
        {image ? <img src={object!.artifact?.url ?? `/api/artifacts/${object!.ref}`} alt="" loading="lazy" />
          : <span className="fx-kind-mark" aria-hidden="true">{markOf(row.kind)}</span>}
        <span className="fx-object-from">#{row.number ?? '?'} · {post?.author_name?.replace(/^@/, '') ?? 'someone'}</span>
        <span aria-hidden="true">—</span><span className="fx-object-title">{row.title}</span>
        {fresh && <span className="fx-object-new">new</span>}
      </button>
      <ObjectActions target={target} compact />
    </div>
  )
}

export function ObjectList({ rows, fresh = [] }: { rows: DiscoveryRow[]; fresh?: string[] }) {
  const siblings = rows.map((r) => r.address)
  return <div className="fx-object-list" role="list">{rows.map((r) => <Line key={r.address} row={r} siblings={siblings} fresh={fresh.includes(r.address)} />)}</div>
}

/** A reply card's own objects, with Peek still stepping through the thread. */
export function ReplyObjectStrip({ post, thread }: { post: Post; thread: Id }) {
  const listed = usePostObjects(post.id)
  const [, redraw] = useState(0)
  useEffect(() => {
    void Promise.all([store.loadObjects(post.id), store.loadThreadObjects(thread)])
      .then(() => redraw((x) => x + 1)).catch(() => {})
  }, [post.id, thread])
  if (!listed) return null
  const rows = rowsOf([post.id])
  if (!rows.length) return null
  const threadRows = rowsOf(store.threadObjects.get(thread)?.posts ?? [post.id])
  const siblings = threadRows.length ? threadRows.map((r) => r.address) : rows.map((r) => r.address)
  return <div className="fx-reply-objects" aria-label={`What #${post.number ?? ''} carries`}>
    <div className="fx-object-list" role="list">{rows.map((r) => <Line key={r.address} row={r} siblings={siblings} />)}</div>
  </div>
}

export default function Carries({ post, kinds, selecting }: {
  post: Post; kinds: [string, number][]; readIn: Id; selecting: boolean; onRead: () => void
}) {
  const [open, setOpen] = useState(false)
  const [menu, setMenu] = useState<HTMLElement | null>(null)
  const [generation, redraw] = useState(0)
  const listing = store.threadObjects.get(post.id)
  const load = () => void store.loadThreadObjects(post.id).then(() => redraw((x) => x + 1)).catch(() => {})
  const rows = useMemo(() => rowsOf(listing?.posts ?? []), [listing, generation])
  if (!kinds.length && !picturesOf(post).length) return null
  const stop = (fn: (e: React.MouseEvent<HTMLElement>) => void) => (e: React.MouseEvent<HTMLElement>) => { e.stopPropagation(); if (!selecting) fn(e) }
  const label = kindsLabel(kinds)
  return (
    <span className="fx-carries" onPointerEnter={load} onFocus={load}>
      {kinds.length > 0 && <button className="fx-kinds" data-act="show" aria-expanded={open}
        title={`${label}: ${open ? 'fold' : 'show in this card'}`} aria-label={`${label}, in this thread`}
        onClick={stop(() => { load(); setOpen((x) => !x) })}>
        {kinds.map(([k, n]) => <span key={k} className="fx-kind" data-kind={k}><span className="fx-kind-mark" aria-hidden="true">{markOf(k)}</span>{n > 1 && <span className="fx-kind-n">{n}</span>}</span>)}
        <span className="fx-kinds-what">in this thread</span><span aria-hidden="true">{open ? '▴' : '▾'}</span>
      </button>}
      <button className="fx-keep-from" data-act="keep" title="What this thread carries" aria-label="What this thread carries"
        aria-expanded={!!menu} onClick={stop((e) => { load(); setMenu(e.currentTarget) })}>◆</button>
      {open && <span className="fx-thread-nav" aria-label={`In this thread, #${post.number ?? ''}`}>
        <span className="fx-thread-nav-head"><b>In this thread</b><span>hover to Peek · arrows move</span></span>
        {!listing ? <span className="fx-faint">Reading…</span> : rows.length ? <ObjectList rows={rows} /> : <span className="fx-faint">Nothing here to keep apart from its words.</span>}
        {!!listing?.omitted && <span className="fx-faint fx-thread-omitted">{listing.omitted} older {listing.omitted === 1 ? 'reply is' : 'replies are'} not shown.</span>}
      </span>}
      {menu && <Sheet anchor={menu} onClose={() => setMenu(null)} label="what this thread carries">
        <Sec>In this thread</Sec>
        {!listing ? <p className="fx-faint">Reading…</p> : rows.length ? <ObjectList rows={rows} /> : <p className="fx-faint">Nothing here to keep apart from its words.</p>}
        {!!listing?.omitted && <p className="fx-faint">{listing.omitted} older replies are not shown.</p>}
      </Sheet>}
    </span>
  )
}
