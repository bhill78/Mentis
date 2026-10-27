import type React from 'react'
import { useEffect, useRef, useState } from 'react'
import { qs, read, type Id } from '../../api'
import ContentSearch from './ContentSearch'
import { bytes, count, type ObjectRow, type Span } from './route'

/* ------------------------------------------------------------------------ *
 * BROWSE (U7): a projection the CONNECTOR supplies, over the latest recorded
 * observations. Never the live source.
 *
 * Only `hierarchy` is built -- a tree from the key's `/` segments, which is
 * what a folder is. A Slack channel › thread, a Jira project › issue or an
 * RSS chronology would each be one more branch here, keyed on the
 * descriptor's `browse`; until a connector brings one, it says so.
 *
 * NAME OR CONTENTS (Sources A, A2). The filter matches names, as before; the
 * switch beside it searches inside the acquired text instead
 * (`ContentSearch`), which says what it could not search.
 * ------------------------------------------------------------------------ */

export interface FolderEntry {
  name: string
  path: string
  count: number
}

export interface PageResult {
  objects: ObjectRow[]
  folders?: FolderEntry[]
  prefix?: string
  matched: number
  next_offset: number | null
}

export default function Browse({
  col,
  browse,
  onOpen,
  onHit,
}: {
  col: Id
  browse: string
  onOpen: (key: string) => void
  onHit: (ref: Id, span: Span, extraction?: string) => void
}) {
  const [by, setBy] = useState<'name' | 'contents'>('name')
  const toggle = (
    <span className="src-view-toggle" role="group" aria-label="search by">
      <button className={'btn quiet' + (by === 'name' ? ' on' : '')} aria-pressed={by === 'name'} onClick={() => setBy('name')}>
        Names
      </button>
      <button
        className={'btn quiet' + (by === 'contents' ? ' on' : '')}
        aria-pressed={by === 'contents'}
        onClick={() => setBy('contents')}
      >
        Contents
      </button>
    </span>
  )
  if (by === 'contents')
    return (
      <div className="src-browse">
        {toggle}
        <ContentSearch col={col} onHit={onHit} />
      </div>
    )
  return <ByName col={col} browse={browse} onOpen={onOpen} toggle={toggle} />
}

export function ByName({
  col,
  browse,
  onOpen,
  toggle,
}: {
  col: Id
  browse: string
  onOpen: (key: string) => void
  toggle: React.ReactNode
}) {
  const [q, setQ] = useState('')
  const [debouncedQ, setDebouncedQ] = useState('')
  const [state, setState] = useState<'present' | 'absent' | ''>('present')
  const [openPaths, setOpenPaths] = useState<Set<string>>(() => new Set())

  // R3: debounce filter input and avoid re-reading every open folder on each keystroke
  useEffect(() => {
    if (!q.trim()) {
      setDebouncedQ('')
      return
    }
    const timer = setTimeout(() => {
      setDebouncedQ(q)
    }, 150)
    return () => clearTimeout(timer)
  }, [q])

  // R2: changing the filter or the state must not collapse folders the user opened
  const handleToggle = (dirPath: string) => {
    setOpenPaths((prev) => {
      const next = new Set(prev)
      if (next.has(dirPath)) {
        next.delete(dirPath)
      } else {
        next.add(dirPath)
      }
      return next
    })
  }

  if (browse !== 'hierarchy')
    return <p className="src-note">This connector's {browse} view arrives with the connector. Nothing to browse yet.</p>

  const isFiltered = !!debouncedQ.trim()

  return (
    <div className="src-browse">
      {toggle}
      <div className="src-browse-bar">
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="filter by name" aria-label="filter by name" />
        <select value={state} onChange={(e) => setState(e.target.value as typeof state)} aria-label="state">
          <option value="present">present</option>
          <option value="absent">recorded absent</option>
          <option value="">every state</option>
        </select>
        <span className="src-faint">the folder projection; secondary · past observations, not the live folder</span>
      </div>
      {isFiltered ? (
        <FlatSearch col={col} q={debouncedQ} state={state} onOpen={onOpen} />
      ) : (
        <div className="src-tree">
          <Dir
            col={col}
            path=""
            name=""
            depth={0}
            initiallyOpen={true}
            state={state}
            openPaths={openPaths}
            onToggle={handleToggle}
            onOpen={onOpen}
          />
        </div>
      )}
    </div>
  )
}

