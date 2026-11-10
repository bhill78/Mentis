/* THE GLOBAL DOCK: Mentis at a glance, one for the whole page.
 *
 * A small glass pill at the foot of the right margin, clear of the composer
 * and of the topic rail. Collapsed it holds ONE Activity control, its badge
 * counting only what needs the owner, and a launcher that reveals Search and
 * Settings. Activity opens one panel with four tabs -- Needs you, Working,
 * Recent, Capacity -- on Needs you while anything waits, else on the tab last
 * used. Every entry with a source goes to it (the post, or the thread a run
 * answered) or opens it beside, in a free working column. Esc closes the
 * panel, then collapses the pill, and focus goes back to what opened it.
 *
 * NOTHING HERE IS NEW DATA. Every panel is a read Fluid already makes:
 *   Needs you  the bell's list, one item per form (`needs-you/items`,
 *              store.loadNeedsItems -- the same answer the bell counts)
 *   Working    Mentis's activity (`/api/activity`, presence.ts useWorking)
 *   Recent     Home's Activity: the latest runs (`home/activity`, then
 *              `runs?ids=`, store.loadHomeActivity / store.runs)
 *   Capacity   `/api/capacity` (composer/execution.ts useCapacity). Reading
 *              it RECORDS a capacity reading, so it is asked only when the
 *              panel is opened, and never on a read-only page.
 *   Search     the record's own search (`/api/references`, search.ts useSearch)
 * Only GETs. Nothing here writes. */
import { useCallback, useEffect, useId, useRef, useState, useSyncExternalStore } from 'react'
import { ago } from '../api'
import { capacityMeters, readAgo, useCapacity, type RuntimeCapacity } from '../composer/execution'
import { Avatar } from '../fluid/identity/Who'
import { store, type Id, type RunItem } from '../fluid/store'
import { itemLine, type NeedsItems } from '../needsItems'
import { isTurn, useSearch, type Hit } from '../search'
import { READ_ONLY } from './live'
import { useWorking, type Working } from './presence'
import { repairText } from './text'
import './dock.css'

export type DockPanel = 'activity' | 'search'
type Open = DockPanel | 'settings'
export type ActivityTab = 'needs' | 'working' | 'recent' | 'capacity'

type OpenConversation = (conversation: string, post?: string, number?: number) => void
/** opens a source beside the conversation, in a free working column */
type OpenBeside = ((conversation: string, post?: string) => void) | null

const TITLES: Record<Open, string> = { activity: 'Activity', search: 'Search', settings: 'Settings' }
const TABS: { id: ActivityTab; label: string }[] = [
  { id: 'needs', label: 'Needs you' }, { id: 'working', label: 'Working' }, { id: 'recent', label: 'Recent' }, { id: 'capacity', label: 'Capacity' },
]
/** the tab last chosen, for the next time Activity opens with nothing waiting */
let lastTab: ActivityTab = 'needs'

/* -- shared reads ---------------------------------------------------------- */

const NEEDS_REREAD = 60000

/** The bell's items (store.needsItems), read once, again every minute while
 *  the page is looked at, and whenever the store's own change loop moves them. */
function useNeedsItems(): { got: NeedsItems | null; error: string | null; reread: () => void } {
  const sub = useCallback((fn: () => void) => store.subscribe('needs-items', fn), [])
  const got = useSyncExternalStore(sub, () => store.needsItems)
  const [error, setError] = useState<string | null>(null)
  const reread = useCallback(() => {
    store.loadNeedsItems().then(() => setError(null), (e: unknown) => setError(String(e instanceof Error ? e.message : e)))
  }, [])
  useEffect(() => {
    if (store.needsItems === null) reread()
    const t = window.setInterval(() => { if (document.visibilityState === 'visible') reread() }, NEEDS_REREAD)
    return () => window.clearInterval(t)
  }, [reread])
  return { got, error, reread }
}

const convName = (id: Id | null | undefined, given?: string | null) =>
  repairText(given || (id ? store.conversations.get(id)?.name ?? '' : '')) || (id ? 'A conversation' : 'No conversation')

/* -- icons (stroke, currentColor) ----------------------------------------- */

