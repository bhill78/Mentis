/* A MAGNET'S QUICK SUMMARY (owner Turns #1227, #1592 and the summary-card
 * sketch: the disc at the card's corner).
 *
 * What the Magnet is and what it holds now, read from its sources through
 * the same live results its pane shows (useMagnet): never a copy of their
 * history. Its summary (what the source says of itself, when it was last
 * active, what is new since it was last opened here, and whether a
 * synthesized summary exists -- none is generated in this build, and it says
 * so), then each kind of thing it collects -- posts, files, images and
 * media, attachments, and any other kind it selects -- with how many, the
 * most recent few, each opening the item itself, and "All" opening the
 * Magnet at that tab. A kind it does not collect says so, with Configure.
 *
 * Drawn two ways from one body: a card anchored to a disc in a window
 * (SummaryCard), or the Summary panel of its pane (anywhere else). */

import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import * as nav from '../../nav'
import { ago } from '../../../api'
import { usePost } from '../../conversation/hooks'
import { excerpt } from '../../conversation/text'
import { act } from '../../objects/actions'
import { ESC, onEscape } from '../../escape'
import type { MagnetConfig, MagnetLive, MagnetResult } from './types'
import { MAGNET_CHOICES } from './choices'
import {
  BUILD_ENV, CATEGORY_LABEL, SOURCE_WORD, glyphOf, holdingOf, notRunning, tabsOf,
  type InformationType, type MagnetStatus,
} from './model'
import { adapters } from './runtime'
import { closePeek, magnetAppOps, type PeekHow } from './client'
import { pictureOf, type ObjectRow } from './conversation'
import { Icon } from './icons'
import { readMagnetTheme, summaryCardPlacement, summaryPresence } from './presentation'

/** The kinds a summary always accounts for (owner: posts, files, media,
 *  attachments), then whatever else the Magnet selects. */
const ALWAYS: InformationType[] = ['post', 'file', 'image', 'attachment']
const RECENT = 3

export interface SummaryProps {
  id: `mag-${string}`
  config: MagnetConfig
  title: string
  live: MagnetLive & { loading: boolean; error?: string }
  unread: number
  status: MagnetStatus
  /** Open (one level up), Configure, Open as workspace (when it may) */
  open?: () => void
  workspace?: () => void
}

export function SummaryBody({ id, config, title, live, unread, status, open, workspace }: SummaryProps) {
  const theme = readMagnetTheme(config)
  const totals = live.summaries.map((s) => s.summary)
  const postsTotal = totals.some((s) => s.posts != null) ? totals.reduce((n, s) => n + (s.posts ?? 0), 0) : undefined
  const holding = holdingOf(live.results, postsTotal)
  const count = (t: InformationType) => holding.find((h) => h.type === t)?.count ?? 0
  const tabs = tabsOf(config, BUILD_ENV, adapters)
  const selected = tabs.filter((t) => t.id !== 'search').map((t) => t.id as InformationType)
  const kinds = [...ALWAYS, ...selected.filter((t) => !ALWAYS.includes(t))]
  return <div className="mg-sum" data-magnet-summary={id}
    data-theme={theme.state === 'available' ? theme.theme : undefined}
    data-theme-unavailable={theme.state === 'unavailable' || undefined}>
    <header className="mg-sum-head">
      <b className="mg-sum-title">{title}</b>
      <span className="mg-sum-status" data-state={status.state}>{status.words}</span>
    </header>
    <SummaryLead config={config} live={live} unread={unread} />
    {theme.state === 'unavailable' && <p className="mg-unavailable" role="status">{theme.reason}</p>}
    {live.error ? <p className="mg-quiet">{live.error}</p> : <div className="mg-cats">
      {kinds.map((t) => {
        const tab = tabs.find((x) => x.id === t)
        if (!tab) return <div key={t} className="mg-cat mg-cat-off" data-type={t}>
          <h4><Icon name={t} /> {CATEGORY_LABEL[t]}</h4>
          <p className="mg-quiet-line">Not collected by this magnet. <button type="button" className="mg-link" onClick={() => magnetAppOps.configure(id, 'collects')}>Configure</button></p>
        </div>
        if (tab.availability.state !== 'available') return <div key={t} className="mg-cat mg-cat-off" data-type={t}>
          <h4><Icon name={t} /> {CATEGORY_LABEL[t]}</h4>
          <p className="mg-quiet-line">{tab.availability.state === 'disabled' ? tab.availability.reason.message : ''}</p>
        </div>
        const items = live.results.filter((r) => r.kind === t)
        const n = count(t)
        return <div key={t} className="mg-cat" data-type={t} data-count={n}>
          <h4><Icon name={t} /> {CATEGORY_LABEL[t]} <span className="mg-count" aria-label={`${n} ${CATEGORY_LABEL[t].toLowerCase()}`}>{n}</span>
            {n > 0 && <button type="button" className="mg-link mg-all" onClick={() => magnetAppOps.showTab(id, t)}>All</button>}</h4>
          {!items.length ? <p className="mg-quiet-line">{live.loading ? 'Reading…' : 'None yet.'}</p>
            : t === 'post' ? <ul className="mg-recent">{items.slice(0, RECENT).map((r) => <PostLine key={r.id} r={r} />)}</ul>
            : t === 'image' ? <ul className="mg-thumbs">{newest(items).slice(0, 4).map((r) => <ObjectLine key={r.id} r={r} kind={t} thumb />)}</ul>
            : <ul className="mg-recent">{newest(items).slice(0, RECENT).map((r) => <ObjectLine key={r.id} r={r} kind={t} />)}</ul>}
        </div>
      })}
    </div>}
    <footer className="mg-sum-foot">
      {open && <button type="button" className="fl-btn" onClick={open}>Open</button>}
      <button type="button" className="fl-btn" onClick={() => magnetAppOps.configure(id, 'all')}>Configure</button>
      {workspace && <button type="button" className="fl-btn" onClick={workspace}>Open as workspace</button>}
    </footer>
  </div>
}

