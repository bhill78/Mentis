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
 *   Working    Mentis's activity (`/api/activity`, Fluid's one reader,
 *              identity/activity.ts useActivity): every open run, and
 *              `runs?ids=` for its runtime, model and start
 *   Recent     Home's Activity: the latest runs (`home/activity`, then
 *              `runs?ids=`, store.loadHomeActivity / store.runs), each with
 *              the request post it answered (`posts?ids=`)
 *   Capacity   `/api/capacity` (composer/execution.ts useCapacity). Reading
 *              it RECORDS a capacity reading, so it is asked only on request,
 *              and never on a read-only page. Beside it, each runtime's
 *              availability as `/api/execution` says it (installed or not,
 *              each Execution Mode supported, unsupported, unverified or
 *              temporarily unavailable, with why): asked on the same request.
 *   Search     the record's own search (`/api/references`, search.ts useSearch)
 *
 * KEPT CURRENT THE WAY FLUID KEEPS ITS BELL: the store's change loop
 * (`store.follow`, `/fluid/api/changes` on Fluid's one pulse) rereads the
 * Needs you items, Home's Activity and every run held whenever the record
 * says they moved; who is working rereads on the same pulse. Nothing here
 * polls on a clock of its own but the bell's one-minute fallback.
 *
 * Only GETs, except an answer given through Fluid's own decision form,
 * which the owner sends (never offered on a read-only page). */
import { lazy, Suspense, useCallback, useEffect, useId, useRef, useState, useSyncExternalStore } from 'react'
import { ago } from '../api'
import { capacityMeters, localServerSays, readAgo, useCapacity, useExecution, windowName, type RuntimeCapacity, type RuntimeChoice } from '../composer/execution'
import { Avatar } from '../fluid/identity/Who'
import { useActivity, type Activity, type ActivityRun } from '../fluid/identity/activity'
import { store, type Id } from '../fluid/store'
import { itemLine, type NeedsItem, type NeedsItems } from '../needsItems'
import { isTurn, useSearch, type Hit } from '../search'
import { READ_ONLY } from './live'
import { useWorking, type Working } from './presence'
import { repairText } from './text'
import { forgetPassage, onSaved, revealPassage, savedPassages, type SavedPassage } from './annotate/passage'
import { ACTIVE, availabilityLines, firstLine, isEnded, PLAIN_END, runStateWord, runtimeModel, stateWords, useConvName, usePost, useRun, useRunModes, type Run } from './activity/records'
import './dock.css'

export type DockPanel = 'activity' | 'search' | 'saved'
type Open = DockPanel | 'settings'
export type ActivityTab = 'needs' | 'working' | 'recent' | 'capacity'

type OpenConversation = (conversation: string, post?: string, number?: number) => void
/** opens a source beside the conversation, in a free working column */
type OpenBeside = ((conversation: string, post?: string) => void) | null

const TITLES: Record<Open, string> = { activity: 'Activity', search: 'Search', saved: 'Saved passages', settings: 'Settings' }
const TABS: { id: ActivityTab; label: string }[] = [
  { id: 'needs', label: 'Needs you' }, { id: 'working', label: 'Working' }, { id: 'recent', label: 'Recent' }, { id: 'capacity', label: 'Capacity' },
]
/** the tab last chosen, for the next time Activity opens with nothing waiting */
let lastTab: ActivityTab = 'needs'

/* -- shared reads ---------------------------------------------------------- */

const NEEDS_REREAD = 60000

/** Fluid's change loop, as its Shell starts it: once for the page, and it
 *  stays (the store offers no stop; Fluid's own page never stops it either). */
const following = () => store.follow()

/** The bell's items (store.needsItems), read once, again every minute while
 *  the page is looked at, and whenever the store's own change loop moves them. */
function useNeedsItems(): { got: NeedsItems | null; error: string | null; reread: () => void } {
  useEffect(following, [])
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
  saved: <><path d="M4.5 2.5h7v11L8 11l-3.5 2.5z" /></>,
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

/** A heading over part of a list, with how many are under it. */
const Group = ({ children }: { children: React.ReactNode }) => <li className="q2-gdock-group">{children}</li>

/** When something happened, in full, for a row's title. */
const at = (t: number | null | undefined) => (t ? new Date(t * 1000).toLocaleString() : null)

function Row({ name, meta, onOpen, lead, onBeside, goWords = 'Go to post', kicker, state, after, title }: {
  name: string
  /** one line, or several (empty ones are left out) */
  meta: string | (string | null | false | undefined)[]
  onOpen?: () => void; lead?: React.ReactNode
  /** opens the source beside the conversation; absent where there is no column or no source */
  onBeside?: () => void
  goWords?: string
  /** what kind of entry, or its state, above its name */
  kicker?: string | null
  /** the record's state, for colour (`data-state`) */
  state?: string
  /** drawn under the row, across it: an answer form */
  after?: React.ReactNode
  title?: string
}) {
  const lines = (Array.isArray(meta) ? meta : [meta]).filter((m): m is string => !!m)
  const body = <>
    {lead}
    <span className="q2-gdock-row-text">
      {kicker && <span className="q2-gdock-kicker" data-state={state}>{kicker}</span>}
      <span className="q2-gdock-name">{name}</span>
      {lines.map((m, i) => <span key={i} className="q2-gdock-meta">{m}</span>)}
    </span>
  </>
  return <li className="q2-gdock-item" data-state={state}>{onOpen
    ? <button type="button" className="q2-gdock-row" onClick={onOpen} title={title ? `${goWords}\n${title}` : goWords}>{body}</button>
    : <div className="q2-gdock-row q2-gdock-row-still" title={title}>{body}</div>}
    {onBeside && <button type="button" className="q2-gdock-row-beside" onClick={onBeside} title="Open beside, in a working column" aria-label={`Open beside: ${name}`}>⇥</button>}
    {after && <div className="q2-gdock-after">{after}</div>}
  </li>
}

/* NEEDS YOU: the bell's items, one per form, each only while it is open --
   the server lists what is outstanding and nothing else, so an answered or
   withdrawn form leaves the list (and the badge) on the next read. A
   decision can be answered here, with Fluid's own decision form
   (experimental/types/decision.tsx `DecisionsOn`, the one its Needs You zone
   draws), loaded only when asked for; every item also goes to its asking
   post. Never on a read-only page. */
const DecisionsOn = lazy(() => import('../experimental/types/decision').then((m) => ({ default: m.DecisionsOn })))

function AnswerHere({ it }: { it: NeedsItem }) {
  const [open, setOpen] = useState(false)
  const n = it.asks.length
  return <>
    <button type="button" className="q2-gdock-more" aria-expanded={open} onClick={() => setOpen(!open)}
      aria-label={`${open ? 'Hide the form for' : 'Answer here'}: ${repairText(itemLine(it).what).slice(0, 80)}`}>
      {open ? 'Hide the form' : n > 1 ? `Answer here (${n} questions)` : 'Answer here'}
    </button>
    {open && it.post && (
      <div className="q2-gdock-answer">
        <Suspense fallback={<p className="q2-gdock-meta">Reading the decision form…</p>}>
          <DecisionsOn post={it.post} only={it.asks}
            onChanged={() => { void store.step().catch(() => {}).then(() => store.loadNeedsItems()).catch(() => {}) }} />
        </Suspense>
      </div>
    )}
  </>
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
        /* the asking post's first line, where the name is the question */
        const on = it.question && it.lead ? `on “${repairText(it.lead)}”` : null
        return <Row key={it.key} kicker={kind} state={it.kind} name={repairText(what)}
          meta={[[asker ? `asked by ${asker}` : null, it.at ? ago(it.at) : null].filter(Boolean).join(' · '), [where, on].filter(Boolean).join(' ')]}
          title={[it.because ? `Because: ${repairText(it.because)}` : null, at(it.at)].filter(Boolean).join('\n') || undefined}
          goWords="Go to the asking post"
          onOpen={it.conversation ? () => go(it.conversation!, it.post ?? undefined, it.post_number ?? undefined) : undefined}
          onBeside={it.conversation && beside ? () => beside(it.conversation!, it.post ?? undefined) : undefined}
          after={!READ_ONLY && it.kind === 'decision' && it.post ? <AnswerHere it={it} /> : undefined} />
      })}
      {got && !items.length && <Note>Nothing needs you.</Note>}
      {!got && !error && <Note>Reading what needs you…</Note>}
      {error && <Note alert>Could not read what needs you: {error}</Note>}
    </ul>
  )
}