const ICON: Record<Open | 'more', React.ReactNode> = {
  activity: <><path d="M4 9.5a4 4 0 0 1 8 0V12l1.2 1.6H2.8L4 12z" /><path d="M6.6 15.2a1.5 1.5 0 0 0 2.8 0" /></>,
  search: <><circle cx="7" cy="7" r="4.4" /><path d="M10.3 10.3L14 14" /></>,
  settings: <><circle cx="8" cy="8" r="2.2" /><path d="M8 1.6v2M8 12.4v2M1.6 8h2M12.4 8h2M3.5 3.5l1.4 1.4M11.1 11.1l1.4 1.4M3.5 12.5l1.4-1.4M11.1 4.9l1.4-1.4" /></>,
  more: <><circle cx="3.2" cy="8" r="1.1" /><circle cx="8" cy="8" r="1.1" /><circle cx="12.8" cy="8" r="1.1" /></>,
}
const Icon = ({ name }: { name: Open | 'more' }) => (
  <svg className="q2-gdock-icon" viewBox="0 0 16 16" width="16" height="16" aria-hidden="true" focusable="false"
    fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round">{ICON[name]}</svg>
)

/* -- the panels' bodies ---------------------------------------------------- */

function Note({ children, alert }: { children: React.ReactNode; alert?: boolean }) {
  return <li className="q2-gdock-note" role={alert ? 'alert' : undefined}>{children}</li>
}

function Row({ name, meta, onOpen, lead, onBeside, goWords = 'Go to post' }: {
  name: string; meta: string; onOpen?: () => void; lead?: React.ReactNode
  /** opens the source beside the conversation; absent where there is no column or no source */
  onBeside?: () => void
  goWords?: string
}) {
  const body = <>
    {lead}
    <span className="q2-gdock-row-text">
      <span className="q2-gdock-name">{name}</span>
      <span className="q2-gdock-meta">{meta}</span>
    </span>
  </>
  return <li className="q2-gdock-item">{onOpen
    ? <button type="button" className="q2-gdock-row" onClick={onOpen} title={goWords}>{body}</button>
    : <div className="q2-gdock-row q2-gdock-row-still">{body}</div>}
    {onBeside && <button type="button" className="q2-gdock-row-beside" onClick={onBeside} title="Open beside, in a working column" aria-label={`Open beside: ${name}`}>⇥</button>}
  </li>
}

function NeedsBody({ go, beside }: { go: OpenConversation; beside: OpenBeside }) {
  const { got, error, reread } = useNeedsItems()
  useEffect(() => { reread() }, [reread])
  if (got?.unknown) return <ul className="q2-gdock-list"><Note>Could not tell what needs you: {got.why ?? 'the Brain did not say who the owner is'}.</Note></ul>
  const items = got?.items ?? []
  return (
    <ul className="q2-gdock-list">
      {got && got.words && <li className="q2-gdock-sum">{got.words}</li>}
      {items.map((it) => {
        const { kind, what } = itemLine(it)
        const where = [convName(it.conversation, it.conversation_name), it.post_number != null ? `#${it.post_number}` : null].filter(Boolean).join(' · ')
        const asker = it.asked_by_name ? it.asked_by_name.replace(/^@?/, '@') : null
        return <Row key={it.key} name={repairText(what)}
          meta={[kind, asker, where, it.at ? ago(it.at) : null].filter(Boolean).join(' · ')}
          onOpen={it.conversation ? () => go(it.conversation!, it.post ?? undefined, it.post_number ?? undefined) : undefined}
          onBeside={it.conversation && beside ? () => beside(it.conversation!, it.post ?? undefined) : undefined} />
      })}
      {got && !items.length && <Note>Nothing needs you.</Note>}
      {!got && !error && <Note>Reading what needs you…</Note>}
      {error && <Note alert>Could not read what needs you: {error}</Note>}
    </ul>
  )
}

