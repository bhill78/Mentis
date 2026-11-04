/* A MAGNET'S QUICK SUMMARY (owner Turns #1227, #1592 and the summary-card
 * sketch: the disc at the card's corner), and the smaller preview a rest or
 * keyboard focus on the disc shows around it (MagnetPreview).
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
import type { MagnetId } from './types'
import * as nav from '../../nav'
import { ago } from '../../../api'
import { usePost } from '../../conversation/hooks'
import { excerpt } from '../../conversation/text'
import { act } from '../../objects/actions'
import { ESC, onEscape } from '../../escape'
import type { MagnetConfig, MagnetLive, MagnetResult } from './types'
import { MAGNET_CHOICES } from './choices'
import {
  BUILD_ENV, CATEGORY_LABEL, SOURCE_WORD, glyphOf, holdingOf, notRunning, sourceKey, tabsOf,
  type InformationType, type MagnetStatus,
} from './model'
import { adapters } from './runtime'
import { closePeek, magnetAppOps } from './client'
import { pictureOf, type ObjectRow } from './conversation'
import { Icon } from './icons'
import { newest } from './Objects'
import { participantsBeyond, previewPlacement, readMagnetTheme, samePreviewPosition, sameSummaryCardPosition, summaryCardPlacement, summaryLatest, summaryPresence, type PreviewPosition } from './presentation'

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
  /** Open (one level up), Configure, Open its source conversation (when it may) */
  open?: () => void
  workspace?: () => void
}

const STATUS_WORD = { partial: 'Partly read', unavailable: 'Not available', busy: 'Busy' } as const

/** Each source that didn't read in full, and why: one never speaks for another. */
export function SourceStatuses({ live }: { live: Pick<MagnetLive, 'statuses'> }) {
  const troubled = (live.statuses ?? []).filter((s) => s.status !== 'ok')
  if (!troubled.length) return null
  return <ul className="mg-sources-said" aria-label="How its sources read">
    {troubled.map((s) => <li key={sourceKey(s.source)} data-status={s.status}>
      <b>{STATUS_WORD[s.status as keyof typeof STATUS_WORD]}</b>{s.reason ? `: ${s.reason}` : ''}</li>)}
  </ul>
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
    <SourceStatuses live={live} />
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
      {workspace && <button type="button" className="fl-btn" onClick={workspace}>Open its source conversation</button>}
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
  const others = participantsBeyond(totals)
  const synthesis = notRunning(config, BUILD_ENV, adapters).find((x) => x.facet === 'synthesis')
  const sources = config.sources.length === 1 ? SOURCE_WORD[glyphOf(config)] : `${config.sources.length} sources`
  /* who is here is said only where a source says it, and nothing where it
     doesn't; who is active now no source can say, so it is not drawn */
  return <div className="mg-sum-about" data-brief={brief || undefined}>
    {about ? <p>{about}</p> : null}
    <p className="mg-sum-facts">
      <span>From {sources}</span>
      {presence.activity != null && presence.activity > 0 && <span> · active {ago(presence.activity)}</span>}
      {presence.participants != null && <span> · {presence.participants}{others ? '+' : ''} participant{presence.participants === 1 && !others ? '' : 's'}</span>}
      {unread > 0 && <span> · <b>{unread} new</b></span>}
    </p>
    <PeopleLine label="Participants" names={presence.participantNames} keys={presence.participantKeys} more={presence.participantNamesMore} others={others} />
    {!brief && <p className="mg-sum-synth" title={synthesis?.reason.message}>
      {config.synthesis.mode === 'manual'
        ? 'No synthesized summary: synthesis is manual, and nothing generates one in this build. What it holds is below.'
        : synthesis?.reason.message ?? 'No synthesized summary yet.'}
    </p>}
  </div>
}

/** A person's initial: the first letter of their name, past any @ or mark. */
const personInitial = (name: string): string => (name.match(/[\p{L}\p{N}]/u)?.[0] ?? name.slice(0, 1)).toLocaleUpperCase()

function PeopleLine({ label, names, keys, more, others = false }: { label: string; names: string[]; keys: string[]; more: number; others?: boolean }) {
  if (names.length === 0) return null
  const shown = names.join(', ')
  const overflow = (more > 0 ? `, plus ${more} more` : '') + (others ? ', and others' : '')
  return <p className="mg-people" aria-label={`${label}: ${shown}${overflow}`}>
    {names.map((name, i) => <span key={keys[i]} className="mg-person" title={name}>{personInitial(name)}</span>)}
    <span className="mg-people-names"><span className="mg-people-text">{label}: {shown}</span>{(more > 0 || others) && <b className="mg-people-more">{more > 0 ? `+${more} more` : 'and others'}</b>}</span>
  </p>
}

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

const PREVIEW = { w: 280, h: 240 }
export const previewIdOf = (id: MagnetId): string => `mg-preview-${id}`

/** What a mouse resting on the disc, or the keyboard's focus on it, is shown
 *  around it: who it is, how it is and what it last had, from its summary and
 *  nothing else, so it reads no page. It describes the disc and takes no focus;
 *  the pointer may move onto it, and Esc puts it away (WCAG 1.4.13). Whatever
 *  a source doesn't say is not drawn. */
