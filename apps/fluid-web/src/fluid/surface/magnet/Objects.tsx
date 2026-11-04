/* WHAT A MAGNET'S PAGE HOLDS, BESIDES POSTS: a compact file list and a small
 * image gallery. Each shows what the source's results already give, reads
 * nothing of its own, and opens the object into the one existing float
 * (objects/actions.ts act.float): no second window, no store of its own. */

import type { MouseEvent } from 'react'
import { act } from '../../objects/actions'
import type { MagnetLive, MagnetResult } from './types'
import { pictureOf, type ObjectRow } from './conversation'
import { Icon } from './icons'
import { tabEmpty, type TabId } from './model'

/** Objects newest first: by their post's number, highest first. */
export const newest = (rs: readonly MagnetResult[]): MagnetResult[] =>
  [...rs].sort((a, b) => ((b.value as ObjectRow).number ?? 0) - ((a.value as ObjectRow).number ?? 0))

const nameOf = (row: ObjectRow): string => row.title ?? row.kind
const fromOf = (row: ObjectRow): string => `from #${row.number ?? '?'}`
/* its click goes no further: the Magnet's window, raised by it, would cover the float it just opened */
const openIn = (row: ObjectRow, e: MouseEvent<HTMLElement>) => {
  e.stopPropagation()
  act.float({ address: row.address, title: nameOf(row), kind: row.kind, from: fromOf(row), anchor: e.currentTarget })
}

/** A tab with nothing to show: what was read, and the way to read on. */
export function TabEmpty({ tab, live, readOn }: { tab: TabId; live: MagnetLive & { loading: boolean }; readOn: { reading: boolean; read(): void } }) {
  const postsInAll = live.summaries.some((x) => x.summary.posts != null) ? live.summaries.reduce((n, x) => n + (x.summary.posts ?? 0), 0) : undefined
  const said = tabEmpty(tab, { loading: live.loading || readOn.reading, more: live.more, statuses: live.statuses, results: live.results, ...(postsInAll != null ? { postsInAll } : {}) })
  return <div className="mg-quiet">
    <p>{said.words}</p>
    {said.more && <button type="button" className="fl-btn mg-more" onClick={readOn.read}>Read more</button>}
  </div>
}

/** Under a tab's items, while its source has more. */
export function ReadOlder({ live, readOn }: { live: MagnetLive & { loading: boolean }; readOn: { reading: boolean; read(): void } }) {
  if (!live.more) return null
  return <div className="mg-more-row"><button type="button" className="fl-btn mg-more" disabled={live.loading || readOn.reading} onClick={readOn.read}>
    {readOn.reading ? 'Reading…' : 'Read more'}</button></div>
}

export function FileList({ results, kind }: { results: readonly MagnetResult[]; kind: 'file' | 'attachment' }) {
  return <ul className="mg-files" aria-label={kind === 'file' ? 'Files' : 'Attachments'}>
    {newest(results).map((r) => {
      const row = r.value as ObjectRow
      const word = row.preview?.is?.word ?? row.preview?.media_type ?? null
      return <li key={r.id}>
        <button type="button" className="mg-file" title={`Open ${nameOf(row)} (${fromOf(row)})`} onClick={(e) => openIn(row, e)}>
          <Icon name={kind} size={14} />
          <span className="mg-file-name">{nameOf(row)}</span>
          <span className="mg-meta">{word ? `${word} · ` : ''}{fromOf(row)}</span>
        </button>
      </li>
    })}
  </ul>
}

export function ImageGallery({ results }: { results: readonly MagnetResult[] }) {
  return <ul className="mg-gallery" aria-label="Images and media">
    {newest(results).map((r) => {
      const row = r.value as ObjectRow
      const pic = pictureOf(row)
      return <li key={r.id}>
        <button type="button" className="mg-tile" title={`Open ${nameOf(row)} (${fromOf(row)})`} aria-label={pic ? undefined : `Open ${nameOf(row)}`}
          onClick={(e) => openIn(row, e)}>
          {pic ? <img src={pic} alt={`Open ${nameOf(row)}`} loading="lazy" />
            : <span className="mg-tile-name"><Icon name="image" size={14} /> {nameOf(row)}</span>}
        </button>
      </li>
    })}
  </ul>
}
