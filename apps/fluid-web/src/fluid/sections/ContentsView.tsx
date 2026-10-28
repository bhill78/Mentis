import { useEffect, useRef, useState, type ReactNode } from 'react'
import { store } from '../store'
import { useConversationObjects, useNav } from '../conversation/hooks'
import type { SectionBodyProps } from './registry'
import { ObjectActions } from '../objects/ObjectActions'
import { act } from '../objects/actions'
import ObjectBody from '../workspace/ObjectBody'
import { kindOf } from '../../experimental/objectkinds'
import { defaultContentsScope, groupDiscovery, limitDiscoveryGroup, postSubtree, summaryRow, type DiscoveryRow } from '../conversation/discovery'
import { setGrouping, useGrouping } from '../present/Grouped'
import { shows, type Show } from '../workspace/hooks'
import { IconMenu, type IconGroup } from '../frame/IconMenu'
import { Sheet } from '../frame/Sheet'
import { SearchButton, useFocusSearch } from '../search-in/FocusSearch'

type ContentsShow = 'objects' | 'media' | 'files' | 'forms' | 'charts'
const CONTENT_SHOWS: { key: ContentsShow; label: string; icon: string; says: string }[] = [
  { key: 'objects', label: 'All', icon: '◫', says: 'Show every object in this scope' },
  { key: 'media', label: 'Media', icon: '▧', says: 'Show pictures, video and sound' },
  { key: 'files', label: 'Files', icon: '▤', says: 'Show files and documents' },
  { key: 'forms', label: 'Forms', icon: '☑', says: 'Show forms and things to fill in' },
  { key: 'charts', label: 'Charts', icon: '▥', says: 'Show charts and visualisations' },
]

const kindMatches = (row: DiscoveryRow, show: ContentsShow): boolean => {
  if (show === 'objects') return true
  const state = store.objects.get(row.address)
  if (show !== 'charts' && state && 'object' in state && shows(state.object, show as Show)) return true
  const kind = row.kind.toLowerCase()
  if (show === 'media') return /image|picture|video|audio|youtube|media/.test(kind)
  if (show === 'files') return /file|document|pdf|code|data|sheet/.test(kind)
  if (show === 'forms') return /form|checklist|input|decision/.test(kind)
  return /chart|graph|plot|diagram|visual/.test(kind)
}

function MenuControl({ label, icon, says, groups }: { label: string; icon: ReactNode; says: string; groups: IconGroup[] }) {
  const [anchor, setAnchor] = useState<HTMLElement | null>(null)
  return <>
    <button type="button" className="fx-contents-control" aria-expanded={!!anchor} title={says}
      onClick={(e) => setAnchor((at) => at ? null : e.currentTarget)}>
      <span aria-hidden="true">{icon}</span><span>{label}</span><span className="fx-contents-caret" aria-hidden="true">▾</span>
    </button>
    {anchor && <Sheet anchor={anchor} onClose={() => setAnchor(null)} label={says} className="fx-contents-menu">
      <IconMenu label={says} groups={groups} onDone={() => setAnchor(null)} />
    </Sheet>}
  </>
}