function WorkingBody({ go, beside, working }: { go: OpenConversation; beside: OpenBeside; working: Working[] }) {
  return (
    <ul className="q2-gdock-list">
      {working.map((w) => (
        <Row key={w.key} name={w.alias.replace(/^@/, '')}
          lead={<span className="q2-pulse q2-gdock-avatar"><Avatar id={w.participant} name={w.alias} size={20} runtime={w.runtime ?? undefined} /></span>}
          meta={[w.doing, w.conversation ? convName(w.conversation) : 'not in a conversation', w.number != null ? `#${w.number}` : null].filter(Boolean).join(' · ')}
          onOpen={w.conversation ? () => go(w.conversation!, w.post ?? undefined, w.number ?? undefined) : undefined}
          onBeside={w.conversation && beside ? () => beside(w.conversation!, w.post ?? undefined) : undefined} />
      ))}
      {!working.length && <Note>Nobody is working right now.</Note>}
    </ul>
  )
}

function RunRow({ id, go, beside }: { id: Id; go: OpenConversation; beside: OpenBeside }) {
  const sub = useCallback((fn: () => void) => store.subscribe('run:' + id, fn), [id])
  const run: RunItem | undefined = useSyncExternalStore(sub, () => store.runs.get(id))
  if (!run) return <Note>Reading a run…</Note>
  if (run.error) return <Note>A run could not be read: {run.error}</Note>
  const who = (run.participant_name || run.participant).replace(/^@/, '')
  const meta = [run.state, run.runtime, convName(run.conversation), ago(run.ended_at ?? run.started_at)].filter(Boolean).join(' · ')
  return <Row name={run.activity && run.state === 'running' ? `${who}: ${run.activity}` : who} meta={meta}
    lead={<span className="q2-gdock-avatar"><Avatar id={run.participant} name={who} size={20} runtime={run.runtime ?? undefined} /></span>}
    goWords="Go to the request this run answered (its result is a reply there)"
    onOpen={run.conversation ? () => go(run.conversation, run.post || undefined) : undefined}
    onBeside={run.conversation && beside ? () => beside(run.conversation, run.post || undefined) : undefined} />
}

function RecentBody({ go, beside }: { go: OpenConversation; beside: OpenBeside }) {
  const sub = useCallback((fn: () => void) => store.subscribe('coll:home:activity', fn), [])
  const data = useSyncExternalStore(sub, () => store.homeActivity)
  const [error, setError] = useState<string | null>(null)
  useEffect(() => {
    store.loadHomeActivity().then(() => setError(null), (e: unknown) => setError(String(e instanceof Error ? e.message : e)))
  }, [])
  const items = data?.items ?? []
  return (
    <ul className="q2-gdock-list">
      {items.map((id) => <RunRow key={id} id={id} go={go} beside={beside} />)}
      {data && !items.length && <Note>No agent has run recently.</Note>}
      {!data && !error && <Note>Reading recent runs…</Note>}
      {error && <Note alert>Could not read recent runs: {error}</Note>}
    </ul>
  )
}

const READ_ONLY_CAPACITY = 'Capacity is not read in the read-only view: reading it records a capacity reading in the Brain.'

function CapacityRuntime({ name, c }: { name: string; c: RuntimeCapacity }) {
  const meters = capacityMeters(c)
  const read = readAgo(c.observed_at)
  return (
    <li className="q2-gdock-cap">
      <div className="q2-gdock-cap-head">
        <span className="q2-gdock-name">{name}</span>
        <span className="q2-gdock-meta">{[c.plan, read].filter(Boolean).join(' · ')}</span>
      </div>
      {!c.established && <p className="q2-gdock-meta">Not established{c.why_not ? `: ${c.why_not}` : ''}</p>}
      {c.established && !meters.length && <p className="q2-gdock-meta">{c.local ? 'A local runtime: no quota.' : 'It reported no usage windows.'}</p>}
      {meters.map((m) => (
        <div key={`${m.group ?? ''}:${m.label}`} className="q2-gdock-meter" data-level={m.level ?? 'unknown'}>
          <span className="q2-gdock-meter-name">{m.group ? `${m.group} ${m.name}` : m.name}</span>
          <span className="q2-gdock-meter-bar" aria-hidden="true"><b style={{ width: `${Math.round((m.left ?? 0) * 100)}%` }} /></span>
          <span className="q2-gdock-meter-said">{m.stale ? 'reset since read' : `${Math.round((m.left ?? 0) * 100)}% left${m.resets ? ` · resets in ${m.resets}` : ''}`}</span>
        </div>
      ))}
    </li>
  )
}

