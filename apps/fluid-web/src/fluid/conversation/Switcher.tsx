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
import { ago, CLIENT_HEADERS } from '../../api'
import { store, type Conversation, type Id } from '../store'
import { closeSheet, openSheet, Sheet } from '../frame/Sheet'
import { useList } from './hooks'
import { setTopic } from './threads'
import { LATEST, latestAnchor, openLatestIn } from './latest'

export const SWITCHER = 'switcher'
const RECENT = 8

interface Topic { id: Id; name: string; turns: number }

/* Each conversation's Topics, from the summary production's picker reads
   (`/api/conversations`). Read once a sheet opens, kept for the page. */
let topicsHeld: Map<Id, Topic[]> | null = null
/* READ AGAIN ONLY IF THE RECORD MOVED (the owner's slowdown, 2026-10-25):
   this summary is ~0.7 s of the server's time and was read on every opening
   of the sheet, so picking a conversation raced its own posts' read against
   it. Held with the change cursor it was read at, it is read again only once
   the record has moved past that -- or `TOPICS_FRESH_MS` has gone by. */
let topicsAt: { cursor: string | null; t: number } | null = null
const TOPICS_FRESH_MS = 60000
function useTopics(): Map<Id, Topic[]> {
  const [got, setGot] = useState(topicsHeld)
  useEffect(() => {
    let live = true
    if (topicsHeld && topicsAt && topicsAt.cursor === store.cursor && Date.now() - topicsAt.t < TOPICS_FRESH_MS) return
    const at = { cursor: store.cursor, t: Date.now() }
    void fetch('/api/conversations', { headers: { ...CLIENT_HEADERS } })
      .then((r) => (r.ok ? r.json() : null))
      .then((b: { conversations?: { id: Id; topics?: Topic[] }[] } | null) => {
        if (!b?.conversations) return
        topicsHeld = new Map(b.conversations.map((c) => [c.id, (c.topics ?? []).filter((t) => t && t.name)]))
        topicsAt = at
        if (live) setGot(topicsHeld)
      })
      .catch(() => {})
    return () => { live = false }
  }, [])
  return got ?? new Map()
}

const plural = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`

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
  const topicsOf = useTopics()
  const [q, setQ] = useState('')
  const [all, setAll] = useState(false)
  const [expanded, setExpanded] = useState<Set<Id>>(() => new Set())
  const [at, setAt] = useState(0)
  const input = useRef<HTMLInputElement>(null)
  const box = useRef<HTMLDivElement>(null)
  useEffect(() => { void store.loadListIfMoved() }, [])
  useEffect(() => {
    const t = setTimeout(() => input.current?.focus(), 50)
    return () => clearTimeout(t)
  }, [])
  const want = q.trim().toLowerCase()
  const convs = (list ?? []).filter((c: Conversation) => c.id !== 'home' && c.name?.toLowerCase() !== 'home')

  /* What is drawn, in order: the rows a key can reach. */
  const { recent, rest, rows } = useMemo(() => {
    const conv = (c: Conversation, open: boolean, only?: Topic[]): Row[] => {
      const topics = topicsOf.get(c.id) ?? []
      const out: Row[] = [{ kind: 'conv', c, topics, open }]
      if (open) for (const t of only ?? topics) out.push({ kind: 'topic', c, t })
      return out
    }
    if (want) {
      const found: Row[] = []
      for (const c of convs) {
        const nameHit = c.name.toLowerCase().includes(want)
        const hits = (topicsOf.get(c.id) ?? []).filter((t) => t.name.toLowerCase().includes(want))
        if (!nameHit && !hits.length) continue
        found.push(...conv(c, hits.length > 0, hits))
      }
      return { recent: found, rest: [] as Row[], rows: found }
    }
    const recent = convs.slice(0, RECENT).flatMap((c) => conv(c, expanded.has(c.id)))
    const rest = all ? convs.slice(RECENT).flatMap((c) => conv(c, expanded.has(c.id))) : []
    const fold: Row[] = convs.length > RECENT ? [{ kind: 'fold' }] : []
    return { recent, rest, rows: [...recent, ...fold, ...rest] }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [list, topicsOf, want, all, expanded])
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
            <span>All conversations</span><small>{all ? 'fewer' : `${convs.length - RECENT} more ▸`}</small>
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
      <li key={c.id} className="fw-conv-row">
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
                {c.working ? ` · ${c.working} working` : ''}
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
      </li>
    )
  }

  let i = -1
  const next = () => ++i
  return (
    <div className="fw-switch" ref={box} onKeyDown={onKey}>
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
        {!want && convs.length > RECENT && draw({ kind: 'fold' }, next())}
        {rest.map((r) => draw(r, next()))}
      </ul>
    </div>
  )
}