/* WORKING: every run the record says is open, from Mentis's activity
   (`/api/activity`, Fluid's one reader, reread as the pulse moves), one
   entry per run. Those this server holds are working now (`live`); an open
   run no process here holds is said as exactly that, never as working and
   never as dead. A run that ends leaves at the next reread, into Recent. */
interface WorkEntry {
  key: string
  participant: Id
  alias: string
  runtime: string | null
  run: ActivityRun | null
  live: boolean
  conversation: Id | null
  post: Id | null
  number: number | null
  since: number | null
}

function workEntries(all: Activity[] | null): WorkEntry[] {
  const out: WorkEntry[] = []
  for (const a of all ?? []) {
    const runs = a.runs ?? []
    for (const r of runs) {
      out.push({ key: r.run, participant: a.participant, alias: a.alias, runtime: null, run: r, live: !!r.live,
        conversation: r.conversation ?? r.working_on?.conversation ?? null, post: r.working_on?.turn ?? r.turn ?? null,
        number: r.working_on?.number ?? null, since: r.working_on?.since ?? null })
    }
    /* a live execution no live run accounts for (one begun without a dispatch), as `live` counts it */
    if (a.has_live_execution && !runs.some((r) => r.live)) {
      out.push({ key: a.participant, participant: a.participant, alias: a.alias, runtime: a.runtime ?? null, run: null, live: true,
        conversation: a.conversation ?? a.working_on?.conversation ?? null, post: a.working_on?.turn ?? null,
        number: a.working_on?.number ?? null, since: a.working_on?.since ?? null })
    }
  }
  return out.sort((x, y) => Number(y.live) - Number(x.live) || (y.since ?? 0) - (x.since ?? 0))
}