function CapacityReader() {
  const { data, error, loading } = useCapacity(true)
  const runtimes = Object.entries(data?.capacity ?? {})
  return (
    <ul className="q2-gdock-list" aria-busy={loading || undefined}>
      {runtimes.map(([name, c]) => <CapacityRuntime key={name} name={name} c={c} />)}
      {data && !runtimes.length && <Note>No runtime reported its capacity.</Note>}
      {!data && !error && <Note>Asking each runtime what it has left… (this takes a few seconds)</Note>}
      {error && <Note alert>Could not read capacity: {error}</Note>}
    </ul>
  )
}

/* The read-only check is made before the reader exists, so a read-only page
   never mounts `useCapacity` and never asks. */
function CapacityBody() {
  const [asked, setAsked] = useState(false)
  if (READ_ONLY) return <ul className="q2-gdock-list"><Note>{READ_ONLY_CAPACITY}</Note></ul>
  if (!asked) return (
    <ul className="q2-gdock-list">
      <Note>Reading capacity asks every runtime what it has left, and the Brain records each reading.</Note>
      <li><button type="button" className="q2-gdock-more" onClick={() => setAsked(true)}>Read capacity now</button></li>
    </ul>
  )
  return <CapacityReader />
}

const hitName = (h: Hit) => repairText(h.said || h.name || h.ref)

function SearchBody({ go, autoFocus }: { go: OpenConversation; autoFocus: boolean }) {
  const [q, setQ] = useState('')
  const { session, loading, more, error, typed, loadMore } = useSearch(q, null)
  const input = useRef<HTMLInputElement>(null)
  useEffect(() => { if (autoFocus) input.current?.focus() }, [autoFocus])
  const current = session && session.q === typed ? session : null
  const rows = current?.rows ?? []
  const shown = rows.filter((h) => isTurn(h) || h.what === 'conversation')
  const elsewhere = rows.length - shown.length
  return (
    <>
      <input ref={input} type="search" className="q2-gdock-search" value={q} onChange={(e) => setQ(e.target.value)}
        placeholder="Search Mentis: words, a post number, ent-…" aria-label="Search Mentis"
        onKeyDown={(e) => { if (e.key === 'Escape' && q) { e.preventDefault(); e.stopPropagation(); setQ('') } }} />
      <ul className="q2-gdock-list" aria-busy={loading || more || undefined}>
        {shown.map((h) => isTurn(h)
          ? <Row key={h.ref} name={hitName(h)}
              meta={[convName(h.conversation, h.conversation_name), h.number != null ? `#${h.number}` : null].filter(Boolean).join(' · ')}
              onOpen={() => go(h.conversation!, h.ref, h.number ?? undefined)} />
          : <Row key={h.ref} name={repairText(h.name || h.said || h.ref)} meta="Conversation" onOpen={() => go(h.ref)} />)}
        {current && elsewhere > 0 && <Note>Also {elsewhere} {elsewhere === 1 ? 'topic, person or link' : 'topics, people or links'}: not opened from here.</Note>}
        {current && !rows.length && <Note>Nothing matches “{current.q}”.</Note>}
        {current && !current.done && <li><button type="button" className="q2-gdock-more" onClick={loadMore} disabled={more}>{more ? 'Searching…' : 'More results'}</button></li>}
        {!typed && <Note>Type two or more characters.</Note>}
        {typed && !current && loading && <Note>Searching…</Note>}
        {error && <Note alert>{error.kind === 'more' ? 'Could not read more' : 'Could not search'}: {error.message}</Note>}
      </ul>
    </>
  )
}

/* ACTIVITY: four tabs over the reads above. The Working tab says how many
   are working; the dock's badge counts only what needs the owner. */