// R1: while a text filter is active, show every match without manual expansion via flat objects(q=...)
export function FlatSearch({
  col,
  q,
  state,
  onOpen,
}: {
  col: Id
  q: string
  state: 'present' | 'absent' | ''
  onOpen: (key: string) => void
}) {
  const [files, setFiles] = useState<ObjectRow[] | null>(null)
  const [nextOffset, setNextOffset] = useState<number | null>(null)
  const [loading, setLoading] = useState(false)
  const [loadingMore, setLoadingMore] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const versionRef = useRef(0)

  useEffect(() => {
    let live = true
    const currentVersion = ++versionRef.current
    setLoading(true)
    // N1: a page still in flight for the superseded listing is discarded (R4), so it never clears this
    setLoadingMore(false)
    setError(null)
    setFiles(null)
    setNextOffset(null)

    ;(async () => {
      try {
        const page: PageResult = await read(
          `/api/sources/${encodeURIComponent(col)}/objects` +
            qs({ state, q: q.trim() || undefined, offset: 0, limit: 200 }),
        )
        if (live && versionRef.current === currentVersion) {
          setFiles(page.objects || [])
          setNextOffset(page.next_offset)
          setLoading(false)
        }
      } catch (e) {
        if (live && versionRef.current === currentVersion) {
          setError((e as Error).message)
          setLoading(false)
        }
      }
    })()

    return () => {
      live = false
    }
  }, [col, state, q])

  // R4: discard responses that belong to a superseded filter/state
  async function loadMore() {
    if (nextOffset === null || loadingMore) return
    const currentVersion = versionRef.current
    setLoadingMore(true)
    try {
      const page: PageResult = await read(
        `/api/sources/${encodeURIComponent(col)}/objects` +
          qs({ state, q: q.trim() || undefined, offset: nextOffset, limit: 200 }),
      )
      if (versionRef.current !== currentVersion) return
      setFiles((prev) => [...(prev || []), ...(page.objects || [])])
      setNextOffset(page.next_offset)
    } catch (e) {
      if (versionRef.current === currentVersion) {
        setError((e as Error).message)
      }
    } finally {
      if (versionRef.current === currentVersion) {
        setLoadingMore(false)
      }
    }
  }

  const isEmpty = !loading && !error && files !== null && files.length === 0

  return (
    <div className="src-tree">
      {loading && <p className="src-faint">reading the record…</p>}
      {error && <p className="act-refused">{error}</p>}
      {files &&
        files.map((f) => (
          <button key={f.key} className="src-file" onClick={() => onOpen(f.key)}>
            {f.label && f.label !== f.key ? f.label : f.key}{' '}
            <span className="src-faint">
              · {bytes(f.size)}
              {f.state !== 'present' ? ` · ${f.state}` : ''}
            </span>
          </button>
        ))}
      {nextOffset !== null && (
        <button className="btn quiet src-more" disabled={loadingMore} onClick={loadMore}>
          {loadingMore ? 'reading…' : 'more files…'}
        </button>
      )}
      {isEmpty && <p className="src-faint">nothing matches</p>}
    </div>
  )
}