function WorkRow({ e, go, beside }: { e: WorkEntry; go: OpenConversation; beside: OpenBeside }) {
  const run = useRun(e.run?.run)
  const conv = useConvName(e.conversation)
  const r = e.run
  const who = e.alias.replace(/^@/, '')
  const waiting = !!(r?.permission || r?.permissions?.length)
  const active = e.live && (!r || ACTIVE.has(r.state))
  /* the state as the server words it; Fluid's own "waiting for you" and "Stopping…" beside it */
  const kicker = [r ? r.state : 'live execution', waiting ? 'waiting for you' : null, r?.stopping ? 'Stopping…' : null, e.live ? null : 'not held here'].filter(Boolean).join(' · ')
  const started = run?.started_at ?? e.since
  /* its Permission and Execution, as the server says them; enforcement said
     only as the server says it, never as enforced unless it is */
  const modes = useRunModes(e.run?.run)
  const enf = modes?.enforcement
  return <Row key={e.key} kicker={kicker} state={waiting ? 'waiting' : active ? 'running' : r?.state ?? 'running'}
    name={r?.activity && e.live ? `${who}: ${repairText(r.activity)}` : who}
    lead={<span className={(active ? 'q2-pulse ' : '') + 'q2-gdock-avatar'}><Avatar id={e.participant} name={e.alias} size={20} runtime={run?.runtime ?? e.runtime ?? undefined} /></span>}
    meta={[
      /* the server's words; the start it may end with is said on the next line */
      r?.words ? repairText(r.words).replace(/\s*·\s*started [\d-]+ [\d:]+$/, '') : e.run ? null : 'a live execution no dispatched run accounts for',
      [runtimeModel(run?.runtime ?? e.runtime, run?.model), started ? `started ${ago(started)}` : null].filter(Boolean).join(' · '),
      e.conversation ? [conv, e.number != null ? `#${e.number}` : null].filter(Boolean).join(' · ') : 'not in a conversation',
      modes ? [...modes.lines, enf && !enf.enforced ? (enf.by ? 'consent not enforced by the runtime' : 'how consent is enforced is not reported') : null].filter(Boolean).join(' · ') : null,
    ]}
    title={[started ? `Started ${at(started)}` : null, enf?.words ?? null].filter(Boolean).join('\n') || undefined}
    goWords="Go to the post this work is on"
    onOpen={e.conversation ? () => go(e.conversation!, e.post ?? undefined, e.number ?? undefined) : undefined}
    onBeside={e.conversation && beside ? () => beside(e.conversation!, e.post ?? undefined) : undefined} />
}

