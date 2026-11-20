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
import { lazy, Suspense, useCallback, useEffect, useId, useMemo, useRef, useState, useSyncExternalStore } from 'react'
import { ago } from '../api'
import { RELOAD_WORDS } from '../brainBinding'
import { checkLegacy, forgetLegacy, useLegacySent } from '../experimental/decisions'
import { capacityMeters, localServerSays, readAgo, useCapacity, useExecution, windowName, type RuntimeCapacity, type RuntimeChoice } from '../composer/execution'
import { Avatar } from '../fluid/identity/Who'
import { useActivity, type Activity, type ActivityRun } from '../fluid/identity/activity'
import { store, type Id } from '../fluid/store'
import { itemLine, type NeedsItem, type NeedsItems } from '../needsItems'
import { isTurn, useSearch, type Hit } from '../search'
import { READ_ONLY } from './live'
import { useWorking, type Working } from './presence'
import { callState, launchOnly, orderWork, workerLine } from './activity/hierarchy'
import { repairText } from './text'
import RunControls from './activity/RunControls'
import { forgetPassage, onSaved, revealPassage, savedPassages, type SavedPassage } from './annotate/passage'
import { ACTIVE, availabilityLines, capacityDiagnostics, capacityReading, executionModeReadings, firstLine, isEnded, PLAIN_END, runStateWord, runtimeAvailability, runtimeModel, stateWords, useConvName, usePost, useRun, useRunModes, type Run } from './activity/records'
import { DraftKeepContext, dropNotAsked, typedAll, typedFor } from '../experimental/draftKeep'
import { RefWordsContext } from '../experimental/refWords'
import { askOf, clearLeave, leaveFor, leaveNow, useLeave, useNeedsBound, useUnfolded } from './needs/about'
import { landAtBlock } from './needs/land'
import { itemName, refName, type About, type Ref } from './needs/inspect'
import { NeedsAbout, refWordsFor, type CanOpen, type OpenRefFn } from './needs/NeedsAbout'
import type { HeldBytes } from '../quiet/media/view'
import './dock.css'

export type DockPanel = 'activity' | 'search' | 'saved'
type Open = DockPanel | 'settings'
export type ActivityTab = 'needs' | 'working' | 'recent' | 'capacity'

type OpenConversation = (conversation: string, post?: string, number?: number) => void
/** opens a source beside the conversation, in a free working column */
type OpenBeside = ((conversation: string, post?: string) => void) | null

/** A Brain record, read in the centre reading area (Quiet Chat's own record page). */
type OpenRecord = ((entry: string) => void) | undefined
/** A held file, in the page's own viewer. */
type OpenFile = ((entry: string, about: Omit<HeldBytes, 'ref' | 'url'>) => void) | undefined
/** The ways this page opens what a Needs You item names. */
interface Openers { record: OpenRecord; file: OpenFile }

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