/** What it is, in a few lines: what its source says of itself, where it is
 *  from, when it was last active, what is new, and whether a synthesized
 *  summary exists. The summary's lead, and the slide-out's above its tabs
 *  (`brief`: its about held to two lines, the synthesis note left out). */
export function SummaryLead({ config, live, unread, brief = false }: Pick<SummaryProps, 'config' | 'live' | 'unread'> & { brief?: boolean }) {
  const totals = live.summaries.map((s) => s.summary)
  const about = totals.find((s) => s.about)?.about
  const presence = summaryPresence(totals)
  const synthesis = notRunning(config, BUILD_ENV, adapters).find((x) => x.facet === 'synthesis')
  const sources = config.sources.length === 1 ? SOURCE_WORD[glyphOf(config)] : `${config.sources.length} sources`
  return <div className="mg-sum-about" data-brief={brief || undefined}>
    {about ? <p>{about}</p> : null}
    <p className="mg-sum-facts">
      <span>From {sources}</span>
      {presence.activity != null && presence.activity > 0 && <span> · active {ago(presence.activity)}</span>}
      {presence.participants != null && <span> · {presence.participants} participant{presence.participants === 1 ? '' : 's'}</span>}
      {presence.working != null && presence.working > 0 && <span className="mg-working"> · {presence.working} active now</span>}
      {unread > 0 && <span> · <b>{unread} new</b></span>}
    </p>
    {presence.participants == null && presence.working == null
      ? <p className="mg-unavailable mg-presence-unavailable" role="status">Participant and current activity details unavailable.</p>
      : null}
    <PeopleLine label="Participants" names={presence.participantNames} more={presence.participantNamesMore} />
    <PeopleLine label="Active now" names={presence.workerNames} more={presence.workerNamesMore} working />
    {!brief && <p className="mg-sum-synth" title={synthesis?.reason.message}>
      {config.synthesis.mode === 'manual'
        ? 'No synthesized summary: synthesis is manual, and nothing generates one in this build. What it holds is below.'
        : synthesis?.reason.message ?? 'No synthesized summary yet.'}
    </p>}
  </div>
}

function PeopleLine({ label, names, more, working = false }: { label: string; names: string[]; more: number; working?: boolean }) {
  if (names.length === 0) return null
  const shown = names.join(', ')
  const overflow = more > 0 ? `, plus ${more} more` : ''
  return <p className={`mg-people${working ? ' mg-workers' : ''}`} aria-label={`${label}: ${shown}${overflow}`}>
    {names.map((name) => <span key={name} className="mg-person" title={name}>{name.slice(0, 1).toLocaleUpperCase()}</span>)}
    <span className="mg-people-names">{label}: {shown}{more > 0 && <b className="mg-people-more"> +{more} more</b>}</span>
  </p>
}

