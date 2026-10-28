import { useEffect } from 'react'
import { store } from '../store'
import { useConversationObjects, useNav } from '../conversation/hooks'
import type { SectionBodyProps } from './registry'
import { Filters } from './shared'
import { ObjectActions } from '../objects/ObjectActions'
import { act } from '../objects/actions'
import ObjectBody from '../workspace/ObjectBody'
import { kindOf } from '../../experimental/objectkinds'
import { groupDiscovery, summaryRow, type DiscoveryRow } from '../conversation/discovery'
import { setGrouping, useGrouping } from '../present/Grouped'
import { shows, type Show } from '../workspace/hooks'

type ContentsShow = 'objects' | 'media' | 'files' | 'forms'
const CONTENT_SHOWS: { key: ContentsShow; label: string }[] = [
  { key: 'objects', label: 'All' }, { key: 'media', label: 'Media' },
  { key: 'files', label: 'Files' }, { key: 'forms', label: 'Forms' },
]

function ContentsObject({ row, siblings, fresh, reading }: { row: DiscoveryRow; siblings: string[]; fresh: boolean; reading: boolean }) {
  const state = store.objects.get(row.address)
  const o = state && 'object' in state ? state.object : null
  const is = o ? kindOf(o) : null
  const url = o?.artifact?.url ?? (o?.ref ? `/api/artifacts/${o.ref}` : null)
  const target = { address: row.address, title: row.title, kind: row.kind,
    from: `from #${row.number ?? '?'}${row.replyTo != null ? ` · reply to #${row.replyTo}` : ''}`, siblings }
  return (
    <div className={'fx-content-object' + (reading ? ' reading' : '')} data-address={row.address} data-post={row.post}>
      {/* a click on the object opens it (◨ Open, its detail); ◱ in its row Peeks */}
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
  )
}

export default function ContentsView({ conversation, options, setOption, chrome, z }: SectionBodyProps) {
  const held = useConversationObjects(conversation ?? '')
  const reading = useNav().reading
  const grouping = useGrouping(z.id) === 'reply' ? 'reply' : 'kind'
  const show = (CONTENT_SHOWS.some((x) => x.key === options.show) ? options.show : 'objects') as ContentsShow
  useEffect(() => { if (conversation) void store.loadConversationObjects(conversation).catch(() => {}) }, [conversation])
  if (!conversation) return null
  if (!held) return chrome({ children: <p className="fx-faint">Reading contents…</p> })
  const rows = held.objects.map(summaryRow).filter((row) => {
    const st = store.objects.get(row.address)
    return show === 'objects' || (!!st && 'object' in st && shows(st.object, show as Show))
  })
  const groups = grouping === 'reply'
    ? groupDiscovery(rows, held.posts).map((g) => ({ key: g.post, label: (() => {
        const p = store.posts.get(g.post)
        return `#${p?.number ?? '?'}${p?.reply_to_number != null ? ` · reply to #${p.reply_to_number}` : ''}`
      })(), items: g.items }))
    : [...new Set(rows.map((r) => r.kind))].map((kind) => ({ key: kind, label: kind, items: rows.filter((r) => r.kind === kind) }))
  const siblings = rows.map((r) => r.address)
  return chrome({
    filters: <>
      <Filters label="How to group contents" className="fx-contents-group" value={grouping}
        items={[{ key: 'reply' as const, label: 'By reply' }, { key: 'kind' as const, label: 'By kind' }]}
        onPick={(g) => setGrouping(z.id, g)} />
      <Filters label="What contents to show" className="fx-contents-show" value={show} items={CONTENT_SHOWS}
        onPick={(value) => setOption('show', value)} />
    </>,
    children: <div className="fx-contents">
      {groups.map((group) => <section key={group.key} className="fx-content-group"><h4>{group.label} <span className="fx-faint">· {group.items.length}</span></h4>
        {group.items.map((row) => <ContentsObject key={row.address} row={row} siblings={siblings}
          fresh={held.fresh.includes(row.address)} reading={reading === row.post} />)}
      </section>)}
      {!rows.length && <p className="fx-faint">No objects match this Show filter.</p>}
    </div>,
  })
}