function ContentsObject({ row, siblings, fresh, reading }: { row: DiscoveryRow; siblings: string[]; fresh: boolean; reading: boolean }) {
  const state = store.objects.get(row.address)
  const o = state && 'object' in state ? state.object : null
  const is = o ? kindOf(o) : null
  const url = o?.artifact?.url ?? (o?.ref ? `/api/artifacts/${o.ref}` : null)
  const target = { address: row.address, title: row.title, kind: row.kind,
    from: `from #${row.number ?? '?'}${row.replyTo != null ? ` · reply to #${row.replyTo}` : ''}`, siblings }
  return <div className={'fx-content-object' + (reading ? ' reading' : '')} data-address={row.address} data-post={row.post}>
    <button className="fx-content-preview" title={`Open ${row.title}: its details`} onClick={(e) => act.open({ ...target, anchor: e.currentTarget })}>
      {o && is?.filter === 'image' && url ? <img src={url} alt="" loading="lazy" />
        : o && (o.kind === 'block' || o.kind === 'figure') ? <span className="turn-body"><ObjectBody o={o} size="compact" /></span>
          : <span className="fx-content-plate"><b>{row.kind}</b><span>{row.title}</span></span>}
    </button>
    <div className="fx-content-meta">
      <span><b>{row.title}</b>{fresh && <span className="fx-object-new"> new</span>}</span>
      <span className="fx-faint">from #{row.number ?? '?'}{row.replyTo != null ? ` · reply to #${row.replyTo}` : ''}</span>
    </div>
    <ObjectActions target={target} compact />
  </div>
}

export default function ContentsView({ conversation, options, setOption, chrome, z }: SectionBodyProps) {
  const held = useConversationObjects(conversation ?? '')
  const reading = useNav().reading
  const grouping = useGrouping(z.id) === 'reply' ? 'reply' : 'kind'
  const show = (CONTENT_SHOWS.some((x) => x.key === options.show) ? options.show : 'objects') as ContentsShow
  const scope = defaultContentsScope(options.scope, held?.objects.length ?? 0)
  const body = useRef<HTMLDivElement | null>(null)
  const search = useFocusSearch(() => body.current, undefined, `${z.id}:contents`)
  const [collapsed, setCollapsed] = useState<Set<string>>(() => new Set())
  const [expanded, setExpanded] = useState<{ key: string; page: number } | null>(null)
  const [groupPage, setGroupPage] = useState(0)
  useEffect(() => { if (conversation) void store.loadConversationObjects(conversation).catch(() => {}) }, [conversation])
  useEffect(() => {
    if (held && options.scope === 'auto') setOption('scope', defaultContentsScope('auto', held.objects.length))
  }, [held, options.scope, setOption])
  if (!conversation) return null
  if (!held) return chrome({ children: <p className="fx-faint">Reading contents…</p> })

  const subtree = scope === 'post' ? postSubtree(reading, held.posts, (post) => store.posts.get(post)?.reply_to) : null
  const scoped = held.objects.map(summaryRow).filter((row) => !subtree || subtree.has(row.post))
  const counts = Object.fromEntries(CONTENT_SHOWS.map((f) => [f.key, scoped.filter((row) => kindMatches(row, f.key)).length]))
  const rows = scoped.filter((row) => kindMatches(row, show))
  const groups = grouping === 'reply'
    ? groupDiscovery(rows, held.posts).map((g) => ({ key: g.post, label: (() => {
        const p = store.posts.get(g.post)
        return `#${p?.number ?? '?'}${p?.reply_to_number != null ? ` · reply to #${p.reply_to_number}` : ''}`
      })(), items: g.items }))
    : [...new Set(rows.map((r) => r.kind))].map((kind) => ({ key: kind, label: kind, items: rows.filter((r) => r.kind === kind) }))
  const siblings = rows.map((r) => r.address)
  const selected = reading ? store.posts.get(reading) : null
  const caption = scope === 'post'
    ? `${selected?.number != null ? `#${selected.number}` : 'This post'} and its replies · ${rows.length}`
    : `Conversation · ${rows.length}`
  const scopeGroups: IconGroup[] = [{ title: 'Scope', items: [
    { id: 'post', icon: '▣', label: 'This post', says: 'Show the selected post and all of its replies', on: scope === 'post', onPick: () => setOption('scope', 'post') },
    { id: 'conversation', icon: '▦', label: 'Conversation', says: 'Show objects from the whole conversation', on: scope === 'conversation', onPick: () => setOption('scope', 'conversation') },
  ] }]
  const groupingGroups: IconGroup[] = [{ title: 'Group', items: [
    { id: 'reply', icon: '↳', label: 'By reply', says: 'Group objects under the post or reply they came from', on: grouping === 'reply', onPick: () => setGrouping(z.id, 'reply') },
    { id: 'kind', icon: '▦', label: 'By kind', says: 'Group objects by their kind', on: grouping === 'kind', onPick: () => setGrouping(z.id, 'kind') },
  ] }]
  const kindGroups: IconGroup[] = [{ title: 'Kind', items: CONTENT_SHOWS.map((f) => ({
    id: f.key, icon: f.icon, label: `${f.label} ${counts[f.key]}`, says: `${f.says} (${counts[f.key]})`, on: show === f.key,
    onPick: () => setOption('show', f.key),
  })) }]
  const groupPages = Math.max(1, Math.ceil(groups.length / 6))
  const atGroupPage = Math.min(groupPage, groupPages - 1)
  const visibleGroups = groups.slice(atGroupPage * 6, (atGroupPage + 1) * 6)

  return chrome({
    filters: <div className="fx-contents-toolbar" role="toolbar" aria-label="Contents controls">
      <MenuControl label={scope === 'post' ? 'This post' : 'Conversation'} icon={scope === 'post' ? '▣' : '▦'} says="Choose which posts Contents follows" groups={scopeGroups} />
      <MenuControl label={grouping === 'reply' ? 'By reply' : 'By kind'} icon={grouping === 'reply' ? '↳' : '▦'} says="Choose how Contents is grouped" groups={groupingGroups} />
      <MenuControl label={`${CONTENT_SHOWS.find((f) => f.key === show)?.label ?? 'All'} ${counts[show]}`} icon={CONTENT_SHOWS.find((f) => f.key === show)?.icon ?? '◫'} says="Filter Contents by kind" groups={kindGroups} />
      <SearchButton className="fx-contents-search" onOpen={() => search.setOpen(true)} label="Focus Search in Contents" />
      <span className="fx-contents-caption" aria-live="polite">{caption}</span>
    </div>,
    children: <div className="fx-contents" ref={body}>
      {search.bar}
      {scope === 'post' && !reading && <p className="fx-faint">No post is selected.{' '}<button className="fx-linkish" onClick={() => setOption('scope', 'conversation')}>Show the conversation</button></p>}
      {visibleGroups.map((group) => {
        const isCollapsed = collapsed.has(group.key)
        const page = expanded?.key === group.key ? expanded.page : undefined
        const limited = limitDiscoveryGroup(group.items, page !== undefined, page ?? 0, 8)
        return <section key={group.key} className={'fx-content-group' + (isCollapsed ? ' collapsed' : '')}>
          <h4><button type="button" aria-expanded={!isCollapsed} onClick={() => {
            setCollapsed((old) => { const next = new Set(old); if (next.has(group.key)) next.delete(group.key); else next.add(group.key); return next })
            if (!isCollapsed && expanded?.key === group.key) setExpanded(null)
          }}><span aria-hidden="true">{isCollapsed ? '▸' : '▾'}</span> {group.label} <span className="fx-faint">· {group.items.length}</span></button></h4>
          {!isCollapsed && limited.shown.map((row) => <ContentsObject key={row.address} row={row} siblings={siblings} fresh={held.fresh.includes(row.address)} reading={reading === row.post} />)}
          {!isCollapsed && page === undefined && limited.hidden > 0 && <button type="button" className="fx-content-more" onClick={() => setExpanded({ key: group.key, page: 0 })}>Show all {group.items.length}</button>}
          {!isCollapsed && page !== undefined && limited.pages > 1 && <div className="fx-content-pages">
            <button type="button" disabled={limited.page === 0} onClick={() => setExpanded({ key: group.key, page: limited.page - 1 })}>Previous</button>
            <span>{limited.page + 1} of {limited.pages}</span>
            <button type="button" disabled={limited.page + 1 === limited.pages} onClick={() => setExpanded({ key: group.key, page: limited.page + 1 })}>Next</button>
            <button type="button" onClick={() => setExpanded(null)}>Collapse</button>
          </div>}
        </section>
      })}
      {groupPages > 1 && <div className="fx-content-pages"><button type="button" disabled={atGroupPage === 0} onClick={() => setGroupPage(atGroupPage - 1)}>Previous groups</button><span>{atGroupPage + 1} of {groupPages}</span><button type="button" disabled={atGroupPage + 1 === groupPages} onClick={() => setGroupPage(atGroupPage + 1)}>Next groups</button></div>}
      {!rows.length && !(scope === 'post' && !reading) && <p className="fx-faint">No objects match this filter.</p>}
    </div>,
  })
}