function WorkingBody({ go, beside }: { go: OpenConversation; beside: OpenBeside }) {
  const all = useActivity()
  const entries = workEntries(all)
  const now = entries.filter((e) => e.live)
  const held = entries.filter((e) => !e.live)
  return (
    <ul className="q2-gdock-list">
      {all === null && <Note>Reading who is working…</Note>}
      {all !== null && !now.length && <Note>Nobody is working right now.</Note>}
      {now.length > 0 && held.length > 0 && <Group>Working now · {now.length}</Group>}
      {now.map((e) => <WorkRow key={e.key} e={e} go={go} beside={beside} />)}
      {held.length > 0 && <Group>Open by the record, held by no process here · {held.length}</Group>}
      {held.map((e) => <WorkRow key={e.key} e={e} go={go} beside={beside} />)}
    </ul>
  )
}

/* RECENT: Home's Activity (`home/activity`): the runs the record says ended
   most recently, newest end first, each with the request it answered (that
   post's own first line) and how it ended in the server's words. Runs still
   open are Working's. The page is the server's: its latest ended runs. */
function RecentRow({ run, go, beside }: { run: Run; go: OpenConversation; beside: OpenBeside }) {
  const post = usePost(run.post)
  const conv = useConvName(run.conversation, post?.home_name)
  const who = (run.participant_name || run.participant).replace(/^@/, '')
  const line = firstLine(post)
  const end = run.ended_at ?? run.started_at
  /* how it ended, where that says more than that it returned (`ended`; an
     older server's `completed`). A run ending is not its work completing:
     whether the work is done is said on the post. */
  const how = PLAIN_END.has(run.state) ? null : stateWords(run.words)
  const word = runStateWord(run.state)
  return <Row kicker={word} state={word} name={line ?? `${who}'s run`}
    lead={<span className="q2-gdock-avatar"><Avatar id={run.participant} name={who} size={20} runtime={run.runtime ?? undefined} /></span>}
    meta={[
      [who, runtimeModel(run.runtime, run.model), `${run.ended_at ? 'ended' : 'started'} ${ago(end)}`].filter(Boolean).join(' · '),
      [conv, post?.number != null ? `#${post.number}` : null].filter(Boolean).join(' · '),
      how,
    ]}
    title={[run.words ? repairText(run.words) : null, `Started ${at(run.started_at)}`, run.ended_at ? `Ended ${at(run.ended_at)}` : null].filter(Boolean).join('\n')}
    goWords="Go to the request this run answered (its result is a reply there; whether the work is done is said on the post)"
    onOpen={run.conversation ? () => go(run.conversation, run.post || undefined, post?.number ?? undefined) : undefined}
    onBeside={run.conversation && beside ? () => beside(run.conversation, run.post || undefined) : undefined} />
}