export function Dir({
  col,
  path,
  name,
  count: dirCount,
  depth,
  initiallyOpen,
  state,
  q,
  openPaths,
  onToggle,
  onOpen,
}: {
  col: Id
  path: string
  name: string
  count?: number
  depth: number
  initiallyOpen?: boolean
  state: 'present' | 'absent' | ''
  q?: string
  openPaths?: Set<string>
  onToggle?: (path: string) => void
  onOpen: (key: string) => void
}) {
  const [localOpen, setLocalOpen] = useState(!!initiallyOpen)
  const isOpen = depth === 0 ? true : openPaths !== undefined ? openPaths.has(path) : localOpen
  const [folders, setFolders] = useState<FolderEntry[] | null>(null)
  const [files, setFiles] = useState<ObjectRow[] | null>(null)
  const [nextOffset, setNextOffset] = useState<number | null>(null)
  const [loading, setLoading] = useState(false)
  const [loadingMore, setLoadingMore] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const versionRef = useRef(0)

  const handleToggle = () => {
    if (onToggle) {
      onToggle(path)
    } else {
      setLocalOpen(!localOpen)
    }
  }

  useEffect(() => {
    if (!isOpen) return
    let live = true
    const currentVersion = ++versionRef.current
    setLoading(true)
    // N1: a page still in flight for the superseded listing is discarded (R4), so it never clears this
    setLoadingMore(false)
    setError(null)
    setFolders(null)
    setFiles(null)
    setNextOffset(null)

    ;(async () => {
      try {
        const page: PageResult = await read(
          `/api/sources/${encodeURIComponent(col)}/objects` +
            qs({ state, prefix: path || '/', q: q?.trim() || undefined, offset: 0, limit: 200 }),
        )
        if (live && versionRef.current === currentVersion) {
          setFolders(page.folders || [])
          setFiles(page.objects || [])
          setNextOffset(page.next_offset)
          setLoading(false)
        }
      } catch (e) {
        if (live && versionRef.current === currentVersion) {
          setError((e as Error).message)
          setLoading(false)
        }
      }
    })()

    return () => {
      live = false
    }
  }, [col, path, state, q, isOpen])

  // R4: discard responses that belong to a superseded filter/state
  async function loadMore() {
    if (nextOffset === null || loadingMore) return
    const currentVersion = versionRef.current
    setLoadingMore(true)
    try {
      const page: PageResult = await read(
        `/api/sources/${encodeURIComponent(col)}/objects` +
          qs({ state, prefix: path || '/', q: q?.trim() || undefined, offset: nextOffset, limit: 200 }),
      )
      if (versionRef.current !== currentVersion) return
      setFiles((prev) => [...(prev || []), ...(page.objects || [])])
      setNextOffset(page.next_offset)
    } catch (e) {
      if (versionRef.current === currentVersion) {
        setError((e as Error).message)
      }
    } finally {
      if (versionRef.current === currentVersion) {
        setLoadingMore(false)
      }
    }
  }

  const isEmpty =
    depth === 0 &&
    !loading &&
    !error &&
    folders !== null &&
    files !== null &&
    folders.length === 0 &&
    files.length === 0

  // R5: order folders as the old Browse did (same collation as before), not raw code points
  const sortedFolders = folders ? [...folders].sort((a, b) => a.name.localeCompare(b.name)) : null

  return (
    <div className="src-dir">
      {depth > 0 && (
        <button className="src-dir-name" aria-expanded={isOpen} onClick={handleToggle}>
          {isOpen ? '▾' : '▸'} {name}/ <span className="src-faint">· {count(dirCount ?? 0)}</span>
        </button>
      )}
      {isOpen && (
        <div className={depth > 0 ? 'src-dir-in' : ''}>
          {loading && <p className="src-faint">{depth === 0 ? 'reading the record…' : 'reading…'}</p>}
          {error && <p className="act-refused">{error}</p>}
          {sortedFolders &&
            sortedFolders.map((d) => (
              <Dir
                key={d.path}
                col={col}
                path={d.path}
                name={d.name}
                count={d.count}
                depth={depth + 1}
                state={state}
                q={q}
                openPaths={openPaths}
                onToggle={onToggle}
                onOpen={onOpen}
              />
            ))}
          {files &&
            files.map((f) => (
              <button key={f.key} className="src-file" onClick={() => onOpen(f.key)}>
                {f.label && f.label !== f.key ? f.label : f.key.split('/').pop()}{' '}
                <span className="src-faint">
                  · {bytes(f.size)}
                  {f.state !== 'present' ? ` · ${f.state}` : ''}
                </span>
              </button>
            ))}
          {nextOffset !== null && (
            <button className="btn quiet src-more" disabled={loadingMore} onClick={loadMore}>
              {loadingMore ? 'reading…' : 'more files…'}
            </button>
          )}
          {isEmpty && <p className="src-faint">nothing matches</p>}
        </div>
      )}
    </div>
  )
}

