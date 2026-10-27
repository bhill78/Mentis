import { useCallback } from 'react'
import { useApi, type Id } from '../../api'
import AddSource from './AddSource'
import Collection from './Collection'
import Compare from './Compare'
import ObjectPage from './Object'
import Overview from './Overview'
import { readRoute, writeRoute, type SourcesAnswer, type SourcesRoute } from './route'
import './sources.css'

/* ------------------------------------------------------------------------ *
 * MANAGE SOURCES: MANAGED CENTRALLY, USED EVERYWHERE.
 *
 * Reached ONLY from the Brain menu -- Mentis ▾ → This Brain → Manage Sources
 * (U2). There is no Brain home band and no Conversation rail entry: material
 * is used from every Conversation through `#` references, and it is managed
 * here, in one place.
 *
 * Every movement inside it is a Place with an address (`#/brain/sources/…`),
 * so Back returns to wherever you came from -- including the Conversation a
 * reference chip was opened from.
 * ------------------------------------------------------------------------ */

export default function SourcesSurface({
  path,
  me,
  nameOf,
  onGo,
  onChanged,
}: {
  /** the part of the address after `sources/` */
  path: string
  me: Id | null
  nameOf: (id: Id | null | undefined) => string
  onGo: (path: string) => void
  onChanged: () => void
}) {
  const route = readRoute(path)
  const go = useCallback((r: SourcesRoute) => onGo(writeRoute(r)), [onGo])
  const all = useApi<SourcesAnswer>('/api/sources')
  const changed = () => {
    all.reload()
    onChanged()
  }
  const descriptors = all.data?.descriptors ?? []

  const crumb = (
    <nav className="src-crumb" aria-label="where in Manage Sources">
      <button className="link" onClick={() => go({ at: 'overview' })} disabled={route.at === 'overview'}>
        Manage Sources
      </button>
      {route.at !== 'overview' && <span aria-hidden="true"> › </span>}
      {route.at === 'add' && <span>Add a source</span>}
      {route.at === 'flow' && (
        <>
          <button className="link" onClick={() => go({ at: 'add' })}>
            Add a source
          </button>
          <span aria-hidden="true"> › </span>
          <span>{descriptors.find((d) => d.id === route.connector)?.label ?? route.connector}</span>
        </>
      )}
      {(route.at === 'collection' || route.at === 'object') && (
        <button className="link" onClick={() => go({ at: 'collection', col: route.col, tab: 'overview' })}>
          {all.data?.collections.find((c) => c.collection === route.col)?.name ?? route.col}
        </button>
      )}
      {route.at === 'object' && (
        <>
          <span aria-hidden="true"> › </span>
          <span className="src-mono">{route.key}</span>
        </>
      )}
      {route.at === 'observation' && <span>an observation</span>}
      {route.at === 'compare' && <span>comparing two observations</span>}
    </nav>
  )

  if (all.error && !all.data) return <p className="act-refused">{all.error}</p>
  if (!all.data) return <p className="src-faint">reading the record…</p>

  let body: React.ReactNode
  switch (route.at) {
    case 'overview':
      body = <Overview data={all.data} go={go} />
      break
    case 'add':
    case 'flow':
      body = <AddSource descriptors={descriptors} connector={route.at === 'flow' ? route.connector : undefined} picker={all.data.picker} me={me} go={go} onChanged={changed} />
      break
    case 'collection':
      body = (
        <Collection
          key={route.col}
          col={route.col}
          tab={route.tab}
          descriptors={descriptors}
          me={me}
          nameOf={nameOf}
          go={go}
          onChanged={changed}
        />
      )
      break
    case 'object':
      body = <ObjectPage key={route.col + route.key} col={route.col} objectKey={route.key} go={go} />
      break
    case 'observation':
      body = (
        <ObjectPage
          key={route.ref + (route.extraction ? `~${route.extraction}` : '') + (route.span ? `@${route.span.offset}-${route.span.end}` : '')}
          pinned={route.ref}
          span={route.span}
          extraction={route.extraction}
          go={go}
        />
      )
      break
    case 'compare':
      body = <Compare a={route.a} b={route.b} go={go} />
      break
  }
  return (
    <div className="src-surface">
      {crumb}
      {body}
    </div>
  )
}