function RecentBody({ go, beside }: { go: OpenConversation; beside: OpenBeside }) {
  const sub = useCallback((fn: () => void) => store.subscribe('coll:home:activity', fn), [])
  const data = useSyncExternalStore(sub, () => store.homeActivity)
  const [error, setError] = useState<string | null>(null)
  useEffect(() => {
    store.loadHomeActivity().then(() => setError(null), (e: unknown) => setError(String(e instanceof Error ? e.message : e)))
  }, [])
  const ids = data?.items ?? []
  const idsKey = ids.join(',')
  /* each run's own key: a run that ends moves here as its record says */
  const runsSub = useCallback((fn: () => void) => {
    const offs = idsKey ? idsKey.split(',').map((id) => store.subscribe('run:' + id, fn)) : []
    return () => offs.forEach((off) => off())
  }, [idsKey])
  useSyncExternalStore(runsSub, () => ids.map((id) => { const r = store.runs.get(id); return r ? `${r.state}:${r.ended_at ?? ''}` : '' }).join('|'))
  const runs = ids.map((id) => store.runs.get(id) as Run | undefined)
  const ended = runs.filter((r): r is Run => !!r && !r.error && isEnded(r))
    .sort((a, b) => (b.ended_at ?? b.started_at) - (a.ended_at ?? a.started_at))
  const open = runs.filter((r) => r && !r.error && !isEnded(r)).length
  const unreadable = runs.filter((r) => r?.error).length
  const reading = data && runs.some((r) => !r)
  return (
    <ul className="q2-gdock-list">
      {ended.map((r) => <RecentRow key={r.id} run={r} go={go} beside={beside} />)}
      {reading && <Note>Reading runs…</Note>}
      {data && !reading && !ended.length && <Note>No agent run has ended recently.</Note>}
      {open > 0 && <Note>{open === 1 ? '1 run is' : `${open} runs are`} still open: see Working.</Note>}
      {unreadable > 0 && <Note>{unreadable === 1 ? 'A run' : `${unreadable} runs`} could not be read.</Note>}
      {!data && !error && <Note>Reading recent runs…</Note>}
      {error && <Note alert>Could not read recent runs: {error}</Note>}
    </ul>
  )
}

/* CAPACITY: what each runtime reported it has left (`/api/capacity`), as
   the composer's picker reads it. Reading it RECORDS a reading, so it is
   asked only on request, and never on a read-only page. Nothing is
   estimated: a window that reported no figure says so (not zero), a window
   whose reset has passed since it was read has no current figure, and every
   reading says how old it is. */
const READ_ONLY_CAPACITY = 'Capacity is not read in the read-only view: reading it records a capacity reading in the Brain.'

const pct = (x: number) => `${Math.round(x * 100)}%`
const clock = (t: number | null | undefined) => (t ? new Date(t * 1000).toLocaleString([], { weekday: 'short', hour: '2-digit', minute: '2-digit' }) : null)