function ActivityBody({ tab, setTab, go, beside, working, needCount }: {
  tab: ActivityTab; setTab: (t: ActivityTab) => void; go: OpenConversation; beside: OpenBeside; working: Working[]; needCount: number | null
}) {
  const tabsId = useId()
  const counts: Partial<Record<ActivityTab, number | null>> = { needs: needCount, working: working.length }
  const choose = (t: ActivityTab) => { lastTab = t; setTab(t) }
  return (
    <>
      <div className="q2-gdock-tabs" role="tablist" aria-label="Activity"
        onKeyDown={(e) => {
          if (e.key !== 'ArrowRight' && e.key !== 'ArrowLeft') return
          e.preventDefault()
          const i = TABS.findIndex((x) => x.id === tab)
          const next = TABS[(i + (e.key === 'ArrowRight' ? 1 : TABS.length - 1)) % TABS.length].id
          choose(next)
          const list = e.currentTarget
          requestAnimationFrame(() => (list.querySelector(`[data-tab="${next}"]`) as HTMLElement | null)?.focus())
        }}>
        {TABS.map((t) => (
          <button key={t.id} type="button" role="tab" data-tab={t.id} id={`${tabsId}-${t.id}`} aria-selected={tab === t.id}
            aria-controls={`${tabsId}-panel`} tabIndex={tab === t.id ? 0 : -1} className={'q2-gdock-tab' + (tab === t.id ? ' on' : '')}
            onClick={() => choose(t.id)}>
            {t.label}{counts[t.id] ? <span className="q2-gdock-tab-n">{counts[t.id]}</span> : null}
          </button>
        ))}
      </div>
      <div role="tabpanel" id={`${tabsId}-panel`} aria-labelledby={`${tabsId}-${tab}`} className="q2-gdock-tabpanel">
        {tab === 'needs' && <NeedsBody go={go} beside={beside} />}
        {tab === 'working' && <WorkingBody go={go} beside={beside} working={working} />}
        {tab === 'recent' && <RecentBody go={go} beside={beside} />}
        {tab === 'capacity' && <CapacityBody />}
      </div>
    </>
  )
}

/** The tab Activity opens on: Needs you while anything waits, else the last used. */
const firstTab = (needCount: number | null): ActivityTab => (needCount ? 'needs' : lastTab)
/** the tab being shown, kept as the last used */
const showTab = (set: (t: ActivityTab) => void) => (t: ActivityTab) => { lastTab = t; set(t) }

/** The same content as the dock's panel, for a working column. */
export function DockPanelBody({ panel, onOpenConversation, onOpenBeside = null, inSurface }: {
  panel: DockPanel
  onOpenConversation: OpenConversation
  onOpenBeside?: OpenBeside
  inSurface?: boolean
}) {
  const working = useWorking(false)
  const needs = useNeedsItems().got
  const needCount = needs?.counts?.total ?? needs?.items.length ?? null
  /* a column opens on the tab the dock was showing */
  const [tab, setTab] = useState<ActivityTab>(() => lastTab)
  return (
    <div className={'q2-gdock-body' + (inSurface ? ' q2-gdock-in-surface' : '')} data-panel={panel}>
      {panel === 'activity' && <ActivityBody tab={tab} setTab={showTab(setTab)} go={onOpenConversation} beside={onOpenBeside} working={working} needCount={needCount} />}
      {panel === 'search' && <SearchBody go={onOpenConversation} autoFocus={!inSurface} />}
    </div>
  )
}

/* -- the dock --------------------------------------------------------------- */