export function MagnetPreview({ id, config, title, live, status, unread, onEnter, onLeave }: Pick<SummaryProps, 'id' | 'config' | 'title' | 'live' | 'status' | 'unread'> & { onEnter: () => void; onLeave: () => void }) {
  const el = useRef<HTMLDivElement | null>(null)
  const [place, setPlace] = useState<PreviewPosition>({ x: MAGNET_CHOICES.disc + 8, y: 0, side: 'right' })
  const theme = readMagnetTheme(config)
  const totals = live.summaries.map((s) => s.summary)
  const presence = summaryPresence(totals)
  const latest = summaryLatest(totals)
  /* placed from what it measures, so a longer finding is held in the viewport too */
  useLayoutEffect(() => {
    const position = () => {
      const zone = el.current?.parentElement
      const disc = zone?.querySelector('.mg-disc')
      if (!zone || !disc || !el.current) return
      const box = el.current.getBoundingClientRect()
      /* the main area, under the app's bar, held to the viewport */
      const main = zone.closest('.fx-main')?.getBoundingClientRect()
      const left = Math.max(0, main?.left ?? 0), top = Math.max(0, main?.top ?? 0)
      const room = { left, top, width: Math.min(window.innerWidth, main?.right ?? Infinity) - left, height: Math.min(window.innerHeight, main?.bottom ?? Infinity) - top }
      const next = previewPlacement(zone.getBoundingClientRect(), disc.getBoundingClientRect(), room, { width: box.width || PREVIEW.w, height: box.height || PREVIEW.h })
      setPlace((current) => samePreviewPosition(current, next) ? current : next)
    }
    position()
    window.addEventListener('resize', position)
    window.addEventListener('scroll', position, true)
    return () => {
      window.removeEventListener('resize', position)
      window.removeEventListener('scroll', position, true)
    }
  }, [latest?.id, latest?.preview, presence.participants])
  useEffect(() => onEscape(ESC.peek, () => { closePeek(id, true); return true }), [id])
  return <div ref={el} id={previewIdOf(id)} className="mg-preview" role="tooltip" data-side={place.side}
    data-theme={theme.state === 'available' ? theme.theme : undefined}
    style={{ left: place.x, top: place.y, width: PREVIEW.w, maxWidth: 'calc(100vw - 16px)', maxHeight: `min(${PREVIEW.h}px, calc(100dvh - 16px))` }}
    onPointerEnter={onEnter} onPointerLeave={onLeave}>
    <header className="mg-sum-head">
      <b className="mg-sum-title">{title}</b>
      <span className="mg-sum-status" data-state={status.state}>{status.words}</span>
    </header>
    <p className="mg-sum-facts">
      <span>From {SOURCE_WORD[glyphOf(config)]}</span>
      {presence.activity != null && presence.activity > 0 && <span> · active {ago(presence.activity)}</span>}
      {unread > 0 && <span> · <b>{unread} new</b></span>}
    </p>
    {latest && <p className="mg-preview-latest">
      <span className="mg-meta">Latest{latest.author ? ` · ${latest.author}` : ''}{latest.at ? ` · ${ago(latest.at)}` : ''}</span>
      {latest.preview && <span className="mg-line-text">{latest.preview}</span>}
    </p>}
    <PeopleLine label="Participants" names={presence.participantNames} keys={presence.participantKeys} more={presence.participantNamesMore} others={participantsBeyond(totals)} />
  </div>
}

/** The card, from Peek: anchored with the disc at its corner, opening away
 *  from the window's nearest edges. It closes on Esc, a press outside, or ×. */
export function SummaryCard(p: SummaryProps) {
  const el = useRef<HTMLDivElement | null>(null)
  const [place, setPlace] = useState({ x: MAGNET_CHOICES.disc / 2, y: MAGNET_CHOICES.disc / 2, flipX: false, flipY: false })
  useLayoutEffect(() => {
    const position = () => {
      const zone = el.current?.parentElement?.getBoundingClientRect()
      if (!zone || typeof window === 'undefined') return
      const next = summaryCardPlacement(zone, { width: window.innerWidth, height: window.innerHeight },
        { width: MAGNET_CHOICES.card.w, height: MAGNET_CHOICES.card.maxH }, MAGNET_CHOICES.disc)
      const position = { x: next.x, y: next.y, flipX: next.flipX, flipY: next.flipY }
      setPlace((current) => sameSummaryCardPosition(current, position) ? current : position)
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
    const outside = (e: PointerEvent) => {
      const zone = el.current?.parentElement
      if (zone && !zone.contains(e.target as Node)) closePeek(p.id)
    }
    document.addEventListener('pointerdown', outside, true)
    return () => document.removeEventListener('pointerdown', outside, true)
  }, [p.id])
  return <div ref={el} className="mg-card" role="dialog" aria-label={`${p.title}: summary`}
    data-flip-x={place.flipX || undefined} data-flip-y={place.flipY || undefined}
    style={{ left: place.x, top: place.y, width: MAGNET_CHOICES.card.w, maxWidth: 'calc(100vw - 16px)', maxHeight: `min(${MAGNET_CHOICES.card.maxH}px, calc(100dvh - 16px))` }}>
    <button type="button" className="mg-card-close fl-btn" aria-label="Close the summary" onClick={() => closePeek(p.id)}>×</button>
    <SummaryBody {...p} />
  </div>
}