function CapacityRuntime({ name, c, rt }: { name: string; c: RuntimeCapacity | undefined; rt?: RuntimeChoice }) {
  const meters = capacityMeters(c)
  const silent = c?.established ? c.windows.filter((w) => w.used_fraction === null) : []
  const read = !c ? null : c.observed_at ? readAgo(c.observed_at) ?? 'read just now' : 'when it was read was not reported'
  const resetAt = new Map((c?.windows ?? []).map((w) => [w.label + ':' + (w.group ?? ''), w]))
  /* which models draw on which group, where the runtime has groups */
  const byGroup = new Map<string, string[]>()
  for (const [model, g] of Object.entries(c?.model_groups ?? {})) if (g) byGroup.set(g, [...(byGroup.get(g) ?? []), model])
  const avail = availabilityLines(rt)
  return (
    <li className="q2-gdock-cap" data-established={c?.established ?? false} data-unavailable={avail.unavailable || undefined}>
      <div className="q2-gdock-cap-head">
        <span className="q2-gdock-name">{name}</span>
        <span className="q2-gdock-meta" title={c?.observed_at ? `Read ${at(c.observed_at)}` : undefined}>{[c?.plan, read].filter(Boolean).join(' · ')}</span>
      </div>
      {avail.lines.map((l, i) => <p key={'a' + i} className="q2-gdock-meta q2-gdock-avail">{l}</p>)}
      {!c && <p className="q2-gdock-meta">Capacity: not reported for this runtime. Nothing was reported: not zero.</p>}
      {c && !c.established && <p className="q2-gdock-meta">Not established{c.why_not ? `: ${c.why_not}` : ''}. Nothing was reported: not zero.</p>}
      {c?.established && c.why_not && <p className="q2-gdock-meta">{c.why_not}</p>}
      {c?.established && !meters.length && !silent.length && <p className="q2-gdock-meta">{c.local ? 'A local runtime: no quota.' : 'It reported no usage windows.'}</p>}
      {meters.map((m) => {
        const w = resetAt.get(m.label + ':' + (m.group ?? ''))
        return (
          <div key={`${m.group ?? ''}:${m.label}`} className="q2-gdock-meter" data-level={m.stale ? 'stale' : m.level ?? 'unknown'}
            title={w && w.used_fraction != null ? `${pct(w.used_fraction)} used, as reported${w.resets_at ? `; resets ${at(w.resets_at)}` : ''}` : undefined}>
            <span className="q2-gdock-meter-name">{m.group ? `${m.group} ${m.name}` : m.name}</span>
            <span className="q2-gdock-meter-bar" aria-hidden="true"><b style={{ width: m.left === null ? 0 : pct(m.left) }} /></span>
            <span className="q2-gdock-meter-said">{m.stale
              ? 'reset since read: no current figure'
              : `${pct(m.left ?? 0)} left${m.resets ? ` · resets in ${m.resets} (${clock(w?.resets_at)})` : ''}`}</span>
          </div>
        )
      })}
      {silent.map((w) => (
        <div key={`silent:${w.group ?? ''}:${w.label}`} className="q2-gdock-meter" data-level="unreported">
          <span className="q2-gdock-meter-name">{w.group ? `${w.group} ${windowName(w.label)}` : windowName(w.label)}</span>
          <span className="q2-gdock-meter-bar" aria-hidden="true"><b style={{ width: 0 }} /></span>
          <span className="q2-gdock-meter-said">not reported</span>
        </div>
      ))}
      {[...byGroup].map(([g, models]) => <p key={g} className="q2-gdock-meta">{g}: {models.join(', ')}</p>)}
      {c?.local?.servers.map((s) => <p key={s.name} className="q2-gdock-meta">{localServerSays(s)}</p>)}
    </li>
  )
}

/** `capacity` false: availability only (`/api/execution` records nothing;
 *  `/api/capacity` records a reading, so a read-only page never asks it). */
function CapacityReader({ capacity = true }: { capacity?: boolean }) {
  const { data, error, loading, reload } = useCapacity(capacity)
  const ex = useExecution(true)
  const caps = data?.capacity ?? {}
  const kinds = new Map((ex.data?.runtimes ?? []).map((r) => [r.kind, r]))
  /* every runtime either read names, capacity's order first */
  const names = [...new Set([...Object.keys(caps), ...kinds.keys()])]
  const reading = (capacity && !data && !error) || (!ex.data && !ex.error)
  return (
    <ul className="q2-gdock-list" aria-busy={loading || ex.loading || undefined}>
      {names.map((name) => <CapacityRuntime key={name} name={name} c={caps[name]} rt={kinds.get(name)} />)}
      {capacity && data && !Object.keys(caps).length && <Note>No runtime reported its capacity: none is present to ask, or none answered.</Note>}
      {reading && <Note>{capacity ? 'Asking each runtime what it has left, and whether it can run… (this takes a few seconds)' : 'Asking each runtime whether it can run… (this takes a few seconds)'}</Note>}
      {error && <Note alert>Could not read capacity: {error}</Note>}
      {ex.error && <Note alert>Could not read which runtimes can run: {ex.error}</Note>}
      {capacity && (data || error) && (
        <li><button type="button" className="q2-gdock-more" onClick={reload} disabled={loading}
          title="Asks each runtime again; the Brain records the reading">
          {loading ? 'Reading…' : 'Read capacity again'}</button></li>
      )}
    </ul>
  )
}

