/* THE SWITCHER: the conversation name's choice sheet (spec section 7, the
 * demo's picker; #190). A search, RECENT with each conversation's activity
 * (the overview the F0 switcher had: posts, included, last activity,
 * working, needs you, not saved), and the Stream. Home and New conversation
 * are the bar's ◎ and + (#190), not rows here.
 *
 * EVERY CONVERSATION IS REACHABLE WITHOUT ITS NAME (#568 1.2). Production's
 * picker (surfaces/ConvPicker.tsx) lists every conversation, each opened out
 * to its Topics with their counts; this brings that browse here, quietly:
 * Recent first, then one fold -- "All conversations" -- under which every
 * other one is listed by when it was last active, and a conversation with
 * Topics opens out (▸) to them. The search matches Topics as well as names,
 * showing the conversation opened out to the Topics that matched. A Topic
 * opens its conversation read under that Topic (A8: Column.tsx's Topics);
 * the conversation's own row, under every post. Nothing is drawn larger at
 * rest: the fold is one line.
 *
 * Keyboard: ↑/↓ move, → opens a conversation's Topics and ← closes them,
 * Enter chooses.
 *
 * LATEST IN EACH ROW (conversation/latest.ts): a conversation's own newest
 * post -- a reply under an old post included -- opened exactly, in its
 * thread, beside the row that opens the conversation where the reader was. */

import { useEffect, useMemo, useRef, useState } from 'react'
import { ago } from '../../api'
import { store, type Conversation, type Id } from '../store'
import { closeSheet, openSheet, Sheet } from '../frame/Sheet'
import { useList } from './hooks'
import { setTopic } from './threads'
import { LATEST, latestAnchor, openLatestIn } from './latest'
import { useLinkDrop } from './linkDrop'
import type { LinkTarget } from '../render/objectRef'
import { registry } from '../surface/actions/registry'
import { installProviders } from '../surface/actions/providers'
import { chromeCtx } from '../surface/SurfaceChrome'
import { classNow, inputMode } from '../frame/narrow'
import * as nav from '../nav'

export const SWITCHER = 'switcher'
const RECENT = 8

interface Topic { id: Id; name: string; turns: number }