export default function GlobalDock({ settings, onOpenInSurface, onOpenConversation, onOpenBeside }: {
  settings: React.ReactNode
  onOpenInSurface: ((panel: DockPanel) => void) | null
  onOpenConversation: (conversation: string, post?: string, number?: number) => void
  /** a source opened beside the conversation; null where there is no working column */
  onOpenBeside: OpenBeside
}) {
  const [open, setOpen] = useState<Open | null>(null)
  const [tab, setTab] = useState<ActivityTab>('needs')
  const [expanded, setExpanded] = useState(false)
  const root = useRef<HTMLDivElement>(null)
  const panelRef = useRef<HTMLDivElement>(null)
  const opener = useRef<HTMLButtonElement | null>(null)
  const launcher = useRef<HTMLButtonElement>(null)
  const panelId = useId()
  const working = useWorking(false)
  const needs = useNeedsItems().got
  const needCount = needs?.counts?.total ?? needs?.items.length ?? null

  const close = useCallback((refocus = true) => {
    setOpen(null)
    if (refocus && opener.current?.isConnected) opener.current.focus()
  }, [])

  /* Esc closes the panel, then collapses; a press outside closes the panel */
  useEffect(() => {
    if (!open && !expanded) return
    const esc = (e: KeyboardEvent) => {
      if (e.key !== 'Escape' || e.defaultPrevented) return
      const inside = root.current?.contains(document.activeElement)
      if (!inside) return
      if (open) { e.preventDefault(); close(true); return }
      if (expanded) { e.preventDefault(); setExpanded(false); launcher.current?.focus() }
    }
    const away = (e: PointerEvent) => { if (open && !root.current?.contains(e.target as Node) && !(e.target as Element).closest?.('#fx-layer')) close(false) }
    document.addEventListener('keydown', esc); document.addEventListener('pointerdown', away)
    return () => { document.removeEventListener('keydown', esc); document.removeEventListener('pointerdown', away) }
  }, [open, expanded, close])

  /* an opened panel takes focus (search focuses its own field) */
  useEffect(() => {
    if (!open || open === 'search') return
    panelRef.current?.focus()
  }, [open])

  const pick = (p: Open, el: HTMLButtonElement) => {
    if (open === p) { close(true); return }
    opener.current = el
    if (p === 'activity') showTab(setTab)(firstTab(needCount))
    setOpen(p)
  }
  const go: OpenConversation = (c, post, number) => { close(false); onOpenConversation(c, post, number) }
  const beside: OpenBeside = onOpenBeside ? (c, post) => { close(false); onOpenBeside(c, post) } : null

  const btn = (p: Open, label: string, extra?: React.ReactNode) => (
    <button type="button" className={'q2-gdock-btn' + (open === p ? ' on' : '')} data-panel={p}
      aria-label={label} title={label} aria-expanded={open === p} aria-controls={open === p ? panelId : undefined}
      onClick={(e) => pick(p, e.currentTarget)}>
      <Icon name={p} />{extra}
    </button>
  )

  /* the badge is what needs the owner, and only that */
  const activityLabel = `Activity${needCount ? ` · needs you: ${needs?.words || needCount}` : ''}`

  return (
    <div className={'q2-gdock' + (expanded ? ' expanded' : '') + (open ? ' has-panel' : '')} ref={root}>
      {open && (
        <div className="q2-gdock-panel" id={panelId} role="dialog" aria-label={TITLES[open]} ref={panelRef} tabIndex={-1}>
          <header className="q2-gdock-head">
            <h2>{TITLES[open]}</h2>
            {open !== 'settings' && onOpenInSurface && (
              <button type="button" className="q2-gdock-beside" title="Open in a working column" aria-label={`Open ${TITLES[open]} in a working column`}
                onClick={() => { const p = open as DockPanel; close(false); onOpenInSurface(p) }}>⇥</button>
            )}
            <button type="button" className="q2-gdock-close" onClick={() => close(true)} aria-label="Close" title="Close">×</button>
          </header>
          {open === 'settings'
            ? <div className="q2-settings-body q2-gdock-settings">{settings}</div>
            : open === 'activity'
            ? <div className="q2-gdock-body" data-panel="activity"><ActivityBody tab={tab} setTab={showTab(setTab)} go={go} beside={beside} working={working} needCount={needCount} /></div>
            : <DockPanelBody panel={open} onOpenConversation={go} onOpenBeside={beside} />}
        </div>
      )}
      <div className="q2-gdock-pill" role="toolbar" aria-label="Mentis">
        {btn('activity', activityLabel, needCount ? <span className="q2-gdock-badge">{needCount > 99 ? '99+' : needCount}</span> : null)}
        {expanded && <>
          {btn('search', 'Search Mentis')}
          {btn('settings', 'Settings')}
        </>}
        <button type="button" ref={launcher} className={'q2-gdock-btn q2-gdock-launch' + (expanded ? ' on' : '')}
          aria-expanded={expanded} aria-label={expanded ? 'Fewer controls' : 'More: Search, Settings'}
          title={expanded ? 'Fewer controls' : 'More: Search, Settings'}
          onClick={() => {
            if (expanded && open && open !== 'activity') setOpen(null)
            setExpanded(!expanded)
          }}>
          <Icon name="more" />
        </button>
      </div>
    </div>
  )
}