/* The read-only check is made before the reader exists, so a read-only page
   never mounts `useCapacity` with a path and never asks it; it may ask only
   which runtimes can run (`/api/execution`, which records nothing). */
function CapacityBody() {
  const [asked, setAsked] = useState(false)
  if (READ_ONLY) return asked ? <><ul className="q2-gdock-list"><Note>{READ_ONLY_CAPACITY}</Note></ul><CapacityReader capacity={false} /></> : (
    <ul className="q2-gdock-list">
      <Note>{READ_ONLY_CAPACITY}</Note>
      <li><button type="button" className="q2-gdock-more" onClick={() => setAsked(true)}>Read which runtimes can run</button></li>
    </ul>
  )
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
        {tab === 'working' && <WorkingBody go={go} beside={beside} />}
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

/* SAVED PASSAGES: what was saved for later from a selection, newest first.
   Opening one goes to its conversation and post, and the exact passage is
   brought into view and marked (from its saved range, under its anchor). The
   list is this browser's: Mentis keeps no per-reader saved list. */
function SavedBody({ go }: { go: OpenConversation }) {
  const sub = useCallback((fn: () => void) => onSaved(fn), [])
  const raw = useSyncExternalStore(sub, () => JSON.stringify(savedPassages()))
  const list = JSON.parse(raw) as SavedPassage[]
  const open = (s: SavedPassage) => { go(s.conversation, s.post, s.number); window.setTimeout(() => revealPassage(s), 300) }
  return (
    <ul className="q2-gdock-list">
      {list.map((s) => (
        <li key={s.anchor} className="q2-gdock-item">
          <button type="button" className="q2-gdock-row" onClick={() => open(s)} title="Go to the passage">
            <span className="q2-gdock-row-text">
              <span className="q2-gdock-name">“{repairText(s.excerpt)}”</span>
              <span className="q2-gdock-meta">{[convName(s.conversation), s.number != null ? `#${s.number}` : null, ago(s.at / 1000)].filter(Boolean).join(' · ')}</span>
            </span>
          </button>
          <button type="button" className="q2-gdock-row-beside" onClick={() => forgetPassage(s.anchor)} title="Remove from saved passages" aria-label={`Remove “${s.excerpt.slice(0, 40)}” from saved passages`}>×</button>
        </li>
      ))}
      {!list.length && <Note>Nothing saved yet. Select words in a post, then Capture › Save for later.</Note>}
      {list.length > 0 && <Note>Kept in this browser: Mentis has no saved list of its own yet. Each passage stays anchored in the Brain.</Note>}
    </ul>
  )
}

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
      {panel === 'saved' && <SavedBody go={onOpenConversation} />}
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
          {btn('saved', 'Saved passages')}
          {btn('settings', 'Settings')}
        </>}
        <button type="button" ref={launcher} className={'q2-gdock-btn q2-gdock-launch' + (expanded ? ' on' : '')}
          aria-expanded={expanded} aria-label={expanded ? 'Fewer controls' : 'More: Search, Saved passages, Settings'}
          title={expanded ? 'Fewer controls' : 'More: Search, Saved passages, Settings'}
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