/** Objects newest first: by their post's number, highest first. */
const newest = (rs: MagnetResult[]) => [...rs].sort((a, b) => ((b.value as ObjectRow).number ?? 0) - ((a.value as ObjectRow).number ?? 0))

function PostLine({ r }: { r: MagnetResult }) {
  const p = usePost(r.id)
  if (!p) return <li className="mg-quiet-line">…</li>
  const home = (r.source as { conversation?: string }).conversation ?? p.home
  return <li>
    <button type="button" className="mg-line" title="Read it in its conversation" onClick={() => { closePeek(); if (home) nav.read(home, p.id, p.number ?? null) }}>
      <span className="mg-meta">{p.number != null ? `#${p.number} · ` : ''}{p.author_name} · {ago(p.at)}</span>
      <span className="mg-line-text">{p.deleted ? 'Deleted' : excerpt(p, 120)}</span>
    </button>
  </li>
}

function ObjectLine({ r, kind, thumb = false }: { r: MagnetResult; kind: InformationType; thumb?: boolean }) {
  const row = r.value as ObjectRow
  const name = row.title ?? row.kind
  const pic = thumb ? pictureOf(row) : null
  return <li>
    <button type="button" className={thumb ? 'mg-thumb' : 'mg-line'} title={`Open ${name} (from #${row.number ?? '?'})`}
      onClick={(e) => { closePeek(); act.open({ address: row.address, title: name, kind: row.kind, from: `from #${row.number ?? '?'}`, anchor: e.currentTarget }) }}>
      {thumb ? (pic ? <img src={pic} alt={name} loading="lazy" /> : <span className="mg-thumb-name"><Icon name={kind} /> {name}</span>)
        : <><span className="mg-meta"><Icon name={kind} size={12} /> from #{row.number ?? '?'}</span><span className="mg-line-text">{name}</span></>}
    </button>
  </li>
}

/** The card: anchored with the disc at its corner, opening away from the
 *  window's nearest edges. A hover's card closes when the pointer leaves it
 *  and the disc; a pinned one (Peek) on Esc, a press outside, or ×. */
export function SummaryCard({ how, onLeave, onEnter, ...p }: SummaryProps & { how: PeekHow; onLeave: () => void; onEnter: () => void }) {
  const el = useRef<HTMLDivElement | null>(null)
  const [place, setPlace] = useState({ x: MAGNET_CHOICES.disc / 2, y: MAGNET_CHOICES.disc / 2, flipX: false, flipY: false })
  useLayoutEffect(() => {
    const position = () => {
      const zone = el.current?.parentElement?.getBoundingClientRect()
      if (!zone || typeof window === 'undefined') return
      const next = summaryCardPlacement(zone, { width: window.innerWidth, height: window.innerHeight },
        { width: MAGNET_CHOICES.card.w, height: MAGNET_CHOICES.card.maxH }, MAGNET_CHOICES.disc)
      setPlace({ x: next.x, y: next.y, flipX: next.flipX, flipY: next.flipY })
    }
    position()
    window.addEventListener('resize', position)
    window.addEventListener('scroll', position, true)
    return () => {
      window.removeEventListener('resize', position)
      window.removeEventListener('scroll', position, true)
    }
  }, [])
  useEffect(() => onEscape(ESC.peek, () => { closePeek(p.id); return true }), [p.id])
  useEffect(() => {
    if (how !== 'pinned') return
    const outside = (e: PointerEvent) => {
      const zone = el.current?.parentElement
      if (zone && !zone.contains(e.target as Node)) closePeek(p.id)
    }
    document.addEventListener('pointerdown', outside, true)
    return () => document.removeEventListener('pointerdown', outside, true)
  }, [how, p.id])
  return <div ref={el} className="mg-card" role="dialog" aria-label={`${p.title}: summary`} data-how={how}
    data-flip-x={place.flipX || undefined} data-flip-y={place.flipY || undefined}
    style={{ left: place.x, top: place.y, width: MAGNET_CHOICES.card.w, maxWidth: 'calc(100vw - 16px)', maxHeight: `min(${MAGNET_CHOICES.card.maxH}px, calc(100dvh - 16px))` }}
    onPointerEnter={onEnter} onPointerLeave={onLeave}>
    <button type="button" className="mg-card-close fl-btn" aria-label="Close the summary" onClick={() => closePeek(p.id)}>×</button>
    <SummaryBody {...p} />
  </div>
}