const plural = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`

/** WHO IS WORKING IN A CONVERSATION RIGHT NOW, as its row says it: how many
 *  runs, and whose ("2 working: @Caretaker ×2"). One entry per run, from
 *  the list's `workers`; a server that sends only the count is said as
 *  before ("2 working"). */
export function workersWords(c: Pick<Conversation, 'working' | 'workers'>): string {
  const ws = c.workers ?? []
  if (!ws.length) return `${c.working} working`
  const by = new Map<string, number>()
  for (const w of ws) { const k = '@' + (w.alias ?? '?').replace(/^@/, ''); by.set(k, (by.get(k) ?? 0) + 1) }
  return `${c.working} working: ${[...by].map(([k, n]) => (n > 1 ? `${k} ×${n}` : k)).join(', ')}`
}
const workersTitle = (c: Conversation) => (c.workers ?? []).map((w) => `@${(w.alias ?? '?').replace(/^@/, '')} is working${w.since ? ` since ${new Date(w.since * 1000).toLocaleTimeString()}` : ''}`).join('\n') || undefined

export default function Switcher({ current, first, view, busy, onPick, onHome, onStream, onGovernance, onNew }: {
  current: Id | null
  first: boolean
  view: 'conversation' | 'home' | 'stream' | 'gov'
  busy: boolean
  onPick: (id: Id) => void
  onHome: () => void
  onStream: () => void
  /** the Governance page; absent, not offered */
  onGovernance?: () => void
  onNew: () => void
}) {
  return (
    <Sheet id={SWITCHER} label="conversations" className="fw-switcher fx-switcher">
      <SwitcherBody current={current} first={first} view={view} busy={busy} onPick={onPick} onHome={onHome} onStream={onStream}
        onGovernance={onGovernance} onNew={onNew} />
    </Sheet>
  )
}

type Row =
  | { kind: 'conv'; c: Conversation; topics: Topic[]; open: boolean }
  | { kind: 'topic'; c: Conversation; t: Topic }
  | { kind: 'fold' }

function SwitcherBody({ current, first, view, onPick, onStream, onGovernance }: Parameters<typeof Switcher>[0]) {
  const list = useList()
  const [q, setQ] = useState('')
  const [found, setFound] = useState<Conversation[]>([])
  const [searchNext, setSearchNext] = useState<string | null>(null)
  const [all, setAll] = useState(false)
  const [expanded, setExpanded] = useState<Set<Id>>(() => new Set())
  const [at, setAt] = useState(0)
  const input = useRef<HTMLInputElement>(null)
  const box = useRef<HTMLDivElement>(null)
  const loadingPage = useRef(false)
  useEffect(() => { void store.loadListIfMoved() }, [])
  useEffect(() => {
    const t = setTimeout(() => input.current?.focus(), 50)
    return () => clearTimeout(t)
  }, [])
  const want = q.trim().toLowerCase()
  useEffect(() => {
    if (!want) { setFound([]); setSearchNext(null); return }
    let live = true
    const timer = window.setTimeout(() => {
      loadingPage.current = true
      void store.conversationPage(null, want).then((page) => {
        if (!live) return
        setFound(page.conversations)
        setSearchNext(page.next)
      }).catch(() => {}).finally(() => { loadingPage.current = false })
    }, 180)
    return () => { live = false; window.clearTimeout(timer) }
  }, [want])
  const convs = (want ? found : list ?? []).filter((c: Conversation) => c.id !== 'home' && c.name?.toLowerCase() !== 'home')
  const topicsOf = useMemo(() => new Map(convs.map((c) => [c.id, (c.topics ?? []).filter((t) => t && t.name)])), [convs])

  const more = () => {
    if (loadingPage.current) return
    if (want) {
      if (!searchNext) return
      loadingPage.current = true
      void store.conversationPage(searchNext, want).then((page) => {
        setFound((was) => {
          const ids = new Set(was.map((c) => c.id))
          return [...was, ...page.conversations.filter((c) => !ids.has(c.id))]
        })
        setSearchNext(page.next)
      }).catch(() => {}).finally(() => { loadingPage.current = false })
    } else if (all && store.listNext) {
      loadingPage.current = true
      void store.loadMoreList().finally(() => { loadingPage.current = false })
    }
  }
  const scrolled = () => {
    const el = box.current
    if (el && el.scrollHeight - el.scrollTop - el.clientHeight < 160) more()
  }
  useEffect(() => { if (all && !want) more() }, [all]) // first page beyond Recent

  /* What is drawn, in order: the rows a key can reach. */
  const { recent, rest, rows } = useMemo(() => {
    const conv = (c: Conversation, open: boolean, only?: Topic[]): Row[] => {
      const topics = topicsOf.get(c.id) ?? []
      const out: Row[] = [{ kind: 'conv', c, topics, open }]
      if (open) for (const t of only ?? topics) out.push({ kind: 'topic', c, t })
      return out
    }
    if (want) {
      const foundRows: Row[] = []
      for (const c of convs) {
        const hits = (topicsOf.get(c.id) ?? []).filter((t) => t.name.toLowerCase().includes(want))
        foundRows.push(...conv(c, hits.length > 0, hits.length ? hits : undefined))
      }
      return { recent: foundRows, rest: [] as Row[], rows: foundRows }
    }
    const recent = convs.slice(0, RECENT).flatMap((c) => conv(c, expanded.has(c.id)))
    const rest = all ? convs.slice(RECENT).flatMap((c) => conv(c, expanded.has(c.id))) : []
    const fold: Row[] = convs.length > RECENT ? [{ kind: 'fold' }] : []
    return { recent, rest, rows: [...recent, ...fold, ...rest] }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [convs, topicsOf, want, all, expanded])
  useEffect(() => setAt(0), [want])
  useEffect(() => {
    box.current?.querySelector<HTMLElement>(at < 0 ? '[data-go].at' : `[data-row="${at}"]`)?.scrollIntoView({ block: 'nearest' })
  }, [at])

  const go = (fn: () => void) => () => { closeSheet(); fn() }
  /* THE GO TO ROWS ARE IN THE SELECTION TOO, above the list: their places
     are -n..-1, so Up from the first conversation reaches them and Enter
     runs the one selected -- while a fresh sheet still starts at the first
     conversation (0), as Enter in the search always has. */
  const openLatestSheet = () => { const el = latestAnchor(); if (el) openSheet(LATEST, el, el.id === 'latest' ? 'end' : 'start'); else closeSheet() }
  const gos: { key: string; run: () => void }[] = !first && !want ? [
    { key: 'stream', run: go(onStream) },
    { key: 'latest', run: openLatestSheet },
    ...(onGovernance ? [{ key: 'gov', run: go(onGovernance) }] : []),
  ] : []
  const goAt = (key: string) => gos.findIndex((g) => g.key === key) - gos.length
  const toggle = (id: Id) => setExpanded((e) => { const n = new Set(e); if (n.has(id)) n.delete(id); else n.add(id); return n })
  const choose = (r: Row | undefined) => {
    if (!r) return
    if (r.kind === 'fold') { setAll((v) => !v); return }
    /* A Topic opens its conversation read under it (A8); the conversation
       itself, under every post. */
    setTopic(r.c.id, r.kind === 'topic' ? r.t.id : null)
    closeSheet(); onPick(r.c.id)
  }
  const onKey = (e: React.KeyboardEvent) => {
    if (e.defaultPrevented) return
    /* Enter on a row the keyboard focused (Tab) is that row's. */
    const focused = (e.target as HTMLElement | null)?.closest?.<HTMLElement>('[data-go], [data-row]')
    if (e.key === 'Enter' && focused && box.current?.contains(focused)) {
      e.preventDefault()
      const g = focused.dataset.go
      if (g) gos.find((x) => x.key === g)?.run()
      else choose(rows[Number(focused.dataset.row)])
      return
    }
    if (at < 0) {
      if (e.key === 'ArrowDown') { e.preventDefault(); setAt((i) => Math.min(rows.length - 1, i + 1)) }
      else if (e.key === 'ArrowUp') { e.preventDefault(); setAt((i) => Math.max(-gos.length, i - 1)) }
      else if (e.key === 'Enter') { e.preventDefault(); gos[at + gos.length]?.run() }
      return
    }
    const r = rows[at]
    if (e.key === 'ArrowDown') { e.preventDefault(); setAt((i) => Math.min(rows.length - 1, i + 1)) }
    else if (e.key === 'ArrowUp') { e.preventDefault(); setAt((i) => Math.max(-gos.length, i - 1)) }
    else if (e.key === 'ArrowRight' && r?.kind === 'conv' && !r.open && r.topics.length && !want) { e.preventDefault(); toggle(r.c.id) }
    else if (e.key === 'ArrowLeft' && r && !want) {
      if (r.kind === 'conv' && r.open) { e.preventDefault(); toggle(r.c.id) }
      else if (r.kind === 'topic') { e.preventDefault(); setAt(rows.findIndex((x) => x.kind === 'conv' && x.c.id === r.c.id)) }
    } else if (e.key === 'Enter') { e.preventDefault(); choose(r) }
  }

  const draw = (r: Row, i: number) => {
    const active = i === at
    if (r.kind === 'fold') {
      return (
        <li key="fold">
          <button className={'fx-row fw-fold' + (active ? ' at' : '')} data-row={i} aria-expanded={all}
            onMouseEnter={() => setAt(i)} onClick={() => choose(r)}>
            <span>All conversations</span><small>{all ? 'fewer' : `${Math.max(0, store.listTotal - RECENT)} more ▸`}</small>
          </button>
        </li>
      )
    }
    if (r.kind === 'topic') {
      return (
        <li key={r.c.id + r.t.id}>
          <button className={'fx-row fw-topic' + (active ? ' at' : '')} data-row={i} data-topic={r.t.id} data-c={r.c.id}
            title={`${r.c.name} › ${r.t.name}`} onMouseEnter={() => setAt(i)} onClick={() => choose(r)}>
            <span><span className="fw-hash" aria-hidden="true">#</span>{r.t.name}</span>
            <small className="fw-meta">{plural(r.t.turns, 'post', 'posts')}</small>
          </button>
        </li>
      )
    }
    const c = r.c
    return (
      <LinkRow key={c.id} c={c}>
        {/* Not a second button in the row: the row stays one control, and
            the keyboard opens it out with → (as ConvPicker's does). */}
        {r.topics.length > 0 ? (
          <span className="fw-open" role="button" tabIndex={-1} aria-expanded={r.open}
            aria-label={`${r.open ? 'hide' : 'show'} the topics of ${c.name}`}
            onClick={() => { if (!want) toggle(c.id) }}>{r.open ? '▾' : '▸'}</span>
        ) : <span className="fw-open none" aria-hidden="true" />}
        <button className={'fx-row' + (c.id === current && view === 'conversation' ? ' on' : '') + (active ? ' at' : '')} data-row={i} data-c={c.id}
          onMouseEnter={() => setAt(i)} onClick={() => choose(r)}>
          <span className="fw-cname">{c.name}</span>
          <small className="fw-meta">
            {c.provisional ? <span className="fw-not-saved">not saved</span> : (
              <>
                {c.posts} {c.posts === 1 ? 'post' : 'posts'}
                {c.included ? ` + ${c.included} included` : ''}
                {' · '}{c.last_activity ? ago(c.last_activity) : 'nothing yet'}
                {c.working ? <span className="fw-working" title={workersTitle(c)}> · {workersWords(c)}</span> : ''}
                {c.needs_you ? <span className="fw-needs-you-count"> · {c.needs_you} needs you</span> : ''}
              </>
            )}
          </small>
        </button>
        {/* NOT A SECOND BUTTON IN THE ROW either, as ▸ is not: the row's
            button stays its one control (what the keyboard's Enter and every
            `li button` reach). Pointer users click it; the keyboard has the
            bar's Latest (L); Tab reaches it, and Enter or Space opens it. */}
        {!c.provisional && c.posts > 0 && (
          <span className="fw-latest-in" role="button" tabIndex={0} data-latest-in={c.id}
            aria-label={`open the latest post in ${c.name}`} title={`Open the latest post in ${c.name}, in its thread`}
            onClick={() => { closeSheet(); void openLatestIn(c.id, view === 'conversation' ? current : null, onPick) }}
            onKeyDown={(e) => {
              if (e.key !== 'Enter' && e.key !== ' ') return
              e.preventDefault(); e.stopPropagation()
              closeSheet(); void openLatestIn(c.id, view === 'conversation' ? current : null, onPick)
            }}>Latest</span>
        )}
        {!c.provisional && <MakeMagnet c={c} />}
      </LinkRow>
    )
  }

  let i = -1
  const next = () => ++i
  return (
    <div className="fw-switch" ref={box} onKeyDown={onKey} onScroll={scrolled}>
      <input ref={input} placeholder="Find a conversation or topic" aria-label="find a conversation or topic" value={q} onChange={(e) => setQ(e.target.value)} />
      {!first && !want && (
        <>
          {/* Home and New conversation are the bar's own ◎ and + (#190: Home
              is never an entry in the conversation list). */}
          <div className="fx-sec">Go to</div>
          <button className={'fx-row fw-stream-link' + (view === 'stream' ? ' on' : '') + (at === goAt('stream') ? ' at' : '')} aria-label="stream" data-go="stream"
            onMouseEnter={() => setAt(goAt('stream'))} onClick={go(onStream)}>
            <span>Stream</span><small>every post, newest first</small>
          </button>
          {/* The newest posts everywhere: the bar's Latest, here too for a
              bar too narrow to hold it (latest.css). */}
          <button className={'fx-row fw-latest-link' + (at === goAt('latest') ? ' at' : '')} aria-label="latest activity" data-go="latest"
            onMouseEnter={() => setAt(goAt('latest'))} onClick={openLatestSheet}>
            <span>Latest activity</span><small>newest posts, replies included (L)</small>
          </button>
          {onGovernance && (
            <button className={'fx-row fw-gov-link' + (view === 'gov' ? ' on' : '') + (at === goAt('gov') ? ' at' : '')} aria-label="governance" data-go="gov"
              onMouseEnter={() => setAt(goAt('gov'))} onClick={go(onGovernance)}>
              <span>Governance</span><small>what is owed to you · rules · personas</small>
            </button>
          )}
        </>
      )}
      <div className="fx-sec">{want ? 'Found' : 'Recent'}</div>
      <ul className="fx-rows">
        {recent.map((r) => draw(r, next()))}
        {list && want && rows.length === 0 && <li className="fx-faint fx-none">No conversation or topic by that name.</li>}
        {!want && store.listTotal > RECENT && draw({ kind: 'fold' }, next())}
        {rest.map((r) => draw(r, next()))}
      </ul>
    </div>
  )
}

/** A conversation's row in the switcher, which an object or a post can be
 *  let go on: included or referenced there, after a confirmation (W4). */
function LinkRow({ c, children }: { c: Pick<Conversation, 'id' | 'name' | 'provisional'>; children: React.ReactNode }) {
  const target = useMemo<LinkTarget | null>(() => (c.provisional ? null : { kind: 'conversation', conversation: c.id, name: c.name }), [c.id, c.name, c.provisional])
  const drop = useLinkDrop(target)
  return <li className={'fw-conv-row' + drop.className} {...drop.props}>{children}</li>
}

/** MAKE MAGNET from a row (Surface Tension P7): the conversation provider's
 *  Make magnet, run through the one registry; not a second button in the row
 *  either, as Latest is not. Disabled with its reason where a Magnet cannot
 *  go (outside a conversation's workspace). */
function MakeMagnet({ c }: { c: Pick<Conversation, 'id' | 'name'> }) {
  installProviders()
  const target = { resource: { address: 'conversation:' + c.id, kind: 'conversation' } }
  const ctx = chromeCtx(classNow(), inputMode())
  const row = registry.list(target, ctx).find((x) => x.def.id === 'conversation.makeMagnet')
  if (!row) return null
  const why = row.availability.state === 'disabled' ? row.availability.reason.message : null
  const make = () => {
    if (why) { nav.toast({ text: why }); return }
    closeSheet()
    void registry.run('conversation.makeMagnet', target, ctx).catch(() => {})
  }
  return <span className="fw-latest-in fw-magnet-in" role="button" tabIndex={0} data-magnet-in={c.id} aria-disabled={why ? true : undefined}
    aria-label={`make a magnet of ${c.name}`} title={why ?? `Make magnet: ${c.name} as a small live view in this workspace`}
    onClick={(e) => { e.stopPropagation(); make() }}
    onKeyDown={(e) => {
      if (e.key !== 'Enter' && e.key !== ' ') return
      e.preventDefault(); e.stopPropagation()
      make()
    }}>Magnet</span>
}