function Row({ name, meta, onOpen, lead, onBeside, goWords = 'Go to post', kicker, state, after, title, depth, itemKey }: {
  /** a Needs you item's key, so the way back from a reference finds its row */
  itemKey?: string
  /** how many Mentis delegations deep this row sits under the run it came from */
  depth?: number
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
  return <li className="q2-gdock-item" data-state={state} data-depth={depth || undefined} data-needs-item={itemKey}>{onOpen
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

function AnswerHere({ it, name, about, open: openRef, can }: { it: NeedsItem; name: string; about: About | null; open: OpenRefFn; can: CanOpen }) {
  /* unfolded for the life of the tab, so coming back from a reference finds
     the form as it was left; what is chosen and typed is the form's own draft */
  const [open, setOpen] = useUnfolded(it.key)
  const n = it.asks.length
  /* the form's own words, with what they name readable and openable */
  const words = useMemo(() => refWordsFor(about, it.conversation, openRef, can), [about, it.conversation, openRef, can])
  return <>
    <button type="button" className="q2-gdock-more" aria-expanded={open} onClick={() => setOpen(!open)}
      aria-label={`${open ? 'Hide the form for' : 'Answer here'}: ${name.slice(0, 80)}`}>
      {open ? 'Hide the form' : n > 1 ? `Answer here (${n} questions)` : 'Answer here'}
    </button>
    {/* the draft is the form's own, in memory for the page; this host asks that
        it be kept only for the question it was made against (experimental/draftKeep.ts) */}
    {open && it.post && (
      <div className="q2-gdock-answer">
        <Suspense fallback={<p className="q2-gdock-meta">Reading the decision form…</p>}>
          <DraftKeepContext.Provider value>
            <RefWordsContext.Provider value={words}>
              <DecisionsOn post={it.post} only={it.asks}
                onChanged={() => { void store.step().catch(() => {}).then(() => store.loadNeedsItems()).catch(() => {}) }} />
            </RefWordsContext.Provider>
          </DraftKeepContext.Provider>
        </Suspense>
      </div>
    )}
  </>
}

/* ONE ITEM: what is asked, by whom and where, in plain words; then WHAT IT
   IS ABOUT -- the thing to be decided, what supports it and what its words
   name, each opening the exact thing (needs/NeedsAbout.tsx) -- and only then
   the answer form. Opening anything from here remembers this item
   (needs/about.ts `leaveFor`), so one press comes back to it as it was. */
/* ANSWERS SENT BEFORE MENTIS NAMED THE BRAIN ON EACH ANSWER, never confirmed: which Brain they
   went to is not known, so they are never sent again or withdrawn from here
   (experimental/decisionOutbox.ts `isLegacy`). Shown, so none disappears without a word: Check
   asks this Brain (a read); Forget removes the note from this browser only. */
function LegacySent() {
  const kept = useLegacySent()
  const [said, setSaid] = useState<Record<string, string>>({})
  if (!kept.length) return null
  return (
    <li className="q2-ny-legacy" data-legacy-sent>
      <Note alert>
        <span>{kept.length === 1 ? 'An answer' : `${kept.length} answers`} sent before this update {kept.length === 1 ? 'was' : 'were'} never
        confirmed. Which Brain {kept.length === 1 ? 'it' : 'they'} went to is not known, so nothing is sent again from here.</span>
      </Note>
      {kept.map((k) => (
        <div key={k.ask} className="q2-ny-unsent" data-legacy-ask={k.ask}>
          <textarea readOnly rows={Math.min(6, [k.label, k.text].filter(Boolean).join('\n').split('\n').length + 1)}
            value={[k.label, k.text].filter(Boolean).join('\n')} aria-label="An answer sent before this update" />
          <span className="q2-ny-unsent-say">{said[k.ask] ?? ''}</span>
          <span>
            <button type="button" className="q2-link-quiet" onClick={() => void checkLegacy(k.ask).then((got) => setSaid((m) => ({ ...m,
              [k.ask]: got === 'recorded' ? 'This Brain holds it: it was recorded.' : got === 'voided' ? 'It was withdrawn and will not be recorded.'
                : got === 'absent' ? 'This Brain does not hold it. If it is still asked, answer again.' : 'The server could not be asked just now.' })))}>Check</button>
            {' · '}
            <button type="button" className="q2-link-quiet" onClick={() => forgetLegacy(k.ask)}>Forget it in this browser</button>
          </span>
        </div>
      ))}
    </li>
  )
}

function NeedsItemRow({ it, about, aboutError, rereading, stale, go, beside, openers, remember }: {
  it: NeedsItem; about: About | null; aboutError: string | null
  /** a later read of what this is about is on its way */
  rereading: boolean
  /** the server now serves another Brain than this page was showing: no answering here */
  stale?: boolean
  go: OpenConversation; beside: OpenBeside; openers: Openers; remember: boolean
}) {
  const { kind, what } = itemLine(it)
  const name = repairText(itemName(about, what))
  const where = [convName(it.conversation, it.conversation_name), it.post_number != null ? `#${it.post_number}` : null].filter(Boolean).join(' · ')
  const asker = it.asked_by_name ? it.asked_by_name.replace(/^@?/, '@') : null
  /* the asking post's first line, where the name is the question */
  const on = it.question && it.lead ? `on “${repairText(it.lead)}”` : null
  const leaving = useCallback((ref: string, opened: string) => { if (remember) leaveFor({ item: it.key, ref, what: name, opened, decision: it.kind === 'decision' }) }, [remember, it.key, name, it.kind])
  const can: CanOpen = useCallback((r) => (r.opens === 'record' ? !!openers.record : r.opens === 'file' ? !!openers.file && !!r.file : !!r.conversation), [openers])
  const open: OpenRefFn = useCallback((r: Ref) => {
    if (!r.available || !r.opens || !can(r)) return false
    leaving(r.id, refName(r, 60))
    if (r.opens === 'record') openers.record!(r.id)
    else if (r.opens === 'file') openers.file!(r.id, r.file!)
    else if (r.opens === 'conversation') go(r.conversation!)
    else {
      go(r.conversation!, r.post ?? undefined, r.number ?? undefined)
      /* a form: at the exact block its request names, not merely its post */
      if (r.type === 'form' && r.post && r.block) void landAtBlock(r.post, r.part ?? 0, r.block)
    }
    return true
  }, [can, go, leaving, openers])
  return <Row itemKey={it.key} kicker={kind} state={it.kind} name={name}
    meta={[[asker ? `asked by ${asker}` : null, it.at ? ago(it.at) : null].filter(Boolean).join(' · '), [where, on].filter(Boolean).join(' ')]}
    title={[it.because ? `Because: ${repairText(it.because)}` : null, at(it.at)].filter(Boolean).join('\n') || undefined}
    goWords="Go to the asking post"
    onOpen={it.conversation ? () => { leaving(it.post ?? it.key, 'the asking post'); go(it.conversation!, it.post ?? undefined, it.post_number ?? undefined) } : undefined}
    onBeside={it.conversation && beside ? () => beside(it.conversation!, it.post ?? undefined) : undefined}
    after={<>
      <NeedsAbout about={about} error={aboutError} rereading={rereading} here={it.conversation} open={open} can={can} />
      {!READ_ONLY && !stale && it.kind === 'decision' && it.post ? <AnswerHere it={it} name={name} about={about} open={open} can={can} /> : null}
      {/* NOT SENT, AND NOT LOST: the server now serves another Brain, so this answer cannot be
          sent from here; what was typed for it stays readable, to copy before reloading */}
      {stale && typedFor(askOf(it)).map((t, i) => (
        <div key={i} className="q2-ny-unsent" data-unsent>
          <span className="q2-ny-unsent-say">Not sent. What you typed, to copy before reloading:</span>
          <textarea readOnly rows={Math.min(6, t.split('\n').length + 1)} value={t} aria-label="What you typed, not sent" />
        </div>
      ))}
    </>} />
}

function NeedsBody({ go, beside, openers, remember }: { go: OpenConversation; beside: OpenBeside; openers: Openers; remember: boolean }) {
  const { got, error, reread } = useNeedsItems()
  useEffect(() => { reread() }, [reread])
  /* read again each time the list is opened: a name may have changed, a post been deleted */
  const [opened] = useState(() => Date.now())
  /* THE LIST AND ITS DETAILS, FROM ONE ANSWER OF ONE BRAIN (needs/about.ts), read on opening and
     again each time the plain list is fetched (record movement, every minute). Only that answer
     is drawn with details and with answering here; the plain list (`got`) is shown only where
     that answer could not be read, without details, exactly as before this work. */
  const about = useNeedsBound(opened, got)
  const shown = about.shown
  const items = shown ? shown.items : about.first ? [] : (got?.items ?? [])
  /* A DRAFT WHOSE QUESTION IS NO LONGER ASKED IS DROPPED: answered or withdrawn anywhere, it
     left this list, and its half-made answer goes with it. Only from an answer bound to this
     page's Brain: a list another Brain answered is never used to drop this page's drafts. */
  const asking = shown && !about.brainChanged ? shown.asks.join(',') : null
  useEffect(() => { if (asking !== null) dropNotAsked(asking ? asking.split(',') : []) }, [asking])
  /* COMING BACK from a reference: the item it was opened from is brought
     into view, and focus returns to that reference. Only for a leave made
     before this list was opened: one made from this very list is going away. */
  const list = useRef<HTMLUListElement>(null)
  const left = useLeave()
  const read = !!shown
  useEffect(() => {
    if (!left || !read || left.at > opened) return
    const row = [...(list.current?.querySelectorAll<HTMLElement>('[data-needs-item]') ?? [])].find((el) => el.dataset.needsItem === left.item)
    if (!row) { clearLeave(); return }
    row.scrollIntoView({ block: 'start' })
    row.setAttribute('data-returned', '')
    /* THE REFERENCE THAT WAS OPENED takes focus again. It may be inside the
       answer form, which is drawn a moment after the list, so it is looked
       for until it is there (or, after a second, the item's own row is). */
    const until = Date.now() + 3000
    let timer = 0
    const find = () => {
      const exact = [...row.querySelectorAll<HTMLElement>('[data-ref-id]')].find((el) => el.dataset.refId === left.ref && el.tagName === 'BUTTON')
      const to = exact ?? (Date.now() > until ? row.querySelector<HTMLElement>('button') : null)
      if (!to) { timer = window.setTimeout(find, 80); return }
      to.focus({ preventScroll: true })
      to.scrollIntoView({ block: 'nearest' })
      clearLeave()
    }
    timer = window.setTimeout(find, 0)
    return () => window.clearTimeout(timer)
  }, [left, read, opened])
  if (got?.unknown) return <ul className="q2-gdock-list"><Note>Could not tell what needs you: {got.why ?? 'the Brain did not say who the owner is'}.</Note></ul>
  return (
    <ul className="q2-gdock-list" ref={list}>
      {about.brainChanged && (
        <Note alert>
          <span data-brain-changed>The server now serves a different Brain than this page was showing. Reload the
          page before deciding anything here: what is listed may not be what you would be deciding.</span>{' '}
          <button type="button" className="q2-link-quiet" data-brain-reload onClick={() => location.reload()}>{RELOAD_WORDS}</button>
        </Note>
      )}
      {/* WHAT WAS TYPED FOR A QUESTION THE LIST NOW SHOWN DOES NOT HOLD (another Brain answered
          it): still readable, to copy before reloading. Those it holds are shown in their rows. */}
      {about.brainChanged && typedAll().filter((d) => !items.some((it) => askOf(it) === d.ask)).map((d) => (
        <li key={d.ask} className="q2-ny-unsent" data-unsent={d.ask}>
          <span className="q2-ny-unsent-say">Not sent. What you typed, to copy before reloading:</span>
          <textarea readOnly rows={Math.min(6, d.text.split('\n').length + 1)} value={d.text} aria-label="What you typed, not sent" />
        </li>
      ))}
      <LegacySent />
      {(shown ? shown.words : got?.words) && <li className="q2-gdock-sum">{shown ? shown.words : got?.words}</li>}
      {items.map((it) => <NeedsItemRow key={it.key} it={it} about={about.of(it)} aboutError={about.errorOf(it)}
        go={go} beside={beside} openers={openers} remember={remember} rereading={about.reading && !!shown} stale={about.brainChanged} />)}
      {!about.first && (shown || got) && !items.length && <Note>Nothing needs you.</Note>}
      {(about.first || !got) && !error && <Note>Reading what needs you…</Note>}
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

/** THE RUN'S NATIVE WORKERS, compactly, under its row: one line each, as the
 *  run's live feed holds them. They are inside this run -- its identity, its
 *  consent -- which the heading says; their tool calls are under Activity. */
function NativeWorkers({ workers }: { workers: NonNullable<ActivityRun['workers']> }) {
  if (!workers.length) return null
  /* a worker only known to have been launched is not counted as running */
  const running = workers.filter((w) => w.status !== 'completed' && w.status !== 'failed' && !launchOnly(w)).length
  return (
    <div className="q2-gdock-workers" role="group" aria-label="Native sub-agents inside this run">
      <span className="q2-gdock-workers-head" title="Workers the runtime started inside this run. They act under this run's identity and consent; they are not Mentis delegations.">
        {workers.length === 1 ? '1 native sub-agent' : `${workers.length} native sub-agents`} inside this run{running ? ` · ${running} running` : ''}
      </span>
      <ul>
        {workers.map((w) => {
          const state = callState(w.status, { ended: false, cancelled: false })
          return <li key={w.id} data-state={launchOnly(w) ? 'launched' : state}>
            {workerLine(w.title ? repairText(w.title) : null, w, state, w.calls_seen).replace(/^Native sub-agent · /, '')}
            {w.now ? <span className="q2-gdock-workers-now"> · now: {repairText(w.now).slice(0, 80)}</span> : null}
          </li>
        })}
      </ul>
    </div>
  )
}

function WorkRow({ e, go, beside, depth = 0 }: { e: WorkEntry; go: OpenConversation; beside: OpenBeside; depth?: number }) {
  const run = useRun(e.run?.run)
  const conv = useConvName(e.conversation)
  const r = e.run
  const who = e.alias.replace(/^@/, '')
  const waiting = !!(r?.permission || r?.permissions?.length)
  const active = e.live && (!r || ACTIVE.has(r.state))
  /* the state as the server words it; Fluid's own "waiting for you" and "Stopping…" beside it */
  /* A MENTIS DELEGATION says so, and whose: an independent execution with
     its own runtime and consent, linked to the work it came from. */
  const from = r?.delegated_from ?? null
  const kicker = [from ? 'Mentis delegation' : null, r ? r.state : 'live execution', waiting ? 'waiting for you' : null, r?.stopping ? 'Stopping…' : null, e.live ? null : 'not held here'].filter(Boolean).join(' · ')
  const started = run?.started_at ?? e.since
  /* its Permission and Execution, as the server says them; enforcement said
     only as the server says it, never as enforced unless it is */
  const modes = useRunModes(e.run?.run)
  const enf = modes?.enforcement
  const workers = r?.workers ?? []
  return <Row key={e.key} depth={depth} kicker={kicker} state={waiting ? 'waiting' : active ? 'running' : r?.state ?? 'running'}
    name={r?.activity && e.live ? `${who}: ${repairText(r.activity)}` : who}
    lead={<span className={(active ? 'q2-pulse ' : '') + 'q2-gdock-avatar'}><Avatar id={e.participant} name={e.alias} size={20} runtime={run?.runtime ?? e.runtime ?? undefined} /></span>}
    meta={[
      /* the server's words; the start it may end with is said on the next line */
      r?.words ? repairText(r.words).replace(/\s*·\s*started [\d-]+ [\d:]+$/, '') : e.run ? null : 'a live execution no dispatched run accounts for',
      from ? `Independent execution, delegated by ${from.by_name ? '@' + from.by_name : 'somebody'}${from.at ? ' ' + ago(from.at) : ''}${depth ? '' : from.run ? '' : ' · the run it came from is no longer open'}` : null,
      [runtimeModel(run?.runtime ?? r?.runtime ?? e.runtime, run?.model ?? r?.model_requested), started ? `started ${ago(started)}` : null].filter(Boolean).join(' · '),
      e.conversation ? [conv, e.number != null ? `#${e.number}` : null].filter(Boolean).join(' · ') : 'not in a conversation',
      modes ? [...modes.lines, enf && !enf.enforced ? (enf.by ? 'consent not enforced by the runtime' : 'how consent is enforced is not reported') : null].filter(Boolean).join(' · ') : null,
    ]}
    title={[started ? `Started ${at(started)}` : null, enf?.words ?? null].filter(Boolean).join('\n') || undefined}
    goWords="Go to the post this work is on"
    /* ITS OWN CONTROLS, bound to this run's id: live activity, Permission, Stop */
    after={e.live && r?.run ? <>
      <NativeWorkers workers={workers} />
      <RunControls run={r.run} who={who} ended={!active && !waiting} runtime={run?.runtime ?? r.runtime ?? e.runtime} />
    </> : undefined}
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
      {/* a Mentis delegation follows the open run it came from, one level in */}
      {orderWork(now).map(({ e, depth }) => <WorkRow key={e.key} e={e} go={go} beside={beside} depth={depth} />)}
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
    /* what it did can still be opened: its native workers, tool calls and usage */
    after={<RunControls run={run.id} who={who} ended runtime={run.runtime} />}
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
   reading says how old it is.

   THE OWNER'S ASK (round 1 of the Mark 2 redesign, approved): "I want to open
   it and know, in a couple of seconds, which runtime I can use and how much of
   it is left." So the closed list is availability, allowances, resets and
   freshness, and NO PROSE -- every sentence the old panel put under every
   runtime now lives in that runtime's own expansion, in ordinary language,
   with the technical strings behind one further disclosure inside it. Nothing
   extra is read for either: both are views over the same two reads.

   The row head is the whole disclosure (there is no separate "Details" line),
   and the one-word availability on it is `runtimeAvailability` -- a reading of
   what `/api/execution` already reported, stated as such in activity/records.ts. */
const READ_ONLY_CAPACITY = 'Capacity is not read in the read-only view: reading it records a capacity reading in the Brain.'

const pct = (x: number) => `${Math.round(x * 100)}%`

/** A row names its own reading's age only where that differs from the
 *  panel's: the header already says how fresh the reading is, so repeating
 *  it on every runtime would be noise, while codex's days-old session file
 *  beside a reading taken just now is exactly what needs saying. */
const OLDER_THAN_S = 60

/** ONE WINDOW'S NAME, SHORTENED WHERE IT MUST BE BUT NEVER WHERE IT IDENTIFIES.
 *
 *  A runtime with quota groups names a window by both (`Gemini Models weekly`,
 *  `Gemini Models 5h`), and in a 360px popup one ellipsised string made the
 *  two read identically -- "Gemini M…" twice, over different figures. The
 *  group gives way and the window's own length is kept whole, so the rows stay
 *  tellable apart; with no group the name is alone and may shorten itself. */
function WindowName({ group, name }: { group: string | null; name: string }) {
  const whole = group ? `${group} ${name}` : name
  return (
    <span className="q2-gdock-meter-name" title={whole}>
      {group && <span className="q2-gdock-meter-grp">{group}</span>}
      <span className="q2-gdock-meter-win">{name}</span>
    </span>
  )
}

function CapacityRuntime({ name, c, rt, freshest }: {
  name: string; c: RuntimeCapacity | undefined; rt?: RuntimeChoice; freshest: number | null
}) {
  const [open, setOpen] = useState(false)
  const [diag, setDiag] = useState(false)
  const meters = capacityMeters(c)
  const silent = c?.established ? c.windows.filter((w) => w.used_fraction === null) : []
  const readWords = c?.observed_at ? readAgo(c.observed_at) : null
  const resetAt = new Map((c?.windows ?? []).map((w) => [w.label + ':' + (w.group ?? ''), w]))
  /* which models draw on which group, where the runtime has groups */
  const byGroup = new Map<string, string[]>()
  for (const [model, g] of Object.entries(c?.model_groups ?? {})) if (g) byGroup.set(g, [...(byGroup.get(g) ?? []), model])
  const av = runtimeAvailability(rt)
  const modes = executionModeReadings(rt)
  const older = c?.observed_at && freshest && freshest - c.observed_at >= OLDER_THAN_S ? readWords : null
  /* the one short line the closed row may carry about its allowance: spent,
     or local (a resource reading, never a quota) -- nothing else is prose */
  const spent = meters.length > 0 && meters.every((m) => !m.stale && m.left === 0)
  const detail = `q2-cap-${name}`
  return (
    <li className="q2-gdock-cap" data-established={c?.established ?? false} data-unavailable={(av.state === 'paused' || av.state === 'off') || undefined}>
      <button type="button" className="q2-gdock-cap-head" aria-expanded={open} aria-controls={detail}
        onClick={() => setOpen(!open)} title={`${name}: ${av.word}${c?.observed_at ? ` · read ${at(c.observed_at)}` : ''}`}>
        <span className="q2-gdock-cap-name">{name}</span>
        {c?.plan && <span className="q2-gdock-plan">{c.plan}</span>}
        {older && <span className="q2-gdock-cap-age">{older}</span>}
        <span className="q2-gdock-cap-gap" />
        <span className="q2-gdock-avail" data-state={av.state}><i aria-hidden="true" />{av.word}</span>
        <span className="q2-gdock-cap-chev" aria-hidden="true">{open ? '⌄' : '›'}</span>
      </button>
      {meters.map((m) => {
        const w = resetAt.get(m.label + ':' + (m.group ?? ''))
        return (
          <div key={`${m.group ?? ''}:${m.label}`} className="q2-gdock-meter"
            data-level={m.stale ? 'stale' : m.left === 0 ? 'out' : m.level ?? 'unknown'}
            title={w && w.used_fraction != null ? `${pct(w.used_fraction)} used, as reported${w.resets_at ? `; resets ${at(w.resets_at)}` : ''}` : undefined}>
            <WindowName group={m.group} name={m.name} />
            <span className="q2-gdock-meter-bar" aria-hidden="true"><b style={{ width: m.left === null ? 0 : pct(m.left) }} /></span>
            {/* A WINDOW PAST ITS RESET CARRIES NO FIGURE, and says so: it has
                refilled by some amount nobody measured (execution.ts
                `capacityMeters`), so the compact row must not let a hatched
                empty bar be read as "none left". */}
            <span className="q2-gdock-meter-said">{m.stale
              ? 'reset since read · no figure'
              : <>{pct(m.left ?? 0)}{m.resets && <span className="q2-gdock-meter-reset"> · {m.resets}</span>}</>}</span>
          </div>
        )
      })}
      {silent.map((w) => (
        <div key={`silent:${w.group ?? ''}:${w.label}`} className="q2-gdock-meter" data-level="unreported">
          <WindowName group={w.group ?? null} name={windowName(w.label)} />
          <span className="q2-gdock-meter-bar" aria-hidden="true"><b style={{ width: 0 }} /></span>
          <span className="q2-gdock-meter-said">not reported</span>
        </div>
      ))}
      {/* THE ONLY PROSE A CLOSED ROW MAY CARRY, and each of these is a figure
          that would otherwise be read as "no limit" rather than "none left" or
          "not a quota". Everything else is in the expansion. */}
      {spent && <p className="q2-gdock-cap-line">No allowance left until it resets.</p>}
      {!c && <p className="q2-gdock-cap-line">Capacity: not reported.</p>}
      {/* A LOCAL RUNTIME HAS NO ALLOWANCE TO ESTABLISH, so "not established"
          is not the fact about it -- it reads as a failure where there is
          none. It says what it runs on instead, ONCE, with each of its model
          servers after it rather than the sentence repeated per server (both
          read wrong in the browser against the dev Brain: Ollama and LM Studio
          each carried their own copy). */}
      {c && !c.established && !c.local && <p className="q2-gdock-cap-line">Its allowance was not established.</p>}
      {c?.established && !meters.length && !silent.length && !c.local && <p className="q2-gdock-cap-line">It reported no usage windows.</p>}
      {c?.local && (
        <p className="q2-gdock-cap-line">Runs on this computer — no allowance.
          {c.local.servers.map((s) => <span key={s.name} className="q2-gdock-cap-srv">{localServerSays(s)}</span>)}</p>
      )}
      {open && (
        <div className="q2-gdock-cap-detail" id={detail}>
          <p className="q2-gdock-cap-dh">Where {name} can run</p>
          {modes.length > 0 ? <>
            {modes.map((m) => (
              <div key={m.mode} className="q2-gdock-cap-mode" data-state={m.state}>
                <i aria-hidden="true" />
                <span>
                  <b>{m.name}</b>{m.isDefault ? ' (its default)' : ''} — <span className="q2-gdock-cap-st">{m.word}</span>
                  <span className="q2-gdock-cap-why">{m.sentence}</span>
                </span>
              </div>
            ))}
          </> : (
            /* NO MODE CONTRACT TO EXPAND: not installed, or this server holds
               no MARS report of its modes. `availabilityLines` is the wording
               already settled for both, so it is said rather than reworded. */
            (availabilityLines(rt).lines.length ? availabilityLines(rt).lines
              : [av.why ?? 'Where this runtime can run was not reported.'])
              .map((l, i) => <p key={'av' + i} className="q2-gdock-cap-why">{l}</p>)
          )}
          <p className="q2-gdock-cap-dh">This reading</p>
          {capacityReading(c, readWords).map((l, i) => <p key={'r' + i} className="q2-gdock-cap-why">{l}</p>)}
          {[...byGroup].map(([g, models]) => <p key={g} className="q2-gdock-cap-why">{g} covers {models.join(', ')}.</p>)}
          {rt?.models_why_not && <p className="q2-gdock-cap-why">{rt.models_why_not}</p>}
          <div className="q2-gdock-cap-diag">
            <button type="button" aria-expanded={diag} onClick={() => setDiag(!diag)}>
              <span aria-hidden="true">{diag ? '⌄' : '›'}</span> Technical diagnostics
            </button>
            {diag && <pre>{capacityDiagnostics(name, c, rt)}</pre>}
          </div>
        </div>
      )}
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
  /* THE FRESHNESS OF THE READING, ONCE, over the panel: the newest
     observation any runtime reported. A row says its own age only where it is
     older than this (CapacityRuntime's `older`). */
  const freshest = Object.values(caps).reduce<number | null>((n, c) => (c.observed_at && (!n || c.observed_at > n) ? c.observed_at : n), null)
  const fresh = freshest ? readAgo(freshest) ?? 'checked just now' : null
  return <>
    {capacity && (data || error) && (
      <div className="q2-gdock-caphead">
        <span className="q2-gdock-caphead-ttl">Allowances left</span>
        {fresh && <span className="q2-gdock-caphead-age">{fresh.replace(/^read /, 'checked ')}</span>}
        <button type="button" className="q2-gdock-caphead-again" onClick={reload} disabled={loading}
          title="Asks each runtime again; the Brain records the reading">{loading ? 'Reading…' : 'Check again'}</button>
      </div>
    )}
    <ul className="q2-gdock-list" aria-busy={loading || ex.loading || undefined}>
      {names.map((name) => <CapacityRuntime key={name} name={name} c={caps[name]} rt={kinds.get(name)} freshest={freshest} />)}
      {capacity && data && !Object.keys(caps).length && <Note>No runtime reported its capacity: none is present to ask, or none answered.</Note>}
      {reading && <Note>{capacity ? 'Asking each runtime what it has left, and whether it can run… (this takes a few seconds)' : 'Asking each runtime whether it can run… (this takes a few seconds)'}</Note>}
      {error && <Note alert>Could not read capacity: {error}</Note>}
      {ex.error && <Note alert>Could not read which runtimes can run: {ex.error}</Note>}
    </ul>
  </>
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
function ActivityBody({ tab, setTab, go, beside, working, needCount, openers, remember }: {
  tab: ActivityTab; setTab: (t: ActivityTab) => void; go: OpenConversation; beside: OpenBeside; working: Working[]; needCount: number | null
  openers: Openers
  /** whether opening something from Needs you leaves this list (the dock's panel closes; a column stays) */
  remember: boolean
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
        {tab === 'needs' && <NeedsBody go={go} beside={beside} openers={openers} remember={remember} />}
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
export function DockPanelBody({ panel, onOpenConversation, onOpenBeside = null, inSurface, onOpenRecord, onOpenFile }: {
  panel: DockPanel
  onOpenConversation: OpenConversation
  onOpenBeside?: OpenBeside
  inSurface?: boolean
  onOpenRecord?: OpenRecord
  onOpenFile?: OpenFile
}) {
  const outward = useRef({ onOpenRecord, onOpenFile })
  outward.current = { onOpenRecord, onOpenFile }
  const hasRecord = !!onOpenRecord, hasFile = !!onOpenFile
  const openers = useMemo<Openers>(() => ({
    record: hasRecord ? (entry) => outward.current.onOpenRecord?.(entry) : undefined,
    file: hasFile ? (entry, about) => outward.current.onOpenFile?.(entry, about) : undefined,
  }), [hasRecord, hasFile])
  const working = useWorking(false)
  const needs = useNeedsItems().got
  const needCount = needs?.counts?.total ?? needs?.items.length ?? null
  /* a column opens on the tab the dock was showing */
  const [tab, setTab] = useState<ActivityTab>(() => lastTab)
  return (
    <div className={'q2-gdock-body' + (inSurface ? ' q2-gdock-in-surface' : '')} data-panel={panel}>
      {panel === 'activity' && <ActivityBody tab={tab} setTab={showTab(setTab)} go={onOpenConversation} beside={onOpenBeside} working={working} needCount={needCount}
        openers={openers} remember={!inSurface} />}
      {panel === 'search' && <SearchBody go={onOpenConversation} autoFocus={!inSurface} />}
      {panel === 'saved' && <SavedBody go={onOpenConversation} />}
    </div>
  )
}

/* -- the dock --------------------------------------------------------------- */

export default function GlobalDock({ settings, onOpenInSurface, onOpenConversation, onOpenBeside, onOpenRecord, onOpenFile }: {
  settings: React.ReactNode
  onOpenInSurface: ((panel: DockPanel) => void) | null
  onOpenConversation: (conversation: string, post?: string, number?: number) => void
  /** a source opened beside the conversation; null where there is no working column */
  onOpenBeside: OpenBeside
  /** a Brain record a Needs you item names, read on its own page */
  onOpenRecord?: OpenRecord
  /** a held file a Needs you item names, in the page's viewer */
  onOpenFile?: OpenFile
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
  /* kept the same between renders, so an item's row is not drawn again for nothing */
  const outward = useRef({ onOpenConversation, onOpenBeside, onOpenRecord, onOpenFile })
  outward.current = { onOpenConversation, onOpenBeside, onOpenRecord, onOpenFile }
  const go: OpenConversation = useCallback((c, post, number) => { close(false); outward.current.onOpenConversation(c, post, number) }, [close])
  const hasBeside = !!onOpenBeside
  const beside: OpenBeside = useMemo(() => (hasBeside ? (c: string, post?: string) => { close(false); outward.current.onOpenBeside?.(c, post) } : null), [hasBeside, close])
  const hasRecord = !!onOpenRecord, hasFile = !!onOpenFile
  const openers = useMemo<Openers>(() => ({
    record: hasRecord ? (entry) => { close(false); outward.current.onOpenRecord?.(entry) } : undefined,
    file: hasFile ? (entry, about) => { close(false); outward.current.onOpenFile?.(entry, about) } : undefined,
  }), [hasRecord, hasFile, close])

  /* THE WAY BACK TO A DECISION. Something a Needs you item names was opened,
     so the panel closed; one control, named for the decision, brings the
     panel back on that item with its form as it was left (needs/about.ts).
     It stays until the reader returns, answers or dismisses it. THE BROWSER'S
     OWN BACK IS NOT LISTENED TO: it does what the page's history does and
     nothing more (a listener of this dock's would answer every history move
     of the page, and reopen Needs you on one that had nothing to do with it).
     Focus goes to the control when the panel closes under it, so Enter, Space
     or Escape there return at once. */
  const left = useLeave()
  const backBtn = useRef<HTMLButtonElement>(null)
  const comeBack = useCallback(() => {
    if (!leaveNow()) return
    opener.current = null
    showTab(setTab)('needs')
    setOpen('activity')
  }, [])
  const leftAt = left?.at
  useEffect(() => {
    if (!leftAt || open) return
    const t = window.setTimeout(() => { if (leaveNow() && (!document.activeElement || document.activeElement === document.body)) backBtn.current?.focus() }, 60)
    return () => window.clearTimeout(t)
  }, [leftAt, open])
  /* the item it came from is no longer asked: there is nothing to go back to */
  useEffect(() => { if (left && needs && !needs.items.some((it) => it.key === left.item)) clearLeave() }, [left, needs])

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
            ? <div className="q2-gdock-body" data-panel="activity"><ActivityBody tab={tab} setTab={showTab(setTab)} go={go} beside={beside} working={working} needCount={needCount} openers={openers} remember /></div>
            : <DockPanelBody panel={open} onOpenConversation={go} onOpenBeside={beside} />}
        </div>
      )}
      {left && open !== 'activity' && (
        <div className="q2-gdock-return" role="group" aria-label={left.decision ? 'A decision you were making' : 'Something that needs you'}>
          <button type="button" ref={backBtn} className="q2-gdock-return-go" data-return-to={left.item}
            title={`Back to: ${left.what}\nYou opened ${left.opened}. What you chose and typed is still there.`}
            aria-label={`${left.decision ? 'Back to your decision' : 'Back to what needs you'}: ${left.what.slice(0, 120)}. You opened ${left.opened}; what you chose and typed is still there.`}
            onClick={comeBack}
            onKeyDown={(e) => { if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); comeBack() } }}>
            <span aria-hidden="true">←</span> {left.decision ? 'Back to your decision' : 'Back to what needs you'}
          </button>
          <button type="button" className="q2-gdock-return-x" aria-label="Dismiss: stay here" title="Dismiss. It stays in Needs you, as you left it." onClick={() => clearLeave()}>×</button>
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
