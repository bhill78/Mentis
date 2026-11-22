/* QUIET CHAT MARK 2 — DESIGN ROUND 1: the editorial conversation.
 *
 * Served at /quiet2 beside Mark 1 (docs/quiet-chat/MARK-2.md). The
 * conversation is the page: one centred reading column, quiet chrome, and
 * margins that stay empty until something in them is asked for. Navigation
 * is stepped markers at the edges: conversations on the left rail, topics on
 * the right. The logo is the Brain's menu (Fluid's BrandMenu), not another
 * conversation list.
 *
 * LAYOUT lives in one place, the Settings toolbar's Layout section: one, two
 * or three columns, the conversation's side, receding and restoring it. Panes
 * are resized by dragging the dividers between them. A receded conversation
 * gives up its whole column (the surfaces take it) and waits as a tab at the
 * outer edge; restoring it brings back the arrangement and sizes it left.
 *
 * Content is the round-1 sample (sample.ts) or, for judging the reading
 * measure, a real conversation's latest posts from the Brain serving this
 * page (real.ts). The composer is Fluid's own, live. Working surfaces are
 * placeholders. */
import '../fluid/fluid.css'
import '../fluid/frame/frame.css'
import '../fluid/frame/bar.css'
import '../fluid/conversation/conversation.css'
import './quiet2.css'
import { Suspense, lazy, useEffect, useLayoutEffect, useRef, useState, type ReactNode } from 'react'
import InstructionsPanel from './brain/author/InstructionsPanel'
import AuthorModal, { type AuthorRequest } from './brain/author/AuthorModal'
import { Layer } from '../fluid/frame/layer'
import { Avatar } from '../fluid/identity/Who'
import { brainIdentity, newOp, store, type Conversation } from '../fluid/store'
import BrandMenu from '../surfaces/BrandMenu'
import { BrainGlyph, SourcesGlyph, SpaceGlyph } from '../surfaces/PlaceIcons'
import Dock from './Dock'
import Viewer, { type ViewerActions } from './viewer/Viewer'
import { closeViewer, inColumn, maximised, moveViewer, openViewer, parkViewer, returnViewer, settleColumns, spaceViewer, useViewerLayout, type OpenViewer } from './viewer/viewers'
import MagnetHost, { findMagnet, focusMagnetManagement } from './magnets/Host'
import { magnetIntent, resumeMagnet, type MagnetIntent, type MagnetOrigin, type QuietMagnetResource } from './magnets/navigation'
import type { RouteResult } from '../fluid/surface/magnet/route'
import { discardMiniDraft, hasMiniDraft } from './magnets/conversation'
import { returnedItemOf } from '../quiet/media/view'
import { magnetAffectedPlaces } from './space/placement'
import { releaseResource } from './space/registry'
import './magnets/host.css'
import { postSource, type SpaceState, type Viewable, type ViewerSource } from './viewer/types'
/* -- THE 3D BRAIN IN QUIET CHAT (quiet2/space/, addendum adm-9f12e8153ca3) -- */
import SpaceReaders from './space/SpaceReaders'
import SpaceStage from './space/SpaceStage'
import { SpaceHostContext, type SpaceHostApi } from './space/host'
import type { SpaceBrainKey, SpaceNode } from './space/contract'
import { CLOSED_NOTICE, graphIntent, inspectIntent, inspectPath, resumeSpace, type SpaceDestination, type SpaceIntent } from './space/history'
import { affectedPlaces, presentationOf, restoresReceded, spacePlace, type ColumnRoom, type RecededOverride } from './space/placement'
import { invalidateOtherBrains, openSession, releaseAllSessions, releaseSession, sessionById, sessionOfBrain, spaceBrainKey } from './space/registry'
import { routeNode, type NodeFacts } from './space/routing'
import { answers, knownOf, resolveEntryFacts } from './space/resolve'
import { provideSpaceSessions } from './space/provider'
import { createSpaceSession } from '../surfaces/space/session'
import SpaceSessionReader from '../surfaces/space/SpaceSessionReader'
import { dragPayload } from '../fluid/brain/address'
import { BACK_TO_SPACE, heldItem } from './brain/logic'
import { LookGallery, LookMaker, Toasts, useSurfaceVars, useTopBar } from './Look'
import { useLook } from '../fluid/frame/look'
import ConversationList from './conversations/ConversationList'
import DangerZone from './conversations/DangerZone'
import ConversationState, { DeletedComposer, TrashedComposer, useConversationRow } from './conversations/ConversationState'
import { TombstoneView } from './conversations/Tombstone'
import { cleanupOf, deletedWords } from './conversations/manage'
import GlobalDock, { DockPanelBody, type DockPanel, type DockResultOpener } from './GlobalDock'
/* the asking block's own fresh read, which is Needs you's (F2) */
import { readFormNow } from './needs/about'
import SelectionToolbar from './annotate/Selection'
import Markers from './Markers'
import BrainBrowser from './brain/BrainBrowser'
import { read as readJson, useApi } from '../api'
import SourcesBrowser from './sources/SourcesBrowser'
import type { How } from './centreHistory'
import { usePlaces } from './places'
import { NO_SPACE, NO_SUCH_RECORD, NO_SUCH_SOURCE, addressOf, centreFor, readAddress, type CentreAt } from './address'
import { CENTRE, guardPlaces, leaving, unfinished, type Ask, type Place } from './leaving'
import SourceMain, { type SourceMainState, type SourceMainView } from './sources/SourceMain'
import { chipAsk, keepsSetup } from './sources/moving'
import { SOURCES_EVENT, type SourcesAnswer, type SourcesRoute } from '../surfaces/sources/route'
import BrainMain from './brain/BrainPages'
import type { BrainMainState, BrainMainView, BrainOrigin } from './brain/logic'
import { fetchBrainRecord, type BrainFilter, type BrainRecordSummary } from './brain/data'
import { BrainNavContext, type BrainNav } from './brain/nav'
import ReceivePreview from './brain/ReceivePreview'
import Post, { PageContext, picturesOf, type PostPage, type SurfaceView } from './Post'
/* RESULT-FIRST NAVIGATION, MOUNTED (HOST-INTEGRATION.md §1). The decisions are
   all in `results/`; what this file supplies is the one thing only a page has
   -- its React state -- handed over once as `ResultPage`. */
import { EXTERNAL_LINK, destinationOfRef } from './results/targets'
import { BRAIN_UNCONFIRMED, beginOpening, holdLaunch, type DecisionLaunch, type LaunchContext, type LaunchFocus } from './results/launch'
import { centreGeneration, mountResults, type BeginMove, type ColumnChoice, type MountedResults, type ResultPage as ResultHostPage } from './results/mount'
import { servingBrainKey } from './results/serving'
import type { MayMove, Navigation } from './results/opener'
import { destinationOfResult, destinationOfTarget, lookupOf } from './results/fromWork'
import type { ResultChoice, ResultsHost, SourceChoice } from './results/host'
import { useWorkOverview, workDetailPath } from '../work/api'
import type { ResultPage as WorkResultPage } from '../work/contract'
import { LONG_REEL, heldIn, postOf, readThread, threadRootOf, usePosts, useRealFlow } from './real'
import { activityOf, newestOf, readNewest, type Activity } from './latest'
import JumpToLatest from './JumpToLatest'
import { CONVERSATION, CONVERSATIONS, PEOPLE, POSTS, TOPICS, type Id, type MarkerItem, type Person, type Post as PostT } from './sample'
import { repairText } from './text'
import { BRAIN, BRAIN_ERROR, READ_ONLY, brainNow, loadBrain, switchBrain } from './live'
import { MOVED_WORDS, RELOAD_WORDS, useBrainMoved } from '../brainBinding'
import { guardReload } from './reloadGuard'
import { useWorking, workingIn } from './presence'
import { SurfacePane } from './Surface'
import { FoldedWork, ReplyFold, ThreadView } from './Thread'
import { readPrefs, readWorkspace, savePrefs, saveWorkspace, type Arrangement, type Measure, type Side } from './prefs'

/* WHERE THE GRAPH COMES FROM, said once for this page (space/provider.ts).
 * Quiet Chat holds no session and reads no graph of its own: the factory and
 * the one reader are Part A's, and this is the single call that gives them to
 * the registry and to SpaceReaders. It is made here rather than inside
 * provider.ts so that the pure decision modules which import the provider --
 * the registry, placement, routing and their checks -- keep no runtime
 * dependency on the renderer. Both are cheap and draw nothing; the canvas
 * itself stays in SpaceHost's own lazily loaded chunk. */
provideSpaceSessions({ createSpaceSession, SpaceSessionReader })

type Pane = 'conv' | 's1' | 's2'
type Content = 'sample' | 'real' | 'long'

/** The two reading measures compared this round. Neither is settled. */
const MEASURES: Record<Measure, { px: number; label: string }> = {
  current: { px: 680, label: 'Current · 680px' },
  wide: { px: 880, label: 'Wider · 880px' },
}

/** The least a pane can be dragged to. */
const MIN: Record<Pane, number> = { conv: 360, s1: 220, s2: 220 }


const params = new URLSearchParams(location.search)
/** what the address this page was opened with asks for (address.ts) */
const opened = readAddress(location.search)
/** how long a 3D Brain asked for by address waits for the Brain to be known */
const SPACE_WAIT_MS = 15000

/** The global dock's panels, by name, for a column's header and the chooser. */
const DOCK_NAMES: Record<DockPanel, string> = { activity: 'Activity', search: 'Search', saved: 'Saved passages' }
const pick = <const T extends string>(k: string, ok: readonly T[], d: NoInfer<T>): T => (ok as readonly string[]).includes(params.get(k) ?? '') ? params.get(k) as T : d

function panesOf(arr: Arrangement, side: Side, receded: boolean): Pane[] {
  const surfaces: Pane[] = arr === 'one' ? [] : arr === 'two' ? ['s1'] : ['s1', 's2']
  if (receded) return surfaces.length ? surfaces : ['s1']
  return side === 'left' ? ['conv', ...surfaces] : [...surfaces, 'conv']
}

const defaultSizes = (panes: Pane[]) => {
  if (panes.length === 1) return [1]
  const conv = panes.length === 2 ? 0.44 : 0.36
  return panes.map((p) => p === 'conv' ? conv : (1 - (panes.includes('conv') ? conv : 0)) / panes.filter((x) => x !== 'conv').length)
}

/** The Brain's name, for the logo's menu -- and its identity, which is what a
 *  graph session is scoped to (space/registry.ts). An identity not yet read is
 *  not a key: nothing is opened against a guessed Brain. */
function useBrain() {
  const [b, setB] = useState<{ name: string | null; whyNot?: string | null; path?: string | null; key?: SpaceBrainKey | null; unread?: boolean }>({ name: null })
  useEffect(() => {
    void brainIdentity().then((x) => {
      /* the identity could not be read: said, so what waits on it can stop waiting */
      if (!x) { setB((was) => ({ ...was, unread: true })); return }
      setB({
        name: x.corpus_name ?? null, whyNot: x.corpus_name_why_not ?? null, path: x.corpus_path ?? null,
        key: spaceBrainKey({ corpusId: x.corpus_id, origin: location.origin, proxy: BRAIN?.brain ?? null }),
      })
    })
  }, [])
  return b
}

/** The Brain's conversations, for the composer's sample target and the rail
 *  in real mode. */
function useConversationList() {
  const [list, setList] = useState(store.list)
  const [why, setWhy] = useState<string | null>(null)
  useEffect(() => {
    /* the rail lists Active conversations only: its page is read that way, so
       archived and trashed ones never take the places of older active ones */
    store.listState = 'active'
    store.loadList().then(() => setList(store.list)).catch((e: unknown) => setWhy(`Could not reach a Mentis server: ${String(e)}`))
    /* reread by the change feed (the dock follows it): the rail shows what it read */
    return store.subscribe('coll:conversations', () => setList(store.list))
  }, [])
  return { list, why }
}

const Glyph = ({ a }: { a: Arrangement }) => (
  <svg width="18" height="14" viewBox="0 0 18 14" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="1.3">
    <rect x=".65" y=".65" width="16.7" height="12.7" rx="2" />
    {a !== 'one' && <path d={a === 'two' ? 'M9 1v12' : 'M6.5 1v12M11.5 1v12'} />}
  </svg>
)

function Choice<T extends string>({ label, value, options, onChange }: {
  label: string; value: T; options: { v: T; label: ReactNode; title?: string }[]; onChange: (v: T) => void
}) {
  return (
    <div className="q2-set-row">
      <span className="q2-set-label">{label}</span>
      <span className="q2-seg" role="radiogroup" aria-label={label}>
        {options.map((o) => (
          <button key={o.v} role="radio" aria-checked={value === o.v} title={o.title} onClick={() => onChange(o.v)}>{o.label}</button>
        ))}
      </span>
    </div>
  )
}

/* SETTINGS: layout and look, shown in the global dock's Settings panel (its
   one entry point). Its Layout section holds every layout control. */
function Settings({ arr, setArr, side, setSide, receded, setReceded, measure, setMeasure }: {
  arr: Arrangement; setArr: (a: Arrangement) => void
  side: Side; setSide: (s: Side) => void
  receded: boolean; setReceded: (r: boolean) => void
  measure: Measure; setMeasure: (m: Measure) => void
}) {
  const [tab, setTab] = useState<'layout' | 'look'>('layout')
  return (
    <div className="q2-settings q2-settings-body">
      {(
        <div className="q2-settings-panel" role="group" aria-label="Settings">
          <div className="q2-settings-tabs" role="tablist" aria-label="Settings">
            <button role="tab" aria-selected={tab === 'layout'} onClick={() => setTab('layout')} title="Layout">
              <svg width="18" height="16" viewBox="0 0 18 14" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="1.3"><rect x=".65" y=".65" width="16.7" height="12.7" rx="2" /><path d="M6.5 1v12M11.5 1v12" /></svg>
              <span>Layout</span>
            </button>
            <button role="tab" aria-selected={tab === 'look'} onClick={() => setTab('look')} title="Backgrounds and theme" aria-label="Backgrounds and theme">
              <svg width="18" height="18" viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="1.5">
                <path d="M12 3a9 9 0 0 0 0 18c1.1 0 1.8-.8 1.8-1.7 0-.5-.2-.9-.5-1.2-.3-.4-.5-.8-.5-1.3 0-1 .8-1.8 1.8-1.8h2.1A4.3 4.3 0 0 0 21 10.7C21 6.4 17 3 12 3Z" />
                <circle cx="7.5" cy="11" r="1.2" /><circle cx="10" cy="7" r="1.2" /><circle cx="15" cy="7" r="1.2" />
              </svg>
            </button>
          </div>
          {tab === 'look' ? <LookGallery /> : <>
          <section aria-label="Layout">
            <h2>Layout</h2>
            <Choice label="Columns" value={arr} onChange={setArr} options={[
              { v: 'one', label: <><Glyph a="one" /> One</>, title: 'Conversation only' },
              { v: 'two', label: <><Glyph a="two" /> Two</>, title: 'Conversation beside a working surface' },
              { v: 'three', label: <><Glyph a="three" /> Three</>, title: 'Conversation and two working surfaces' },
            ]} />
            <Choice label="Conversation" value={side} onChange={setSide} options={[
              { v: 'left', label: 'Left' }, { v: 'right', label: 'Right' },
            ]} />
            <Choice label="Conversation is" value={receded ? 'receded' : 'shown'} onChange={(v) => setReceded(v === 'receded')} options={[
              { v: 'shown', label: 'Restored', title: 'Restore the conversation to its place' },
              { v: 'receded', label: 'Receded', title: 'Let the conversation recede to the edge; the surfaces take its space' },
            ]} />
            <p className="q2-set-note">Drag the dividers between columns to resize them.</p>
          </section>
          <section aria-label="Reading measure (round 1 comparison)">
            <h2>Reading measure <span>for review</span></h2>
            <Choice label="Measure" value={measure} onChange={setMeasure} options={[
              { v: 'current', label: MEASURES.current.label }, { v: 'wide', label: MEASURES.wide.label },
            ]} />
          </section>
          </>}
        </div>
      )}
    </div>
  )
}

function Surface({ n }: { n: number }) {
  return (
    <div className="q2-surface-inner">
      <p className="q2-surface-kicker">Working surface {n}</p>
      <p>A document, a board, a run's activity or the 3D Brain would sit here. Round 1 shows only the arrangement; nothing is docked.</p>
    </div>
  )
}

/** Panes in a row with draggable dividers. Sizes are fractions of the row;
 *  a drag moves the boundary between two neighbours, never below either's
 *  minimum, so the row never needs to scroll sideways. */
function Panes({ panes, sizes, setSizes, render, onSettled }: {
  panes: Pane[]; sizes: number[]; setSizes: (s: number[]) => void; render: (p: Pane) => ReactNode
  /** a resize finished (a drag let go, or a key step): the sizes are kept */
  onSettled?: () => void
}) {
  const row = useRef<HTMLDivElement>(null)
  const [width, setWidth] = useState(0)
  useLayoutEffect(() => {
    const el = row.current
    if (!el) return
    const ro = new ResizeObserver(() => setWidth(el.clientWidth))
    ro.observe(el); setWidth(el.clientWidth)
    return () => ro.disconnect()
  }, [])
  /* where the window is too narrow for every minimum, minimums give way */
  const room = width - (panes.length - 1) * 9
  const mins = panes.reduce((n, p) => n + MIN[p], 0) <= room ? panes.map((p) => MIN[p]) : panes.map(() => 0)

  /* a boundary moved by `dx` from where it stood in `base`: a drag always
     measures from where it began, so no step is lost or doubled */
  const move = (i: number, dx: number, base: number[] = sizes) => {
    if (room <= 0) return
    const next = [...base]
    const pair = next[i] + next[i + 1]
    const lo = mins[i] / room, hi = pair - mins[i + 1] / room
    next[i] = Math.min(Math.max(next[i] + dx / room, lo), Math.max(lo, hi))
    next[i + 1] = pair - next[i]
    setSizes(next)
  }
  const drag = (i: number) => (e: React.PointerEvent<HTMLDivElement>) => {
    e.preventDefault()
    const el = e.currentTarget
    el.setPointerCapture(e.pointerId)
    const start = e.clientX, base = [...sizes]
    const on = (ev: PointerEvent) => move(i, ev.clientX - start, base)
    const off = () => {
      el.removeEventListener('pointermove', on); el.removeEventListener('pointerup', off); el.removeEventListener('pointercancel', off)
      el.classList.remove('dragging'); document.body.classList.remove('q2-resizing')
      /* after the last move has been drawn */
      requestAnimationFrame(() => onSettled?.())
    }
    el.addEventListener('pointermove', on); el.addEventListener('pointerup', off); el.addEventListener('pointercancel', off)
    el.classList.add('dragging'); document.body.classList.add('q2-resizing')
  }
  return (
    <div className="q2-panes" ref={row}>
      {panes.map((p, i) => (
        <PaneSlot key={p} p={p} grow={sizes[i] ?? 1} min={mins[i]} last={i === panes.length - 1}
          divider={i < panes.length - 1 ? (
            <div className="q2-divider" role="separator" aria-orientation="vertical" tabIndex={0}
              aria-label={`resize ${p === 'conv' ? 'the conversation' : 'surface ' + p.slice(1)}`}
              aria-valuenow={Math.round((sizes[i] ?? 0) * 100)} aria-valuemin={0} aria-valuemax={100}
              onPointerDown={drag(i)}
              onKeyDown={(e) => { if (e.key === 'ArrowLeft' || e.key === 'ArrowRight') { e.preventDefault(); move(i, (e.key === 'ArrowLeft' ? -1 : 1) * room * 0.02); requestAnimationFrame(() => onSettled?.()) } }} />
          ) : null}>
          {render(p)}
        </PaneSlot>
      ))}
    </div>
  )
}

function PaneSlot({ p, grow, min, children, divider }: { p: Pane; grow: number; min: number; last: boolean; children: ReactNode; divider: ReactNode }) {
  return (
    <>
      <div className={p === 'conv' ? 'q2-pane q2-conv' : 'q2-pane q2-surface'} style={{ flex: `${grow} 1 0px`, minWidth: min }}
        aria-label={p === 'conv' ? undefined : `working surface ${p.slice(1)}`} role={p === 'conv' ? undefined : 'region'}>
        {children}
      </div>
      {divider}
    </>
  )
}

const minutesSince = (at: number | null) => at ? Math.max(1, Math.round((Date.now() / 1000 - at) / 60)) : 60 * 24 * 365

/** The reader, as this Brain names them: whose posts they may edit. */
function useMe() {
  const [me, setMe] = useState<Id | null>(store.me)
  useEffect(() => { store.loadMe().then(setMe, () => {}) }, [])
  return me
}

/* CONVERSATION-WIDE TOOLS, in the conversation's own header: who is in it
   (and filtering by them), its instructions (Fluid's own), its link. Post
   actions stay on posts; Brain navigation stays on the logo; layout stays in
   Settings. */
function ConversationTools({ people, conversation, name, named, who, setWho, say, onRenamed, trashed, onNewInstruction, onOpenRecord }: {
  people: Person[]; conversation: Id | null; name: string
  /** in Trash: no Rename here (restore it first) */
  trashed?: boolean
  /** the name to start a rename from: empty while it is still unnamed */
  named: string
  who: Person | null; setWho: (p: Person | null) => void; say: (w: string) => void
  /** a rename was recorded: whatever shows the name reads it again */
  onRenamed: () => void
  /** write an instruction for this conversation: the compact Brain editor */
  onNewInstruction: () => void
  /** an instruction listed here, opened as its record */
  onOpenRecord: (id: Id) => void
}) {
  const [open, setOpenNow] = useState<null | 'people' | 'instructions' | 'rename'>(null)
  const box = useRef<HTMLDivElement>(null)
  /* THE INSTRUCTIONS BOX HOLDS NOTHING TYPED: it lists what applies and
     opens the compact Brain editor to write one, so closing it loses nothing. */
  const setOpen = setOpenNow
  const closing = useRef(setOpen)
  closing.current = setOpen
  useEffect(() => { setOpenNow(null) }, [conversation])
  useEffect(() => {
    if (!open) return
    const away = (e: PointerEvent) => { if (!box.current?.contains(e.target as Node)) closing.current(null) }
    const esc = (e: KeyboardEvent) => { if (e.key === 'Escape') closing.current(null) }
    document.addEventListener('pointerdown', away); document.addEventListener('keydown', esc)
    return () => { document.removeEventListener('pointerdown', away); document.removeEventListener('keydown', esc) }
  }, [open])
  /* this interface's own address for the conversation */
  const link = conversation ? `${location.origin}${location.pathname}?c=${encodeURIComponent(conversation)}` : location.href
  return (
    <div className="q2-conv-tools" role="toolbar" aria-label="conversation tools" ref={box}>
      <button aria-expanded={open === 'people'} aria-haspopup="menu" onClick={() => setOpen(open === 'people' ? null : 'people')}
        className={who ? 'on' : undefined}>
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true"><circle cx="9" cy="8" r="3.5" /><path d="M2.5 20a6.5 6.5 0 0 1 13 0M16 4.5a3.5 3.5 0 0 1 0 7M18 14a6 6 0 0 1 3.5 6" /></svg>
        <span>{who ? who.name.replace(/^@/, '') : `${people.length} participants`}</span>
      </button>
      {conversation && !READ_ONLY && <button aria-expanded={open === 'instructions'} aria-haspopup="dialog" onClick={() => setOpen(open === 'instructions' ? null : 'instructions')}>
        <span aria-hidden="true">≡</span><span>Instructions</span>
      </button>}
      {conversation && !READ_ONLY && !trashed && <button aria-expanded={open === 'rename'} aria-haspopup="dialog" onClick={() => setOpen(open === 'rename' ? null : 'rename')}
        title="Rename this conversation">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M4 20h4L19 9l-4-4L4 16v4Z" /><path d="m13.5 6.5 4 4" /></svg>
        <span>Rename</span>
      </button>}
      <button onClick={() => { void navigator.clipboard?.writeText(link).then(() => say('Link to the conversation copied.'), () => say('Could not reach the clipboard.')) }}>
        <span>Copy link</span>
      </button>
      {open === 'people' && (
        <div className="q2-menu q2-people" role="menu" aria-label="participants">
          <p className="q2-menu-head">Show only posts by, or asked by</p>
          {people.map((p) => (
            <button key={p.id} role="menuitemradio" aria-checked={who?.id === p.id} onClick={() => { setWho(who?.id === p.id ? null : p); setOpen(null) }}>
              <Avatar id={p.id} name={p.name} size={20} /> <span>{p.name.replace(/^@/, '')}</span>{p.agent && <span className="q2-agent">agent</span>}
            </button>
          ))}
          {who && <button role="menuitem" className="q2-menu-clear" onClick={() => { setWho(null); setOpen(null) }}>Show everyone</button>}
        </div>
      )}
      {open === 'instructions' && conversation && (
        <div className="q2-menu q2-instructions" role="dialog" aria-label={`instructions for ${name}`}>
          <InstructionsPanel key={conversation} conversation={conversation} name={name} canWrite={!READ_ONLY}
            onNew={() => { setOpenNow(null); onNewInstruction() }} onOpen={(id) => { setOpenNow(null); onOpenRecord(id) }} />
        </div>
      )}
      {open === 'rename' && conversation && (
        <RenameConversation conversation={conversation} named={named}
          done={(renamed) => { setOpen(null); if (renamed) { say(`Renamed “${renamed}”.`); onRenamed() } }} />
      )}
    </div>
  )
}

/* RENAMING A CONVERSATION: Mentis's own act (Fluid's `renameConversation`,
   `Conversations.rename_conversation`): a new version of the same
   Conversation, with the act that says so; its id, posts, replies and work
   stay where they are. By the reader, as Fluid's Save does it. One operation
   key per name asked for, kept across a lost answer so a retry is the same
   operation. Enter saves, Escape lets it go. */
function RenameConversation({ conversation, named, done }: { conversation: Id; named: string; done: (renamed: string | null) => void }) {
  const [text, setText] = useState(named)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const op = useRef<{ name: string; op: string } | null>(null)
  const input = useRef<HTMLInputElement>(null)
  useEffect(() => { input.current?.focus(); input.current?.select() }, [])
  const want = text.trim()
  const save = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!want || want === named.trim() || busy) return
    setBusy(true); setErr(null)
    if (op.current?.name !== want) op.current = { name: want, op: newOp() }
    try {
      const author = store.me ?? await store.loadMe()
      const got = await store.renameConversation(conversation, author, want, op.current.op)
      op.current = null
      done(got.name ?? want)
    } catch (x: unknown) {
      if ((x as { serverAnswer?: boolean })?.serverAnswer) op.current = null
      setErr(x instanceof Error ? x.message : String(x))
      setBusy(false)
    }
  }
  return (
    <form className="q2-menu q2-rename" role="dialog" aria-label="Rename this conversation" onSubmit={(e) => void save(e)}
      onKeyDown={(e) => { if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); done(null) } }}>
      <label className="q2-menu-head" htmlFor="q2-rename-input">Rename this conversation</label>
      <input id="q2-rename-input" ref={input} className="q2-rename-input" value={text} maxLength={200} disabled={busy}
        placeholder="A name for this conversation" onChange={(e) => setText(e.target.value)} />
      {err && <p className="q2-editor-err" role="alert">{err}</p>}
      <div className="q2-editor-row">
        <span className="q2-rename-note">Its posts, replies and work stay with it.</span>
        <span className="q2-toolbar-gap" />
        <button type="button" className="q2-link" onClick={() => done(null)} disabled={busy}>Cancel</button>
        <button type="submit" className="q2-editor-save" disabled={busy || !want || want === named.trim()}>{busy ? 'Saving…' : 'Save'}</button>
      </div>
    </form>
  )
}

/* A maximised viewer: over the work row, which is inert behind it; focus
   moves into it, Escape closes it, and focus returns to what opened it. */
/** what last opened a viewer, recorded before the row behind goes inert */
let openedBy: HTMLElement | null = null

/** WHAT TAB MAY REACH INSIDE THE MAXIMISED FRAME. The frame's own controls and
 *  whatever the renderer draws, in document order; anything hidden, disabled or
 *  taken out of the order by its own renderer is not one of them. */
const TABBABLE = 'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), iframe, [tabindex]:not([tabindex="-1"])'

function MaxLayer({ id, actions }: { id: string; actions: ViewerActions }) {
  const box = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const opener = openedBy
    box.current?.querySelector<HTMLElement>('.q2v-head button')?.focus()
    /* after the row behind is no longer inert: the next frame */
    return () => { requestAnimationFrame(() => { if (opener?.isConnected) opener.focus() }) }
  }, [])
  /* TAB STAYS IN THE DIALOG IT IS DRAWN AS (independent rendered review
     adm-d4c77f502b8c, F7). The frame already declares itself `role="dialog"
     aria-modal="true"`, moves focus in and closes on Escape, and the work row
     behind it is inert -- but the Tab order runs on past the last control into
     the rest of the document, so sixteen presses put focus on the body, outside
     a modal that says nothing else exists. The loop is the frame's own usable
     controls, in document order, and it only acts on Tab: every other key,
     including whatever a renderer binds, is untouched, and a renderer that has
     already handled a Tab itself (`defaultPrevented`) keeps it. */
  const keepTab = (e: React.KeyboardEvent) => {
    if (e.key !== 'Tab' || e.defaultPrevented || !box.current) return
    const all = [...box.current.querySelectorAll<HTMLElement>(TABBABLE)]
      .filter((el) => el.offsetParent !== null || el === document.activeElement)
    if (!all.length) { e.preventDefault(); box.current.focus(); return }
    const at = all.indexOf(document.activeElement as HTMLElement)
    const last = all.length - 1
    /* only the edges are moved: inside the frame the browser's own order is
       what a reader expects, and nothing here reorders it */
    if (!e.shiftKey && (at === last || at === -1)) { e.preventDefault(); all[0].focus(); return }
    if (e.shiftKey && (at === 0 || at === -1)) { e.preventDefault(); all[last].focus() }
  }
  return (
    <div className="q2-max-layer" ref={box} role="dialog" aria-modal="true" aria-label="Viewer" tabIndex={-1}
      onKeyDown={(e) => {
        if (e.key === 'Escape' && !e.defaultPrevented) { e.preventDefault(); (actions.restore ?? actions.close)(); return }
        keepTab(e)
      }}>
      <Viewer id={id} placement="max" actions={actions} />
    </div>
  )
}

/* the renderer's own test stage, in development only */
const HarnessView = lazy(() => import('./viewer/Harness'))

export default function Quiet2() {
  /* a renderer's own test stage (viewer/Harness.tsx), outside the product */
  const harness = import.meta.env.DEV ? params.get('harness') : null
  /* which Brain, and whether it may be written, is known before anything is drawn */
  const [ready, setReady] = useState(false)
  useEffect(() => { void loadBrain().finally(() => setReady(true)) }, [])
  if (harness) return <Suspense fallback={null}><HarnessView kind={harness} /></Suspense>
  return ready ? <Quiet2Page /> : null
}

/* WHICH BRAIN, IN THE TOP LINE: its name and whether it may be written; on
   the development server, a click offers the other one. Choosing reloads the
   page on it, so nothing written here is carried across. */
function BrainState() {
  const [open, setOpen] = useState(false)
  const [moved, setMoved] = useState<string | null>(null)
  const box = useRef<HTMLSpanElement>(null)
  /* another tab chose another Brain: this one says so (its own reads stay its own) */
  useEffect(() => {
    if (!BRAIN) return
    const check = () => { void brainNow().then((b) => setMoved(b && b !== BRAIN!.brain ? b : null)) }
    window.addEventListener('focus', check)
    return () => window.removeEventListener('focus', check)
  }, [])
  useEffect(() => {
    if (!open) return
    const away = (e: PointerEvent) => { if (!box.current?.contains(e.target as Node)) setOpen(false) }
    const esc = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpen(false) }
    document.addEventListener('pointerdown', away); document.addEventListener('keydown', esc)
    return () => { document.removeEventListener('pointerdown', away); document.removeEventListener('keydown', esc) }
  }, [open])
  if (BRAIN_ERROR) return <span className="q2-readonly-badge" role="alert" title="The development server did not say which Brain this is, so nothing that writes is offered">Brain unknown · read-only</span>
  if (!BRAIN) return READ_ONLY ? <span className="q2-readonly-badge" title="This preview reads the Brain only">Read-only</span> : null
  const b = BRAIN
  return (
    <span className="q2-brain-state" ref={box}>
      <button className={'q2-readonly-badge q2-brain-' + b.brain} aria-haspopup="menu" aria-expanded={open} onClick={() => setOpen(!open)}
        title={b.readOnly ? `${b.label}: read-only. Nothing can be posted, replied, edited or changed.` : `${b.label}: writing is on (posting, replying, editing).`}>
        {b.label} · {b.readOnly ? 'read-only' : 'writes on'}
      </button>
      {moved && <span className="q2-brain-moved" role="alert">Another tab chose {b.choices.find((c) => c.brain === moved)?.label}. <button className="q2-link" onClick={() => location.reload()}>Reload</button></span>}
      {open && (
        <span className="q2-menu q2-brain-menu" role="menu" aria-label="Brain">
          <span className="q2-menu-head">This page reads</span>
          {b.choices.map((c) => (
            <button key={c.brain} role="menuitemradio" aria-checked={c.brain === b.brain}
              onClick={() => { if (c.brain !== b.brain) void switchBrain(c.brain); else setOpen(false) }}>
              <span>{c.label}</span><span className="q2v-menu-sub">{c.readOnly ? 'read-only: nothing is written' : 'disposable: writing is on'}</span>
            </button>
          ))}
          <span className="q2-brain-note">Switching reloads the page on that Brain. Unsent words and open views stay with the Brain they were written in.</span>
        </span>
      )}
    </span>
  )
}

/** Bound a reading-place restore while its conversation is being fetched. */
const PLACE_MS = 10000

function Quiet2Page() {
  const postsVersion = usePosts()
  const [who, setWho] = useState<Person | null>(null)
  const [topic, setTopic] = useState<string | null>(null)
  /* THE READER'S PREFERENCES (prefs.ts): the workspace as this Brain's page
     was left, the look as the reader keeps it everywhere. The address
     overrides them for this load; only the reader's own changes are saved. */
  const [saved] = useState(() => ({ ws: readWorkspace(), prefs: readPrefs() }))
  const [arr, setArrNow] = useState<Arrangement>(pick('arr', ['one', 'two', 'three'], saved.ws.arr))
  const [side, setSideNow] = useState<Side>(pick('side', ['left', 'right'], saved.ws.side))
  const [receded, setRecededNow] = useState(params.has('receded') ? params.get('receded') === '1' : saved.ws.receded)
  const [measure, setMeasureNow] = useState<Measure>(pick('measure', ['current', 'wide'], saved.prefs.measure))
  /* THE READER'S OWN LAST WORD ON THE LAYOUT, counted: a presentation
     override taken to show something (space/, a receded conversation brought
     back for a reader) is put back only while this has not moved since. */
  const layoutRev = useRef(0)
  const setArr = (a: Arrangement) => { layoutRev.current++; setArrNow(a); saveWorkspace({ arr: a }) }
  const setSide = (s: Side) => { layoutRev.current++; setSideNow(s); saveWorkspace({ side: s }) }
  const setReceded = (r: boolean) => { layoutRev.current++; setRecededNow(r); saveWorkspace({ receded: r }) }
  const setMeasure = (m: Measure) => { setMeasureNow(m); savePrefs({ measure: m }) }
  /* REAL CONTENT by default: the Brain's own conversations. The sample and
     the long-form reel are fixtures for isolated UI checks, asked for by
     address only (content=sample, content=long) */
  const [content, setContent] = useState<Content>(pick('content', ['sample', 'real', 'long'], 'real'))
  /* the conversation asked for by address, else the one last chosen on this Brain */
  const [chosen, setRealId] = useState<string | null>(params.get('c') ?? saved.ws.conversation)
  /** a remembered conversation not yet confirmed readable */
  const restoredC = useRef(params.get('c') ? null : saved.ws.conversation)
  const [sizes, setSizesAll] = useState<Record<string, number[]>>(saved.ws.sizes)
  const sizesRef = useRef(sizes)
  sizesRef.current = sizes
  const [replyTo, setReplyTo] = useState<PostT | null>(null)
  /* a thread read in the reading column, in place of the flow */
  const [entered, setEntered] = useState<Id | null>(null)
  /* THE CONVERSATION AS IT WAS LEFT for a thread: where it was scrolled,
     what was being answered, which thread; Back puts all three back */
  const left = useRef<{ scroll: number; offset: number | null; replyTo: PostT | null; root: Id } | null>(null)
  const [enteredAt, setEnteredAt] = useState<Id | null>(null)
  const [returned, setReturned] = useState<Id | null>(null)
  const [surfaces, setSurfaces] = useState<Record<'s1' | 's2', SurfaceView | null>>({ s1: null, s2: null })
  /* a global dock panel kept beside the conversation, in a working column */
  const [dockPanels, setDockPanels] = useState<Record<'s1' | 's2', DockPanel | null>>({ s1: null, s2: null })
  const [notice, setNotice] = useState<string | null>(null)
  /* where content opens when every working column is in use (the reader
     chooses); declared here because the graph's host is told whether the work
     row behind it is inert, and this is one of the things that makes it so */
  /* THE CHOOSER IS ONE STATE FOR BOTH CALLERS (HOST-INTEGRATION.md §1.3): a
     `ColumnChoice` whose `decide` belongs to whoever asked. A result's
     placement, its registration and its history entry are made in
     `results/mount.ts` however the reader answers, so the three buttons say
     only which column -- or that the reader cancelled. The page's own
     pictures keep their own `decide`, which registers nothing. */
  const [choosing, setChoosing] = useState<ColumnChoice | null>(null)
  const brain = useBrain()
  const [magnetSignal, setMagnetSignal] = useState(0)
  const surfaceVars = useSurfaceVars()
  const topBar = useTopBar()
  const viewerLayout = useViewerLayout()
  const viewersNow = () => [...viewerLayout.values()]
  const maxNow = maximised()
  /** whether column `s` has words written in its composer */
  const surfaceDraft = (s: 's1' | 's2') => !!(document.querySelector(`[data-surface="${s.slice(1)}"] textarea`) as HTMLTextAreaElement | null)?.value
  const me = useMe()
  const { list, why } = useConversationList()
  const isReal = content !== 'sample'
  const [reread, setReread] = useState(0)
  /* the conversation read: the one chosen, else the Brain's most recently
     active named conversation */
  const named = (list ?? []).filter((c) => c.name && !/^unnamed/i.test(c.name) && (c.state ?? 'active') === 'active')
  /* conversations started on this page (and the one shown): on the rail
     while still unnamed */
  const [started, setStarted] = useState<string[]>([])
  const realId: string | null = chosen ?? named[0]?.id ?? null
  /* `at=<number>`: a real conversation read around one post (Mentis's own
     `around` read), rather than its latest threads */
  const at = opened.at && realId === opened.c ? Number(opened.at) : undefined
  /* A TOPIC IN FORCE is read from the Brain (its posts, not only those of the
     latest threads): its id from the topics this conversation was read with */
  const topicIds = useRef(new Map<string, string>())
  const topicId = content === 'real' && topic ? topicIds.current.get(topic) : undefined
  const real = useRealFlow(isReal ? content : null, realId, reread, at, topicId)
  const readingNow = useRef({ conversation: realId, read: real.read?.conversation })
  readingNow.current = { conversation: realId, read: real.read?.conversation }
  const placing = useRef(0)
  useEffect(() => () => { placing.current++ }, [])
  for (const t of real.read?.topics ?? []) if (t.id) topicIds.current.set(t.name, t.id)
  /* A REMEMBERED CONVERSATION THAT CANNOT BE READ (gone from this Brain, a
     fresh development copy): forgotten, and the Brain's most recent read */
  useEffect(() => {
    if (!restoredC.current || chosen !== restoredC.current) return
    if (real.read) { restoredC.current = null; return }
    if (real.error && /\b404\b|not found|no such|unknown conversation/i.test(real.error)) { restoredC.current = null; saveWorkspace({ conversation: null }); setRealId(null) }
  }, [real.read, real.error, chosen])
  /* PERMANENT DELETION'S CONFIRMATION, over the whole workspace: reachable
     only when the server says deletion is available and Trash's work check
     passes (`manage.menuFor`) */
  const [danger, setDanger] = useState<Conversation | null>(null)
  /* bumped to open the conversation list again, focus in it (back from it) */
  const [listSignal, setListSignal] = useState(0)
  /* THE BRAIN BROWSER (Manage Brain, round 2): the rail's Brain icon opens
     this card over the conversation; its own filter and search stay while
     it is open (DESIGN-r2.md, "Navigation" §2) */
  const [brainOpen, setBrainOpen] = useState(false)
  const [brainFilter, setBrainFilter] = useState<BrainFilter>('knowledge')
  const [brainQuery, setBrainQuery] = useState('')
  /* THE BRAIN IN THE MAIN READING AREA: a record opened from the browser
     (or a post, where no working surface is free), what it led to, and the
     forms the old Governance page offered. The conversation waits under it:
     where it was read is kept and put back on return. */
  /* WHAT THE ADDRESS ASKED FOR is what the page opens on (address.ts): a
     record, a source, the Sources browser. It is the first entry of the
     history, in place, not something opened afterwards on top of it. */
  const [firstAt] = useState<CentreAt>(() => (pick('content', ['sample', 'real', 'long'], 'real') !== 'sample' ? centreFor(opened.asked) : null))
  const [brainMain, setBrainMain] = useState<BrainMainState | null>(firstAt?.brain ?? null)
  /* AN ADDRESS THAT NAMES SOMETHING THIS BRAIN DOES NOT HOLD: said, above the
     conversation that is shown instead, until the reader goes somewhere. */
  const [unread, setUnread] = useState<string | null>(opened.asked.what === 'nothing' ? opened.asked.words : null)
  /* A BRAIN RECORD BEING MADE: the compact editor, over whatever is here.
     Never part of the composer; the workspace behind it is not touched. */
  const [authorNew, setAuthorNew] = useState<AuthorRequest | null>(null)
  const brainLeft = useRef<number | null>(null)
  const brainNow = useRef<BrainMainState | null>(null)
  brainNow.current = brainMain
  /* the record the reader left to look at a post it pointed to: one step back */
  const [brainReturn, setBrainReturn] = useState<BrainMainState | null>(null)
  const [brainPreview, setBrainPreview] = useState<{ persona?: Id } | null>(null)
  /* MANAGE SOURCES (sources/): the rail's data-store icon opens the Sources
     browser, the Brain browser's own card; a source opened from it takes
     the centre reading column exactly as a Brain record does, and the
     conversation waits under it with its place kept (`brainLeft`, the one
     remembered place for whatever takes the centre). The sources are read
     once here, from the first time either is opened, so the card and the
     page never disagree; a refresh in progress is followed while one of
     them is in view (a run is not in the record, so nothing announces it). */
  const [sourcesOpen, setSourcesOpen] = useState(!!firstAt?.sources)
  /* UNFINISHED WORK IN THE WAY (leaving.ts): what was asked, and what to do
     when the reader says to go anyway. Only ever asked, never refused. */
  const [leave, setLeave] = useState<{ ask: Ask; go: () => void; stay?: () => void } | null>(null)
  const [sourceMain, setSourceMain] = useState<SourceMainState | null>(firstAt?.source ?? null)
  const [sourceLast, setSourceLast] = useState<Id | null>(firstAt?.source?.view.page === 'source' ? firstAt.source.view.col : null)
  const [sourcesWanted, setSourcesWanted] = useState(!!firstAt?.source || !!firstAt?.sources)
  const sourcesRead = useApi<SourcesAnswer>(isReal && sourcesWanted ? '/api/sources' : null)
  const sourcesInView = sourcesOpen || !!sourceMain
  const sourcesRunning = !!sourcesRead.data?.collections.some((c) => c.run?.state === 'running')
  useEffect(() => {
    if (!sourcesInView || !sourcesRunning) return
    const t = window.setInterval(() => sourcesRead.reload(), 2000)
    return () => clearInterval(t)
  }, [sourcesInView, sourcesRunning]) // eslint-disable-line react-hooks/exhaustive-deps
  /* never both browsers at once, however the Brain's was opened. The Sources
     browser is an entry of the history (it has an address); the Brain's card
     is not, so the entry gives the browser up in place and the card stays. */
  const keepBrainCard = useRef(false)
  useEffect(() => {
    if (!brainOpen) return
    if (centreAt.current?.sources) { keepBrainCard.current = true; centre.replace(null); keepBrainCard.current = false } else setSourcesOpen(false)
  }, [brainOpen]) // eslint-disable-line react-hooks/exhaustive-deps
  /* WHAT TAKES THE CENTRE COLUMN IS AN ENTRY OF THE BROWSER'S HISTORY
     (centreHistory.ts): a source, a file read in place, Add a source, a
     Brain record. Every way into and out of the centre goes through
     `centre`, so the page's Back controls and the browser's Back walk the
     same entries, and Back never leaves Quiet Chat for another page while
     there is somewhere in it to go back to. State is set in ONE place,
     here, whichever of them moved. */
  /* THE GRAPH'S SIDE OF AN ENTRY (space/), reached through a ref because the
     page's placement is known further down. It never holds a graph, a read or
     a camera: only which session, and what is being read. */
  const spaceRef = useRef<{
    apply: (to: SpaceIntent | undefined, how: How) => BrainMainState | null
    onLeftSpace: () => void
  }>({ apply: () => null, onLeftSpace: () => {} })
  const magnetRef = useRef<{
    apply(to: MagnetIntent | undefined): CentreAt;
    affected(to?: unknown): Place[];
  }>({ apply: () => null, affected: () => [CENTRE] })
  const [restoreMagnetOrigin, setRestoreMagnetOrigin] = useState<string | null>(null)
  /** the entry the centre is on now, so a transition knows what is behind it */
  const centreAt = useRef<CentreAt>(firstAt)
  /** THE MOUNTED RESULT OPERATIONS (`results/mount.ts`), built further down
   *  once the page's own moves are known, and reached from the callbacks
   *  above through this ref. The registry, the centre generation and a pending
   *  close's marker are module state in `mount.ts`, so re-mounting on every
   *  render loses nothing (HOST-INTEGRATION.md §1.2). */
  const results = useRef<MountedResults | null>(null)
  /** the explicit way back out of a result, offered by its own close */
  const [resultReturn, setResultReturn] = useState<LaunchContext | null>(null)
  /** the 3D Brain was asked for by address and is not open yet (it opens
   *  once the Brain is known, further down): the address keeps naming it */
  const askedSpace = useRef(opened.asked.what === 'space' && pick('content', ['sample', 'real', 'long'], 'real') !== 'sample')
  /** the conversation an entry of the history is of, shown (set further down,
   *  where what a conversation press does is known) */
  const showRef = useRef<(k: string) => void>(() => {})
  /* EVERY ENTRY SAYS WHICH CONVERSATION IT IS OF, AND HAS AN ADDRESS
     (places.ts, address.ts): the centre's callers still say only what takes
     the centre. */
  const centre = usePlaces({ c: params.get('c') || null, at: firstAt }, { apply: (to, from, how, asked) => {
    /* leaving the conversation: where it was read is kept, once */
    if (!from && to) brainLeft.current = document.querySelector<HTMLElement>('.q2-conv')?.scrollTop ?? null
    /* A RESULT ENTRY IS THE RESULT PART'S (HOST-INTEGRATION.md §1.3, B4.2).
       `R.applyCentre` records the entry through `enterCentre` FIRST, whatever
       it is -- so `centreAt.current` is never left on the Place underneath --
       and then either draws the entry itself, answers the landing of a close
       it has refused (F7-R2b), or takes a maximised result off the centre
       (F16) and leaves the arms below to the page. True means the page applies
       NOTHING of this entry, which is what stops a refused landing writing the
       old Brain's record, source column or Sources browser back (B2).
       The mount is reached through a ref because it is built further down,
       where the page's own moves are known -- the same way `spaceRef`,
       `showRef` and `pickRef` are reached. */
    if (results.current) { if (results.current.applyCentre(to)) return } else centreAt.current = to
    setUnread(null)
    const visible = to?.magnet ? magnetRef.current.apply(to.magnet) : (magnetRef.current.apply(undefined), to)
    if (!keepBrainCard.current) setBrainOpen(false)
    /* THE SOURCES BROWSER IS AN ENTRY: open exactly where the entry says, and
       read again as it opens, since a run started elsewhere is announced by
       nothing */
    setSourcesOpen(!!visible?.sources)
    if (visible?.sources) { setSourcesWanted(true); if (how !== 'replace' && !to?.magnet) sourcesRead.reload() }
    /* THE GRAPH AND THE READER TOGETHER, after the guard: placement, the
       parked graph and what is read are applied in one go, so nothing is
       half-moved (addendum §3). A graph entry's reader is none; an inspect
       entry's reader is derived from its target -- the history holds the
       intent, never a second copy of a record. */
    const fromSpace = spaceRef.current.apply(to?.magnet ? undefined : visible?.space, how)
    setBrainMain(visible?.brain ?? fromSpace ?? null)
    setSourceMain(visible?.source ?? null)
    if (to?.source) { setSourcesWanted(true); if (to.source.view.page === 'source') setSourceLast(to.source.view.col) }
    /* THE BROWSER'S OWN BACK, out of a source or a record opened from its
       browser: the browser card again, as the page's Back gives it */
    if (how === 'pop' && !asked && !to && from) {
      if (from.brain && from.brain.stack.length === 1 && from.brain.origin.from === 'browser') setBrainOpen(true)
    }
  },
  show: (k) => showRef.current(k),
  /* THE BROWSER'S OWN BACK AND FORWARD, off a page holding unfinished work:
     the same question the page's own controls put, put here instead, because
     by the time the browser says it moved it has already moved. Stay walks it
     back to the entry the reader was on. */
  ask: (go, stay, to) => {
    const places = magnetRef.current.affected(to)
    const focus = document.activeElement as HTMLElement | null
    const run = (i: number): boolean => {
      if (i >= places.length) { go(); return false }
      const was = leaving(unfinished(places[i]))
      if (was.ask) { setLeave({ ask: was.ask, go: () => { run(i + 1) }, stay: () => { stay(); requestAnimationFrame(() => focus?.focus()) } }); return true }
      if (was.note) setNotice(was.note)
      return run(i + 1)
    }
    // A no-question path is applied by centreHistory itself.
    const first = places.findIndex((p) => leaving(unfinished(p)).ask)
    if (first < 0) return false
    return run(first)
  },
  /* THEIR OWN FORWARD UNDOING THE BACK THEY WERE ASKED ABOUT: they are back
     where they were, with the question answered by the asking. */
  unask: () => setLeave(null),
  address: (to) => addressOf(location, to, opened, askedSpace.current) })
  /* WHAT THE ADDRESS NAMED THAT COULD NOT BE TAKEN AS WRITTEN (a file that is
     not one, a post number that is not a number): said once. The address has
     already been put right, as the first entry was made. */
  useEffect(() => {
    if (!opened.note) return
    /* it stays until dismissed or the reader goes somewhere, on whatever is
       shown: the conversation, a record, a source, the Sources browser */
    setUnread(opened.note)
  }, []) // eslint-disable-line react-hooks/exhaustive-deps
  const brainMoved = useBrainMoved()
  useEffect(() => guardReload(), [])
  const saidLine = unread ? (
    <p className="q2-filter q2-unread" role="alert">
      <span className="q2-filter-what">{unread}</span>
      <button type="button" className="q2-filter-clear" onClick={() => setUnread(null)}>Dismiss</button>
    </p>
  ) : null
  /* NOTHING UNSAVED LEAVES WITHOUT A QUESTION. Every way OUT of whatever
     holds the centre column -- the page's Back controls, a record's links, a
     conversation press -- comes through here: where leaving would lose work
     it asks once (Stay, or Discard changes and switch), and otherwise it
     simply goes. Merely reading holds nobody: a page that has nothing
     unfinished says nothing, and `unfinished()` then answers null. */
  /* A GUARD THE READER ANSWERED WITH STAY IS AN ANSWER (HOST-INTEGRATION.md
     §1.2, B3): `setLeave` already takes `stay`, and a result's press needs to
     hear it so Stay is reported as the reader's own cancellation rather than
     as silence. Callers that pass no `stay` are unchanged. */
  const guarded = (go: () => void, place: Place = CENTRE, stay?: () => void) => {
    const was = leaving(unfinished(place))
    if (was.ask) { setLeave({ ask: was.ask, go, stay }); return }
    if (was.note) setNotice(was.note)
    go()
  }
  /** somewhere else in the centre column, or out of it: asked about first */
  const goCentre = (to: CentreAt, then?: () => void) =>
    guarded(() => centre.go(to, then))
  /** EVERY PLACE A TRANSITION ACTUALLY DISPLACES, asked in turn, and the move
   *  committed only once they all permit leaving (addendum §3, "One guarded
   *  commit per transition"). Any Stay leaves everything exactly as it is,
   *  because nothing has been applied yet. */
  const guardedAll = (places: Place[], go: () => void) => {
    const focus = document.activeElement as HTMLElement | null
    guardPlaces(places, { standing: unfinished, note: setNotice, commit: go,
      stay: () => requestAnimationFrame(() => focus?.focus()),
      ask: (ask, proceed, stay) => setLeave({ ask, go: proceed, stay }) })
  }
  /* who is working now: Mentis's activity, and the sample's simulated work */
  const working = useWorking(content === 'sample')
  /* after a post: its thread is read again, or the flow for a new post */
  const onPosted = (root: Id | null) => {
    const r = root ? postOf(root) : undefined
    if (r?.real && r.conversation) void readThread(r.conversation, r.root ?? r.id).catch(() => {})
    else if (isReal) setReread((n) => n + 1)
  }
  const dock = useRef<HTMLDivElement>(null)
  /* reading earlier posts adds above: the reader stays where they were */
  const earlierFrom = useRef<number | null>(null)
  useLayoutEffect(() => {
    const pane = document.querySelector<HTMLElement>('.q2-conv')
    if (earlierFrom.current === null || !pane) return
    pane.scrollTop += pane.scrollHeight - earlierFrom.current
    earlierFrom.current = null
  }, [real.read?.top.length])

  const panes = panesOf(arr, side, receded)
  const key = panes.join(',')
  const paneSizes = sizes[key] ?? defaultSizes(panes)
  const surfacePanes = panes.filter((p): p is 's1' | 's2' => p !== 'conv')

  /* -- THE 3D BRAIN (space/, addendum §§1,3,4) ------------------------------
     ONE GRAPH, in a working column or maximised, parked while something is
     read from it and coming back to the same view. Everything about the
     drawing, the camera, the options, the time and the reads belongs to the
     graph module and its session; what is here is placement, the leaving
     question, the browser's history and which reader a chosen thing opens.

     A PARKED GRAPH IS STILL OPEN: it holds its viewer id and its session, and
     nothing but an explicit Close, a Brain change or this page going away
     disposes it. */
  /** the columns as they are at this moment, for placement decisions */
  const room: ColumnRoom = { shown: surfacePanes, free: (s) => !surfaces[s] && !inColumn(s) && !dockPanels[s] }
  const graph = spaceViewer()
  const graphSession = graph ? sessionById((graph.state as SpaceState).sessionId) : null
  const graphShown = !!graph && graph.place !== 'parked'
  const graphParked = !!graph && graph.place === 'parked'
  /** A MAXIMISED VIEWER THAT CANNOT BE SAFELY DISPLACED: nothing else may take
   *  max, because taking it would close content with nowhere to go. */
  const maxBlocked = () => {
    const m = maximised()
    return !!m && m.content.kind !== 'brain-space' && !(m.from && surfacePanes.includes(m.from))
  }
  /* WHERE THE GRAPH GOES is not a placement question at all any more: it is
     always full screen (space/placement.ts `spacePlace`). The generic
     column-or-maximise choice below (`onView`) still answers for every other
     kind of content. */
  const focusGraph = () => requestAnimationFrame(() =>
    document.querySelector<HTMLElement>('.q2-space-stage .q2-space-close')?.focus())
  /* THE CONVERSATION BROUGHT BACK TO SHOW A READER (addendum §3): a receded
     conversation gives up its column, and a record read from the graph would
     have nowhere to be seen. It is restored in memory only -- never saved as
     the reader's preference -- and put back only when the graph returns and
     only if the reader has not changed the layout themselves since. */
  const recededFor = useRef<RecededOverride | null>(null)
  /** what a graph inspect entry is read by: the existing readers, chosen by
   *  the target's own family (routing.ts). Post and Conversation targets are
   *  read in the conversation column, so they hold no Brain page. */
  const readerFor = (t: SpaceDestination): BrainMainState | null =>
    t.kind === 'record' ? { stack: [{ page: 'record', entry: t.entry }], origin: { from: 'space' } }
      : t.kind === 'entry' ? { stack: [{ page: 'entry', entry: t.entry }], origin: { from: 'space' } }
        : null
  spaceRef.current = {
    /* ONE APPLY for every way a graph entry is reached: the first Open, a
       repeated Open, the page's own return, the browser's Back and Forward.
       The guard has already passed by the time this runs. */
    apply: (to) => {
      const v = spaceViewer()
      if (!to) {
        /* ORDINARY NAVIGATION WHILE A GRAPH IS OPEN: it never sits maximised
           over what the reader went to; in a column it is left alone, with
           the other column's content preserved. */
        if (v && v.place === 'max') parkViewer(v.id)
        recededFor.current = null
        return null
      }
      const r = resumeSpace({ space: to }, { brainKey: brain.key ?? null, live: (id) => !!sessionById(id) })
      if (r.how === 'other-brain') return null
      if (r.how === 'expired-graph') {
        /* NEVER RECREATED: an id this page closed, or one from before a
           reload, is gone. The centre becomes the ordinary conversation and
           the reader is told why, once. */
        setNotice(r.notice)
        requestAnimationFrame(() => centre.replace(null))
        return null
      }
      if (r.how === 'expired-inspect') {
        /* its target may still be read -- in THIS Brain, as an ordinary
           reader, with the graph origin stripped */
        const plain = readerFor(r.target)
        requestAnimationFrame(() => centre.replace(plain ? { brain: { stack: plain.stack, origin: { from: 'link' } } } : null))
        if (!plain) showSpaceTargetNow(r.target)
        return plain ? { stack: plain.stack, origin: { from: 'link' } } : null
      }
      if (to.phase === 'inspect') {
        /* INSPECTION ALWAYS PARKS THE GRAPH, in a column as much as
           maximised: the reader is reading, and a canvas is not what they
           asked for. The conversation comes back if it had receded, so the
           reader is actually visible. */
        if (v && v.place !== 'parked') parkViewer(v.id)
        if (receded && !recededFor.current) { recededFor.current = { was: true, atRevision: layoutRev.current }; setRecededNow(false) }
        if (to.target.kind === 'post' || to.target.kind === 'conversation') showSpaceTargetNow(to.target)
        return readerFor(to.target)
      }
      /* A GRAPH ENTRY: the extant graph, shown again, with no reader. */
      if (v && v.place === 'parked') {
        const back = spacePlace()
        if (maxBlocked()) {
          setNotice('Close or restore the maximised view first: the 3D Brain has nowhere to come back to.')
          return null
        }
        returnViewer(v.id, back.place, back.from)
        focusGraph()
      }
      const was = recededFor.current
      if (was && restoresReceded(was, layoutRev.current)) setRecededNow(was.was)
      recededFor.current = null
      return null
    },
    onLeftSpace: () => { recededFor.current = null },
  }
  /** a post or a conversation the graph sent the reader to, shown in the
   *  conversation column without touching the history (the entry is already
   *  the graph's inspect intent) */
  const showSpaceTargetNow = (t: SpaceDestination) => {
    const conv = t.kind === 'post' ? t.conversation : t.kind === 'conversation' ? t.conversation : null
    if (!conv) return
    const here = realId === conv && content === 'real'
    if (!here) { brainLeft.current = null; setRealId(conv); setContent('real'); saveWorkspace({ conversation: conv }) }
    if (t.kind !== 'post') return
    if (here) requestAnimationFrame(() => now.current.showPost(conv, t.post))
    else pendingPost.current = { conversation: conv, post: t.post }
  }
  /** WHETHER THE CENTRE HOLDS A READER NOW. A graph entry shows none, so
   *  everything the centre holds -- a record being written, a source, the very
   *  detail the graph sent the reader to -- is displaced by one, and the
   *  leaving question is owed to it (review R1). The conversation itself is
   *  not displaced: it waits underneath, and its entry is null. */
  const centreHeld = () => !!centreAt.current
  /** THE GRAPH, OPENED OR FOCUSED. The first Open creates the one session for
   *  this Brain; a repeated Open focuses the same view -- no second graph, no
   *  reread and no duplicate history entry -- and a parked one comes back. */
  const openSpace = (inPlace = false) => {
    const bk = brain.key
    if (!bk) { setNotice('Which Brain this page serves is not known yet: the 3D Brain opens once it is.'); return }
    const v = spaceViewer()
    if (v && v.place !== 'parked') { focusGraph(); return }
    /* ALWAYS THE SAME PLACE, whatever the columns happen to hold */
    const to = spacePlace()
    if (maxBlocked()) {
      setNotice('Close or restore the maximised view first: the 3D Brain has nowhere to open.')
      return
    }
    guardedAll(affectedPlaces({ what: 'place', into: to.place, centreHeld: centreHeld() }, room), () => {
      const s = sessionOfBrain(bk) ?? openSession(bk)
      /* asked for by address and not to be had: the address stops naming it */
      if (!s) { setNotice('The 3D Brain is not part of this build yet.'); if (inPlace) centre.replace(null); return }
      openedBy = document.activeElement as HTMLElement | null
      if (!spaceViewer()) openViewer({ kind: 'brain-space' }, { kind: 'brain', brainKey: bk }, to.place, { sessionId: s.id } satisfies SpaceState)
      /* OPENED BY THE ADDRESS, the graph is the entry the page is already on */
      if (inPlace) centre.replace(graphIntent(bk, s.id)); else centre.go(graphIntent(bk, s.id))
    })
  }
  /* THE 3D BRAIN ASKED FOR BY ADDRESS (`space=1`): opened once the Brain this
     page serves is known -- a graph is never opened against a guessed Brain --
     and only if the reader has not gone somewhere else meanwhile. It is a new
     view: a graph's camera and choices live in its session, and a session
     does not outlive the page (space/history.ts). */
  useEffect(() => {
    if (!askedSpace.current || !brain.key || !isReal) return
    askedSpace.current = false
    if (!centreAt.current) openSpace(true)
  }, [brain.key, isReal]) // eslint-disable-line react-hooks/exhaustive-deps
  /* ...AND WHERE THE BRAIN CANNOT BE KNOWN (its identity could not be read, or
     has not come in `SPACE_WAIT_MS`), the address does not go on naming a 3D
     Brain that is not shown (independent review, 2026-11-20): settled once,
     the name taken off, and it is said. */
  const spaceNotOpened = () => {
    if (!askedSpace.current) return
    askedSpace.current = false
    if (centreAt.current) return
    centre.replace(null)
    setUnread(NO_SPACE)
  }
  useEffect(() => { if (brain.unread) spaceNotOpened() }, [brain.unread]) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (!askedSpace.current) return
    const t = window.setTimeout(spaceNotOpened, SPACE_WAIT_MS)
    return () => clearTimeout(t)
  }, []) // eslint-disable-line react-hooks/exhaustive-deps
  /** back to the extant graph, from a reader or from parked. The same entry
   *  the graph was shown by, so the history walks back to it rather than
   *  growing a second one (centreHistory `plan`). */
  const backToSpace = () => {
    const v = spaceViewer()
    const bk = brain.key
    if (!v || !bk) return
    const sid = (v.state as SpaceState).sessionId
    if (!sessionById(sid)) { setNotice(CLOSED_NOTICE); return }
    guarded(() => centre.go(graphIntent(bk, sid)))
  }
  /** WHERE A CHOSEN THING, OR A LINK OFF ITS READER, IS READ (§4). One
   *  dispatcher for both, so a related id is routed by what IT is. */
  const dispatchSpace = (facts: NodeFacts) => {
    const bk = brain.key
    const v = spaceViewer()
    if (!bk || !v) return
    const sid = (v.state as SpaceState).sessionId
    if (!sessionById(sid)) { setNotice(CLOSED_NOTICE); return }
    const r = routeNode(facts)
    if (r.how === 'go') {
      guardedAll(affectedPlaces({ what: 'inspect' }, room), () => {
        const entry = inspectIntent(bk, sid, r.to)
        /* THE GRAPH'S OWN ENTRY IS BEHIND THIS ONE, so Back returns to it --
           and so is the detail this was reached from, so Back visits that
           first (§3; review R2). Walking back to the graph before pushing
           would have truncated the detail being left. */
        if (inspectPath(centreAt.current?.space, sid) === 'push') centre.go(entry)
        else centre.go(graphIntent(bk, sid), () => centre.go(entry))
      })
      return
    }
    /* NOT ENOUGH IS KNOWN YET. The graph's own settled read answers it for
       free where it holds the answer; where it holds the thing but NOT the
       answer -- a Turn it returned with no Conversation -- its silence is not
       the record's, so the record is read before the fallback is taken. The
       read goes through the page's own client (`api.ts` `read`), which carries
       the interface header every JSON route requires: a bare fetch would be
       refused, and the refusal would look exactly like an id the Brain does
       not hold. A read that fails leaves the honest fallback.

       WHAT IS ALREADY KNOWN GOES WITH IT (review R3): a Turn whose kind is
       settled and whose placement is not is asked of its own Turn read
       directly, rather than of an entry read that does not answer that. */
    const known = knownOf(facts, graphSession?.getSnapshot().read.data ?? null)
    if (answers(r.want, known)) { dispatchSpace(known); return }
    const ask = ++asking.current
    void resolveEntryFacts(facts.entry, readJson, known)
      .then((f) => { if (ask === asking.current) now.current.dispatchSpace(f) })
  }
  /** THE ONE RELEASE PATH (addendum §1): the reader's explicit Close. The
   *  session is disposed once, its id is never usable again on this page, and
   *  the entry that named it is replaced rather than left pointing at it. */
  const closeSpace = () => {
    const v = spaceViewer()
    if (!v) return
    const sid = (v.state as SpaceState).sessionId
    const inspecting = centreAt.current?.space?.phase === 'inspect'
    const target = centreAt.current?.space?.phase === 'inspect' ? centreAt.current.space.target : null
    releaseSession(sid)
    closeViewer(v.id)
    recededFor.current = null
    /* CLOSED WHILE A READER IS UP: the reader, its draft and its target stay
       exactly as they are; only the way back to the graph goes. */
    const plain = target ? readerFor(target) : null
    if (centreAt.current?.space) centre.replace(plain ? { brain: { stack: plain.stack, origin: { from: 'link' } } } : null)
    if (!inspecting) requestAnimationFrame(() => focusBrand())
  }
  const focusBrand = () => document.querySelector<HTMLElement>('.q2-brand .brand-menu-open')?.focus()
  /* A BRAIN THAT IS NOT THE ONE THIS PAGE SERVES keeps no graph: its sessions
     are disposed and their ids expired, so an old entry cannot attach. */
  useEffect(() => {
    const key = brainMoved ? null : brain.key ?? null
    invalidateOtherBrains(key)
    for (const v of viewersNow()) if ((v.content.kind === 'magnet' && (!key || v.content.brainKey !== key || !findMagnet(v.content.resourceId))) || (v.source.kind === 'magnet-item' && (!key || v.source.brainKey !== key))) closeViewer(v.id)
  }, [brain.key, brainMoved])
  /* the page going: nothing of a graph survives it */
  useEffect(() => () => releaseAllSessions(), [])
  const spaceHost: SpaceHostApi = {
    onOpen: (node: SpaceNode) => dispatchSpace({ entry: node.entry, kind: node.kind, layer: node.layer, conversation: node.conversation }),
    /* DRAGGED INTO A COMPOSER: exactly the payload Fluid's own Brain place
       carries (fluid/brain/address.ts). Nothing is written by a drag; only
       Send writes. */
    onDragChosen: (node: SpaceNode, e) => {
      for (const [mime, value] of dragPayload(node, location.origin)) e.dataTransfer.setData(mime, value)
      e.dataTransfer.effectAllowed = 'copy'
    },
    inertHost: !!maxNow || !!choosing || !!danger,
  }

  /* what is drawn: the sample, or real posts, all from the one store */
  const top: Id[] = isReal ? real.read?.top ?? [] : POSTS.filter((p) => !p.replyTo).map((p) => p.id)
  /* a conversation still unnamed reads as Fluid shows it ("Unnamed · started …") */
  const unnamed = isReal ? (list ?? []).find((c) => c.provisional && c.id === real.read?.conversation) : undefined
  const name = isReal ? unnamed?.name ?? real.read?.name ?? (why ? 'No Brain' : real.error ? 'This conversation could not be read' : 'Reading…') : CONVERSATION.name
  const total = isReal ? real.read?.total ?? 0 : CONVERSATION.total
  const conversationId = content === 'real' ? realId : null
  /* WHERE IT IS LISTED: an archived or trashed one says so under its title,
     and in Trash its composer gives way to Restore */
  const convRow = useConversationRow(conversationId)
  const trashed = (convRow?.state ?? 'active') === 'trashed'
  /* the conversation a new Brain record is opened from, where there is one */
  const hereNow = conversationId ? { id: conversationId, name } : null
  /* PERMANENTLY DELETED: only its tombstone is shown, never a post of it */
  const deleted = convRow?.state === 'deleted'
  const people: Person[] = isReal
    ? (real.read?.participants ?? []).map((p) => ({ id: p.id, name: p.name, agent: !!top.map(postOf).find((x) => x?.by.id === p.id)?.by.agent }))
    : Object.values(PEOPLE)
  const railConversations: MarkerItem[] = isReal
    ? (list ?? []).filter((c) => (c.state ?? 'active') === 'active' && (started.includes(c.id) || c.id === realId || named.includes(c))).slice(0, 16).map((c) => ({ key: c.id, name: repairText(c.name), count: c.posts, idle: minutesSince(c.last_activity ?? c.created) }))
    : CONVERSATIONS
  /* every topic of the conversation, the most used first */
  const convTopics: string[] = isReal
    ? (real.read?.topics ?? []).slice().sort((a, b) => b.count - a.count).map((t) => t.name)
    : TOPICS.map((t) => t.name)
  const railTopics: MarkerItem[] = isReal
    ? (real.read?.topics ?? []).slice().sort((a, b) => b.count - a.count).slice(0, 8).map((t) => ({ ...t, idle: 60 * 24 * 3 }))
    : TOPICS
  /* where the conversation's composer writes: the conversation shown, or for
     the sample and the reel, the post being answered's own conversation, or
     else the dev Brain's first named one */
  const composerTarget = replyTo?.real && replyTo.conversation ? replyTo.conversation
    : conversationId ?? (named[0]?.id ?? list?.[0]?.id ?? null)

  useEffect(() => { document.title = `${name} · Quiet` }, [name])
  /* Fluid's look for what is shown: the atmosphere, the theme, the controls */
  useLook(conversationId, conversationId ? name : null)
  useEffect(() => { setWho(null); setTopic(null); setEntered(null); setReplyTo(null); topicIds.current.clear() }, [content, realId])
  /* a surface that is no longer shown lets go of what it held */
  useEffect(() => {
    setSurfaces((s) => ({ s1: surfacePanes.includes('s1') ? s.s1 : null, s2: surfacePanes.includes('s2') ? s.s2 : null }))
    setDockPanels((d) => ({ s1: surfacePanes.includes('s1') ? d.s1 : null, s2: surfacePanes.includes('s2') ? d.s2 : null }))
    if (settleColumns(surfacePanes)) setNotice('A viewer from a column that closed is shown maximised (or closed if another was).')
  }, [surfacePanes.join(',')]) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (!notice) return
    const t = setTimeout(() => setNotice(null), 3200)
    return () => clearTimeout(t)
  }, [notice])

  const shown = (p: PostT) => (!who || p.by.id === who.id || p.requestedBy?.id === who.id) && (!topic || !!p.topics?.includes(topic))
  /* posts that do not match the filter fold into one quiet line per run */
  const rows: ({ post: PostT } | { hidden: number; key: string })[] = []
  for (const id of top) {
    const p = postOf(id)
    if (!p) continue
    if (shown(p)) rows.push({ post: p })
    else {
      const last = rows[rows.length - 1]
      if (last && 'hidden' in last) last.hidden++; else rows.push({ hidden: 1, key: 'h-' + p.id })
    }
  }

  /* THE PLACE A VIEW'S COMPOSER WRITES TO (Fluid keeps one draft per
     place): two composers on one place would share and overwrite a draft,
     so a view is never opened where its place is already being written. */
  const placeOf = (v: SurfaceView | null): string | null => {
    if (!v) return null
    if (v.kind === 'conversation') return `conversation:${v.conversation}`
    const p = postOf(v.kind === 'thread' ? v.root : v.kind === 'post' ? v.id : '')
    return (v.kind === 'thread' || v.kind === 'post') && p?.real && p.conversation ? `thread:${p.conversation}:${v.kind === 'thread' ? v.root : v.id}` : null
  }
  const mainPlace = entered && postOf(entered)?.real ? `thread:${postOf(entered)!.conversation}:${entered}` : composerTarget ? `conversation:${composerTarget}` : null
  /* ===================== RESULT-FIRST NAVIGATION, MOUNTED =====================
     HOST-INTEGRATION.md §1.2. Nothing below decides anything: each member is
     something the page already does, with the unsaved-work guard's three ends
     made explicit. */
  /** WHERE THE READER IS NOW, as a launch: identity and position only. The
   *  Brain is the one the SERVER serves, read from `brainBinding.ts` through
   *  `results/serving.ts` -- never `brain.key`, which is the 3D Brain's graph
   *  key and is the same string for two serving instances of one corpus at
   *  one origin (F2). */
  const launchNow = (focus: LaunchFocus, decision?: DecisionLaunch | null): LaunchContext => holdLaunch({
    opening: beginOpening(),
    brainKey: servingBrainKey(),
    place: { conversation: realId, centre: centreAt.current },
    thread: entered ? { root: entered, at: enteredAt } : null,
    reading: { scroll: document.querySelector<HTMLElement>('.q2-conv')?.scrollTop ?? 0, offset: left.current?.offset ?? null },
    reply: replyTo?.id ?? null,
    draft: mainPlace,                       // THE KEY, never the text
    focus, decision: decision ?? null,
  })
  /** WHAT THE WORK IN THIS CONVERSATION ACTUALLY PRODUCED. The existing
   *  bounded overview read (`/api/work?conversation=`), whose items carry the
   *  server's own `result_summary` and its exact `origin` / `update_turns`
   *  mapping; `runs: false` because nothing here shows live run words. */
  const workHere = useWorkOverview({ viewer: null, conversation: isReal ? realId : null, on: isReal && !!realId, runs: false })
  const resultsOf = lookupOf(workHere.data)
  /** READING MORE: the same work detail read, with the server's own cursors.
   *  A moved or foreign cursor comes back as the server's 409 refresh
   *  condition, which the chooser shows as a reload offer.
   *
   *  THE DETAIL READ ANSWERS `result_groups`, AND THAT IS WHAT IS READ
   *  (independent rendered review adm-d4c77f502b8c, F1). `result_summary` is
   *  the OVERVIEW member (`WorkItem`, 8 groups x 4 items); the detail route
   *  (`result_destinations.detail`) puts its paged answer -- 20 x 20, and a
   *  single-group continuation -- in `result_groups` (`WorkDetail`) and does
   *  not carry the overview member at all. So every continuation read threw
   *  "Those results could not be read.": the older generations and the omitted
   *  tails could not be reached through the chooser, which is the
   *  search-through-history this work exists to remove. The refusal path is
   *  unchanged and deliberate: `readJson` throws `ResultsRefreshRequired` for
   *  the server's 409, which the chooser tells apart from a failed read
   *  (`isRefresh`) and answers by dropping its cursors and offering the first
   *  page again, and an answer with no page at all is still said in words
   *  rather than drawn as an empty result set. */
  const readResults = async (path: string): Promise<WorkResultPage> => {
    const body = await readJson<{ result_groups?: WorkResultPage; error?: string }>(path)
    const page = body?.result_groups
    if (!page) throw new Error(body?.error || 'Those results could not be read.')
    return page
  }
  /** WHAT THE CHOOSER ASKS OF THIS PAGE (`results/host.ts`): opening a chosen
   *  result through the one shared operation, its group's source post, and
   *  the continuation reads. The chooser builds no target, URL or viewer. */
  const resultsHost: ResultsHost = {
    open: (c: ResultChoice) => {
      const R = results.current
      if (!R) { setNotice('Results open once this page knows which Brain it is on.'); return }
      const d = destinationOfResult(c.item, { work: c.work, group: c.group.id })
      R.openResult(d, launchNow({ control: `result:${c.group.id}:${c.item.ref}`, fallback: { kind: 'conversation' } }))
    },
    openSource: (c: SourceChoice) => {
      const src = c.group.source
      if (!src) return
      openFromDock(src.conversation, src.turn)
    },
    more: {
      groupsBefore: (work, cursor) => readResults(workDetailPath(work, null, { resultsBefore: cursor })),
      itemsAfter: (work, group, cursor) => readResults(workDetailPath(work, null, { resultGroup: group, itemsAfter: cursor })),
    },
  }
  const openBeside = (v: SurfaceView) => {
    const place = placeOf(v)
    if (place && (place === mainPlace || surfacePanes.some((s) => placeOf(surfaces[s]) === place))) {
      setNotice('That is already open, with its own composer.')
      return
    }
    /* an empty surface only: one in use is never replaced behind its back */
    const free = surfacePanes.find((s) => !surfaces[s] && !inColumn(s) && !dockPanels[s])
    if (!free) { setNotice('Every working surface is in use: close one to open this.'); return }
    setSurfaces((s) => ({ ...s, [free]: v }))
    if (v.kind === 'thread' && entered === v.root) setEntered(null)
  }
  /* a Brain-browser row opens as its own full reading view (DESIGN-r2.md
     "Opened from the Brain browser, a record takes the main reading area");
     reusing the same working-surface machinery as "beside a post" rather
     than a second window system -- closing the browser card first so the
     record, not an empty card, is what the reader sees land */
  const BRAIN_TABS: Record<BrainFilter, string> = { knowledge: 'Knowledge', governing: 'Governing', 'needs-you': 'Needs you', all: 'All' }
  /** into the Brain's reading area: the conversation's place is remembered once */
  const enterBrain = (view: BrainMainView, origin: BrainOrigin) => guarded(() => {
    setBrainReturn(null)
    centre.go({ brain: { stack: [view], origin } })
  })
  const openBrainRecord = (id: string, _summary: BrainRecordSummary) =>
    enterBrain({ page: 'record', entry: id }, { from: 'browser', label: BRAIN_TABS[brainFilter] })
  /** out of the Brain's reading area, to the conversation where it was */
  const leaveBrain = () => goCentre(null)
  /** the Sources browser, opened or closed; never both browsers at once */
  const toggleSources = () => {
    setSourcesWanted(true); setBrainOpen(false)
    if (sourcesOpen) { closeSources(); return }
    /* MANAGE SOURCES IS A PLACE WITH AN ADDRESS: the browser is an entry of
       the history, so Back closes it and a refresh shows it again. It leaves
       whatever holds the centre, so it asks first where that loses work. */
    guarded(() => centre.go({ sources: 'all' }))
  }
  /** the Sources browser, closed: one step back where the page knows what it
   *  was opened from, and otherwise the conversation in its place -- never a
   *  new entry whose only use is to open it again */
  const closeSources = () => { if (centreAt.current?.sources) centre.back(null); else setSourcesOpen(false) }
  /** into the centre column with a source, or with Add a source */
  const enterSources = (view: SourceMainView) => guarded(() => {
    setBrainReturn(null)
    centre.go({ source: { view, reading: null } })
  })
  /** what the Sources pages ask for: a file read in place and the way back
      from it are steps of the history; a choice inside Add a source is not.
      A MOVE THAT UNMOUNTS THE PAGE ASKS FIRST (moving.ts, review
      ent-d960d458078c): a different source, and Add a source from a source,
      take a changed selection and an unapplied preview with them; reading a
      file in place and returning from it keep the page and lose nothing. */
  const sourceTo = (to: SourceMainState) => {
    const move = () => {
      if (sourceMain?.view.page === 'add' && to.view.page === 'add') centre.replace({ source: to })
      else centre.go({ source: to })
    }
    if (keepsSetup(sourceMain, to)) move(); else guarded(move)
  }
  /** out to the Sources browser, over the conversation where it was */
  const sourcesOut = () => centre.go({ sources: 'all' })
  /** Back: the same way out, asked about first where it would lose work */
  const sourcesBack = () => guarded(sourcesOut)
  /** CLOSING A WORKING COLUMN takes what is in it away, so it asks the same
      question the centre's own ways out ask -- about ITS column only
      (leaving.ts). Switching conversations beside an open record still never
      asks: that record stays exactly where it is. (Review ent-d960d458078c,
      W1: a typed challenge went with the column's close and nothing was
      said.) */
  const closeSurface = (p: 's1' | 's2') =>
    guarded(() => setSurfaces((s) => ({ ...s, [p]: null })), p)
  /** held content beside the conversation: a free working column, or the one already showing a source's content */
  const sourceBeside = (route: SourcesRoute, source: string | null): boolean => {
    const v: SurfaceView = { kind: 'source-content', route, source }
    const showing = surfacePanes.find((s) => surfaces[s]?.kind === 'source-content' && !inColumn(s) && !dockPanels[s])
    if (showing) { setSurfaces((s) => ({ ...s, [showing]: v })); return true }
    const free = surfacePanes.find((s) => !surfaces[s] && !inColumn(s) && !dockPanels[s])
    if (!free) return false
    setSurfaces((s) => ({ ...s, [free]: v }))
    return true
  }
  /* A REFERENCE CHIP'S "Open in Sources", "Compare" and "Go to latest"
     (sources/moving.ts `chipAsk`): the chip announces a Sources address and
     only Fluid's shell was listening. Here it opens the screen Quiet Chat
     already has for it, the way a source's own page opens held content:
     beside the conversation where a working column is free, otherwise in the
     centre over its source's page -- asked about first where that would take
     unfinished work away. */
  const chipAsking = useRef(0)
  const openFromChip = (address: string) => {
    const a = chipAsk(address)
    if (a.to === 'browser') { if (!sourcesOpen) toggleSources(); return }
    /* the source pages read the kinds and names the browser reads */
    setSourcesWanted(true)
    if (a.to === 'add') { enterSources({ page: 'add', connector: a.connector }); return }
    if (a.to === 'source') { enterSources({ page: 'source', col: a.col }); return }
    const ask = ++chipAsking.current
    const known = a.col ? Promise.resolve(a.col) : readJson<{ collection?: string | null }>(`/api/references?ref=${encodeURIComponent(a.ref ?? '')}`).then((p) => p.collection ?? null, () => null)
    void known.then((col) => { if (ask === chipAsking.current) chipRef.current(a.route, col) })
  }
  const showFromChip = (route: SourcesRoute, col: string | null) => {
    if (surfacePanes.length && sourceBeside(route, (col && sourcesRead.data?.collections.find((c) => c.collection === col)?.name) || null)) return
    if (!col) { setNotice('That could not be opened: its source could not be read.'); return }
    const to: SourceMainState = { view: { page: 'source', col }, reading: route }
    if (sourceMain && keepsSetup(sourceMain, to)) centre.go({ source: to })
    else guarded(() => { setBrainReturn(null); centre.go({ source: to }) })
  }
  const chipRef = useRef(showFromChip)
  chipRef.current = showFromChip
  const chipOpenRef = useRef(openFromChip)
  chipOpenRef.current = openFromChip
  useEffect(() => {
    const on = (e: Event) => chipOpenRef.current((e as CustomEvent<string>).detail ?? '')
    window.addEventListener(SOURCES_EVENT, on)
    return () => window.removeEventListener(SOURCES_EVENT, on)
  }, [])
  /** one step back from the post a record pointed to: the record again */
  const backToRecord = () => {
    const to = brainReturn
    if (!to) return
    setBrainReturn(null)
    centre.go({ brain: to })
  }
  const brainBack = () => {
    const cur = brainMain
    if (!cur) return
    if (cur.stack.length > 1) { goCentre({ brain: { ...cur, stack: cur.stack.slice(0, -1) } }); return }
    /* READ FROM THE 3D BRAIN: Back is back to the graph, which is parked and
       comes back exactly as it was -- not out to the conversation. */
    if (cur.origin.from === 'space') { backToSpace(); return }
    goCentre(null, () => {
      if (cur.origin.from === 'browser') setBrainOpen(true)
      else if (cur.origin.from === 'post') { const post = cur.origin.post; requestAnimationFrame(() => requestAnimationFrame(() => flashPost(post))) }
    })
  }
  /** a post's record mark: beside the conversation where a surface is free,
      else in the reading area, with Back to that exact post */
  const openRecordFromPost = (entry: Id, from: { post: Id; conversation: Id | null; recordKind?: string | null }) => {
    const free = surfacePanes.find((s) => !surfaces[s] && !inColumn(s) && !dockPanels[s])
    if (free) { openBeside({ kind: 'brain-record', entry, variant: 'beside', post: from.post, conversation: from.conversation, recordKind: from.recordKind }); return }
    const p = postOf(from.post)
    enterBrain({ page: 'record', entry }, { from: 'post', post: from.post, label: `Back to ${p?.number ? '#' + p.number : 'the post'}` })
  }
  /** the post, marked a moment, where it is drawn */
  const flashPost = (post: Id) => {
    const el = document.querySelector<HTMLElement>(`.q2-conv [data-post="${post}"]`)
    if (!el) return
    el.classList.remove('q2-post-flash'); void el.offsetWidth; el.classList.add('q2-post-flash')
  }
  /* the Brain's reading area is read from its top; leaving it puts the
     conversation back where it was */
  const brainTop = brainMain ? brainMain.stack[brainMain.stack.length - 1] : null
  const brainTopKey = brainTop ? `${brainTop.page}:${'entry' in brainTop ? brainTop.entry : ''}:${brainMain!.stack.length}` : null
  /* a source, or Add a source, in the centre: one key for whichever page it is */
  const centreKey = brainTopKey ?? (sourceMain ? 'source:' + (sourceMain.view.page === 'source' ? sourceMain.view.col : 'add') : null)
  useLayoutEffect(() => {
    const pane = document.querySelector<HTMLElement>('.q2-conv')
    if (!pane) return
    if (centreKey) { pane.scrollTop = 0; return }
    if (brainLeft.current === null) return
    const to = brainLeft.current
    brainLeft.current = null
    /* THE PLACE IS PUT BACK AS THE POSTS ARRIVE. The column was unmounted
       while the centre held it, so on the way back it is short at first and
       the browser clamps the place asked for to whatever is drawn yet -- one
       frame was not always enough, and the reader landed at the top of a
       conversation they were deep inside. It is asked for again each frame
       until the posts are tall enough to hold it, and no longer; the first
       move the READER makes ends it, so nothing ever pulls against them. */
    let frame = 0
    let theirs = false
    const deadline = performance.now() + 1500
    const stop = () => { theirs = true }
    const put = () => {
      if (theirs) return
      pane.scrollTop = to
      if (pane.scrollTop < to && performance.now() < deadline) frame = requestAnimationFrame(put)
    }
    pane.addEventListener('wheel', stop, { passive: true })
    pane.addEventListener('touchstart', stop, { passive: true })
    window.addEventListener('keydown', stop)
    put()
    return () => {
      cancelAnimationFrame(frame)
      pane.removeEventListener('wheel', stop)
      pane.removeEventListener('touchstart', stop)
      window.removeEventListener('keydown', stop)
    }
  }, [centreKey])
  /* A RECORD ASKED FOR BY ADDRESS (`?record=ent-…`, what Copy link copies) is
     what the page opened on (`firstAt`), and its address STAYS: a refresh
     shows the record again and the address in the bar is the record's own
     (owner, 2026-11-20; it used to be taken off, so a refresh lost it).
     WHAT THE ADDRESS NAMES MAY NOT BE THERE. A record or a source this Brain
     does not hold is said, once, over the conversation -- not left as a page
     about nothing -- and the address stops naming it. Only while the reader
     is still where the address put them; a read that merely failed keeps the
     page, which says so itself and offers to try again. */
  const stillFirst = () => !!firstAt && centreAt.current === firstAt
  const notHeld = (words: string) => { if (!stillFirst()) return; centre.replace(null); setUnread(words) }
  useEffect(() => {
    /* what the address could not even name (not an id): said the same way,
       and taken off the address, which would otherwise go on naming it */
    if (opened.asked.what === 'nothing' && !centreAt.current) { const words = opened.asked.words; centre.replace(null); setUnread(words) }
    if (opened.asked.what !== 'record' || !firstAt?.brain) return
    void fetchBrainRecord(opened.asked.entry).then(null, (e: unknown) => {
      if (/no such entry|not found|\b404\b/i.test(e instanceof Error ? e.message : String(e))) notHeld(NO_SUCH_RECORD)
    })
  }, []) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    const v = firstAt?.source?.view
    if (!v || v.page !== 'source' || !sourcesRead.data) return
    if (!sourcesRead.data.collections.some((x) => x.collection === v.col)) notHeld(NO_SUCH_SOURCE)
  }, [sourcesRead.data]) // eslint-disable-line react-hooks/exhaustive-deps
  /* -- VIEWERS: where content opens, and what each viewer may do ---------- */
  /** what column `s` holds now, in words; null when it is empty */
  const holdsWords = (s: 's1' | 's2'): string | null => {
    const v = inColumn(s)
    if (v) return v.title
    if (dockPanels[s]) return DOCK_NAMES[dockPanels[s]!]
    const sv = surfaces[s]
    if (!sv) return null
    const p = postOf(sv.kind === 'thread' ? sv.root : sv.kind === 'post' ? sv.id : '')
    return sv.kind === 'conversation' ? 'a conversation' : `${sv.kind} ${p?.number ? '#' + p.number : ''}`.trim()
  }
  /** put a viewer in column `s`, replacing (by the reader's choice) what was there */
  const placeIn = (id: string, s: 's1' | 's2') => {
    const there = inColumn(s)
    if (there && there.id !== id) closeViewer(there.id)
    setSurfaces((x) => ({ ...x, [s]: null }))
    setDockPanels((x) => ({ ...x, [s]: null }))
    moveViewer(id, s)
  }
  /* CONTENT OPENS where there is room: an empty working column; with none
     free, the reader chooses (replace a column, or maximise); with no
     columns at all, maximised over the conversation */
  const onView = (content: Viewable, source: ViewerSource) => {
    openedBy = document.activeElement as HTMLElement | null
    if (!surfacePanes.length) { openViewer(content, source, 'max'); return }
    const free = surfacePanes.find((s) => !surfaces[s] && !inColumn(s) && !dockPanels[s])
    if (free) { openViewer(content, source, free); return }
    chooseWhere(content, source)
  }
  /** ASK THE READER WHERE A PICTURE GOES, with the placement this page owns.
   *  The launch is where the reader is, so the one chooser can be drawn for
   *  both callers; nothing reads it on this path, which registers no result. */
  const chooseWhere = (content: Viewable, source: ViewerSource) => setChoosing({
    content, source, launch: launchNow({ control: null, fallback: { kind: 'conversation' } }),
    decide: (where) => {
      if (where === 'cancelled' || where === 'none') { setChoosing(null); return }
      placeChosen({ content, source }, where)
    },
  })
  const revealPost = (post: Id) => {
    const el = document.querySelector<HTMLElement>(`.q2-conv [data-post="${post}"]`) ?? document.querySelector<HTMLElement>(`.q2-surface [data-post="${post}"]`)
    if (!el) {
      /* a reply inside a folded thread: read its thread there */
      const p = postOf(post)
      if (p?.replyTo && !receded) { page.onEnter(p.root ?? p.replyTo, post); return }
      setNotice(receded ? 'Restore the conversation to see the post it came from.' : 'That post is not shown in this conversation now.')
      return
    }
    el.scrollIntoView({ block: 'center' })
    el.classList.remove('q2-post-flash'); void el.offsetWidth; el.classList.add('q2-post-flash')
  }
  const actionsFor = (v: OpenViewer): ViewerActions => {
    const post = postSource(v.source)
    const magnetSource = v.source.kind === 'magnet-item' ? v.source : null
    const guardedViewer = (into: 'max' | 's1' | 's2', commit: () => void) => {
      if (!magnetSource) { commit(); return }
      guardedAll(magnetLost(false, undefined, into), commit)
    }
    /* THE GRAPH IS NOT FRAMED LIKE THIS AT ALL any more: it has its own
       full-screen stage (space/SpaceStage.tsx) and never reaches the document
       viewer's frame, so none of these actions is written for it. */
    return {
      columns: surfacePanes.filter((s) => v.place !== s).map((s) => ({ s, label: `Column ${s.slice(1)}`, holds: inColumn(s)?.id === v.id ? null : holdsWords(s), draft: surfaceDraft(s) })),
      /* THE MAGNET'S OWN PLACEMENT GUARD IS KEPT EXACTLY (TEST baseline
         90f5642): a magnet-item viewer is asked about before it moves. A
         result's viewer is never `magnet-item`, so `guardedViewer` commits
         straight through for one. */
      moveTo: (s) => guardedViewer(s, () => placeIn(v.id, s)),
      maximise: v.place === 'max' ? null : () => guardedViewer('max', () => moveViewer(v.id, 'max')),
      restore: v.place === 'max' && v.from && surfacePanes.includes(v.from) ? () => guardedViewer(v.from!, () => placeIn(v.id, v.from!)) : null,
      /* EVERY FRAME CLOSE GOES THROUGH THE RESULT PART (HOST-INTEGRATION.md
         §1.3) -- for a result AND for an ordinary picture: `closeSteps` keeps
         the baseline's reveal for a viewer nothing registered (N3), through
         `ResultPage.reveal`, and a magnet-item viewer (which has no post
         source) simply closes, as it did. Only before the mount exists is
         the baseline's own close used. */
      close: () => {
        if (results.current) { results.current.closeResult(v.id); return }
        closeViewer(v.id); if (v.place === 'max' && post) requestAnimationFrame(() => revealPost(post.post))
      },
      /* the source is shown beside the viewer: a maximised viewer goes back
         to its column if it has one; otherwise it stays open and the post is
         shown in the conversation once the viewer is closed or moved. Going
         to source is not closing (H3), so it has its own operation. */
      toSource: post ? () => {
        /* A MAGNET-SOURCED VIEWER IS THE MAGNET'S (TEST baseline 90f5642),
           and the two arms are exclusive: a result's viewer is never
           `magnet-item`, and a magnet item is never a registered result. */
        if (magnetSource) {
          const r = findMagnet(magnetSource.resourceId)
          if (r) conversationFromMagnet(r, post.conversation!, post.post)
          else setNotice('The Magnet view expired. Open the source conversation from its ordinary navigation.')
          return
        }
        if (results.current) { results.current.goToSource(v.id, { conversation: post.conversation ?? realId!, post: post.post }); return }
        if (v.place === 'max' && v.from && surfacePanes.includes(v.from)) moveViewer(v.id, v.from)
        else if (v.place === 'max') { setNotice('Close the viewer to return to the post it came from; it stays open until then.'); return }
        requestAnimationFrame(() => revealPost(post.post))
      } : null,
      sourceName: post
        ? (post.conversation ? repairText(store.conversations.get(post.conversation)?.name ?? '') || null : 'Sample conversation')
        : `the whole Brain${brain.name ? ` · ${brain.name}` : ''}`,
    }
  }
  const holds = (v: SurfaceView | null, id: Id) => !!v && (v.kind === 'thread' ? v.root === id : v.kind === 'post' ? v.id === id : false)
  const surfaceName = (s: 's1' | 's2') => surfacePanes.length > 1 ? `surface ${s.slice(1)}` : 'the working surface'
  const page: PostPage = {
    me, who, topic,
    onWho: (p) => setWho(who?.id === p.id ? null : p),
    onTopic: (t) => setTopic(topic === t ? null : t),
    onReply: (p) => { setReplyTo(p); dock.current?.querySelector<HTMLTextAreaElement>('textarea')?.focus() },
    onEnter: (root, at) => {
      /* A THREAD ALREADY OPEN IN A COLUMN stays there, with its draft and the
         reply it is writing: the reader is pointed to it rather than it being
         closed and read here */
      const rootConv = postOf(root)?.conversation
      const there = rootConv ? surfacePanes.find((s) => document.querySelector(`[data-surface="${s.slice(1)}"] .fx-composer[data-where="${CSS.escape(`thread:${rootConv}:${root}`)}"]`)) : undefined
      if (there) {
        setNotice(`That thread is open in column ${there.slice(1)}.`)
        const col = document.querySelector<HTMLElement>(`[data-surface="${there.slice(1)}"]`)?.closest<HTMLElement>('.q2-pane')
        const target = col?.querySelector<HTMLElement>(`[data-post="${at ?? root}"]`) ?? col
        target?.scrollIntoView({ block: 'center' })
        target?.classList.remove('q2-post-flash'); void target?.offsetWidth; target?.classList.add('q2-post-flash')
        return
      }
      if (!entered) {
        const pane = document.querySelector<HTMLElement>('.q2-conv')
        const item = pane?.querySelector<HTMLElement>(`.q2-flow-item:has(> [data-post="${root}"])`)
        const el = item?.querySelector<HTMLElement>(':scope > .q2-fold, :scope > .q2-divider-dots') ?? item
        /* where the thread's own post stood in the column: the anchor Back
           returns to, so a change above it cannot shift the reader */
        left.current = { scroll: pane?.scrollTop ?? 0, offset: el && pane ? el.getBoundingClientRect().top - pane.getBoundingClientRect().top : null, replyTo, root }
      }
      setEntered(root); setEnteredAt(at ?? null); setReplyTo(null)
      /* read here, it is no longer also open in a surface */
      setSurfaces((s) => ({ s1: holds(s.s1, root) ? null : s.s1, s2: holds(s.s2, root) ? null : s.s2 }))
    },
    onBeside: surfacePanes.length ? openBeside : null,
    onView,
    openElsewhere: (id) => {
      const s = surfacePanes.find((x) => holds(surfaces[x], id))
      return s ? surfaceName(s) : null
    },
    say: setNotice,
    working,
    brain: isReal ? {
      openFromPost: openRecordFromPost,
      openFull: (entry) => enterBrain({ page: 'record', entry }, { from: 'link' }),
      goToPost: (conversation, turn) => now.current.goToPost(conversation, turn),
      openBrowser: () => setBrainOpen(true),
      newRecord: (kind, basis) => setAuthorNew({ kind, basis, conversation: hereNow }),
      preview: (persona) => setBrainPreview({ persona }),
      canWrite: !READ_ONLY,
    } : undefined,
    sources: isReal ? { open: (col) => enterSources({ page: 'source', col }) } : undefined,
    /* WHAT THE WORK THIS POST BELONGS TO ACTUALLY PRODUCED, before the
       routine activity under it (owner's §3). Only the real conversation
       has a mapping to lend: the sample's posts are not recorded Turns. */
    results: isReal ? { of: resultsOf, host: resultsHost } : undefined,
  }
  /* WHERE A RECORD'S LINKS GO while it is read in the main reading area.
     READ FROM THE GRAPH, every link goes through the SAME dispatcher the
     chosen node went through (§4): the linked id is routed by what it is, it
     inherits the graph origin, and Back visits the detail before it. */
  const fromSpace = brainMain?.origin.from === 'space'
  const brainNav: BrainNav = {
    /* EVERY LINK OFF A RECORD LEAVES THE PAGE IT IS ON, and a record being
       written, revised or challenged lives nowhere else until it is recorded:
       each of these asks first where there is something to lose (`guarded`). */
    openRecord: (entry) => {
      if (fromSpace) { dispatchSpace({ entry }); return }
      if (brainMain) goCentre({ brain: { ...brainMain, stack: [...brainMain.stack, { page: 'record', entry }] } })
    },
    openEntry: fromSpace ? (entry) => dispatchSpace({ entry }) : undefined,
    /* HELD BYTES, IN THE VIEWER THE PAGE ALREADY HAS (addendum §4). It opens
       where content opens: a free working column, else the reader's choice.
       Its source is the Brain itself -- there is no post, and none is
       invented -- so closing it closes only the media: the graph, parked or
       shown, and the way back to it are untouched. */
    openMedia: brain.key ? (_entry, item) => onView({ kind: 'file', item }, { kind: 'brain', brainKey: brain.key! }) : undefined,
    /* a post it points at: the conversation is shown at that post, and one
       step back returns to the record */
    goToPost: (conversation, turn) => guarded(() => { setBrainReturn(brainMain); brainLeft.current = null; centre.go(null, () => now.current.goToPost(conversation, turn)) }),
    openBrowser: () => goCentre(null, () => setBrainOpen(true)),
    newRecord: (kind, basis) => setAuthorNew({ kind, basis, conversation: hereNow }),
    preview: (persona) => setBrainPreview({ persona }),
    canWrite: !READ_ONLY,
  }
  const enteredPost = entered ? postOf(entered) : undefined
  const backToConversation = () => {
    const was = left.current
    setEntered(null); setEnteredAt(null)
    setReplyTo(was?.replyTo ?? null)
    setReturned(was?.root ?? null)
  }
  /* entering: the thread is read from its top, or from the post asked for.
     ENTERING ONCE, HOWEVER OFTEN THE RECORD MOVES. This runs again when the
     conversation is read again, because the thread entered may not be drawn
     yet when it is entered -- and the conversation is now read again on the
     pulse as well (real.ts "the flow follows the record"), so without this
     an arriving post would put a reader deep in a thread back at its top.
     Where the reader was placed is remembered: the same thread, at the same
     post, is placed once and then left alone. */
  const placed = useRef<string | null>(null)
  useLayoutEffect(() => {
    if (!entered) { placed.current = null; return }
    const at = `${entered}|${enteredAt ?? ''}`
    if (placed.current === at) return
    const pane = document.querySelector<HTMLElement>('.q2-conv')
    if (!pane) return
    if (enteredAt) {
      const el = pane.querySelector<HTMLElement>(`[data-post="${enteredAt}"]`)
      /* not drawn yet: from the top until it is, then at it */
      if (el) { placed.current = at; pane.scrollTop += el.getBoundingClientRect().top - pane.getBoundingClientRect().top - 90; return }
      pane.scrollTop = 0
      return
    }
    placed.current = at
    pane.scrollTop = 0
  }, [entered, enteredAt, real.read, postsVersion])
  /* back: the conversation where it was, the thread's post marked a moment */
  useLayoutEffect(() => {
    if (entered || !returned) return
    const pane = document.querySelector<HTMLElement>('.q2-conv')
    const was = left.current
    /* again once what Back restored (the reply's mark) has been drawn */
    const put = () => {
      if (!pane || !was) return
      pane.scrollTop = was.scroll
      const item = pane.querySelector<HTMLElement>(`.q2-flow-item:has(> [data-post="${was.root}"])`)
      const el = item?.querySelector<HTMLElement>(':scope > .q2-fold, :scope > .q2-divider-dots') ?? item
      if (el && was.offset !== null) pane.scrollTop += el.getBoundingClientRect().top - pane.getBoundingClientRect().top - was.offset
    }
    put()
    const again = requestAnimationFrame(() => requestAnimationFrame(put))
    left.current = null
    const t = setTimeout(() => setReturned(null), 1600)
    return () => { clearTimeout(t); cancelAnimationFrame(again) }
  }, [entered, returned])

  /* -- JUMP TO LATEST (usability 5.6, revised) -------------------------------
     The conversation's newest activity (latest.ts says what that is and
     where it is read from) decides whether the round arrow beside the
     composer pulses: while it is out of view -- scrolled past, folded in an
     old thread, in a thread not entered, or not read -- it does. The arrow
     opens JumpToLatest's list of where work last ended; a row goes to its
     post through `goTo`. The rail's arrow goes to another conversation's
     newest post through `latestOf`. */
  const [serverNewest, setServerNewest] = useState<Activity | null>(null)
  useEffect(() => {
    setServerNewest(null)
    if (content !== 'real' || !realId) return
    let live = true
    readNewest(realId).then((a) => { if (live) setServerNewest(a) }, () => {})
    return () => { live = false }
  }, [content, realId, real.read])
  const latest = content === 'real' && realId
    ? newestOf([serverNewest, ...heldIn(realId).map(activityOf)])
    : null
  const [awayFromLatest, setAway] = useState(false)
  /** where the reader was before a jump within the flow (its scroll) */
  const [jumpFrom, setJumpFrom] = useState<number | null>(null)
  useEffect(() => { setJumpFrom(null) }, [realId, entered])
  useEffect(() => {
    const pane = document.querySelector<HTMLElement>('.q2-conv')
    if (!pane || !latest || receded) { setAway(false); return }
    const id = latest.id
    const look = () => {
      const el = pane.querySelector<HTMLElement>(`[data-post="${CSS.escape(id)}"]`)
      if (!el) { setAway(true); return }
      const r = el.getBoundingClientRect(), p = pane.getBoundingClientRect()
      const floor = Math.min(p.bottom, dock.current?.getBoundingClientRect().top ?? p.bottom)
      const seen = r.bottom > p.top + 24 && r.top < floor - 24
      setAway(!seen)
    }
    look()
    const again = requestAnimationFrame(look)
    pane.addEventListener('scroll', look, { passive: true })
    window.addEventListener('resize', look)
    return () => { cancelAnimationFrame(again); pane.removeEventListener('scroll', look); window.removeEventListener('resize', look) }
  }, [latest?.id, postsVersion, entered, receded, real.read]) // eslint-disable-line react-hooks/exhaustive-deps
  /** marks a post once it is drawn: scrolled to, highlighted a moment, and
   *  given focus (without scrolling again) for a keyboard or screen reader */
  const markWhenDrawn = (id: Id, tries = 120) => {
    const el = document.querySelector<HTMLElement>(`.q2-conv [data-post="${CSS.escape(id)}"]`)
    if (!el) { if (tries > 0) requestAnimationFrame(() => markWhenDrawn(id, tries - 1)); return }
    requestAnimationFrame(() => {
      el.scrollIntoView({ block: 'center' })
      /* an attribute, not a class: the post's own class is React's and is
         redrawn as the reader points at it */
      el.removeAttribute('data-latest-mark'); void el.offsetWidth; el.setAttribute('data-latest-mark', '')
      window.setTimeout(() => el.removeAttribute('data-latest-mark'), 2800)
      if (!el.hasAttribute('tabindex')) el.setAttribute('tabindex', '-1')
      el.focus({ preventScroll: true })
    })
  }
  /** GOES TO ONE POST of the conversation shown: scrolled to where it is
   *  drawn in the flow (Back to where you were is then offered), else its
   *  thread read and entered at it, every reply on the way drawn (the
   *  thread's Back to conversation returns); marked either way. */
  const goTo = (t: Activity) => {
    if (!realId) return
    const pane = document.querySelector<HTMLElement>('.q2-conv')
    if (pane?.querySelector(`[data-post="${CSS.escape(t.id)}"]`)) {
      const from = entered ? null : pane.scrollTop
      markWhenDrawn(t.id)
      requestAnimationFrame(() => requestAnimationFrame(() => setJumpFrom(from)))
      return
    }
    const ask = ++asking.current
    const conv = realId
    void (t.root ? Promise.resolve(t.root) : threadRootOf(conv, t.id)).then(async (root) => {
      await readThread(conv, root)
      if (ask !== asking.current || now.current.realId !== conv) return
      now.current.page.onEnter(root, t.id)
      markWhenDrawn(t.id)
    }).catch(() => { if (ask === asking.current) setNotice('That post could not be read.') })
  }
  const goToRef = useRef(goTo)
  goToRef.current = goTo
  /* THE RAIL'S ARROW: another conversation's newest post, straight there --
     its conversation opened, then the post gone to once it is read */
  const pendingLatest = useRef<{ conversation: Id; to: Activity } | null>(null)
  const latestOf = (conv: Id) => {
    readNewest(conv).then((to) => {
      if (!to) { setNotice('Nothing has been posted there yet.'); return }
      if (conv === now.current.realId && content === 'real') { goToRef.current(to); return }
      pendingLatest.current = { conversation: conv, to }
      if (!pickConversation(conv)) pendingLatest.current = null
    }, () => setNotice('Its latest post could not be read.'))
  }
  useEffect(() => {
    const want = pendingLatest.current
    if (!want || !real.read || real.read.conversation !== want.conversation) return
    pendingLatest.current = null
    requestAnimationFrame(() => goToRef.current(want.to))
  }, [real.read])
  const backFromLatest = () => {
    const pane = document.querySelector<HTMLElement>('.q2-conv')
    if (pane && jumpFrom !== null) pane.scrollTop = jumpFrom
    setJumpFrom(null)
  }
  const jump = latest && realId ? (
    <JumpToLatest conversation={realId} away={awayFromLatest} onGo={goTo}
      onBack={jumpFrom !== null && !entered ? backFromLatest : null} />
  ) : null

  const conversation = brainMain ? (
    <div className="q2-col q2-col-brain">
      {saidLine}
      <BrainNavContext.Provider value={brainNav}>
        <BrainMain state={brainMain} canWrite={!READ_ONLY} onBack={brainBack} onLeave={leaveBrain} />
      </BrainNavContext.Provider>
    </div>
  ) : sourceMain ? (
    <div className="q2-col q2-col-brain q2-col-sources">
      {saidLine}
      <SourceMain state={sourceMain} data={sourcesRead.data} me={me} canWrite={!READ_ONLY}
        onState={sourceTo}
        onBack={sourcesBack} onLeave={() => goCentre(null)} onCancel={sourcesBack}
        onBeside={surfacePanes.length ? sourceBeside : null} onChanged={() => sourcesRead.reload()} />
    </div>
  ) : (
    <div className="q2-col">
      {centreAt.current?.magnet && findMagnet(centreAt.current.magnet.resourceId) && <p className="q2-back-bar" role="status">
        <button type="button" className="q2-back-btn" onClick={() => { const r = findMagnet(centreAt.current!.magnet!.resourceId); if (r) expandMagnet(r) }}>‹ Back to Magnet</button>
        <button type="button" className="q2-link-quiet" onClick={() => { const r = findMagnet(centreAt.current!.magnet!.resourceId); if (r) originMagnet(r) }}>Return to origin conversation</button>
      </p>}
      {/* THE 3D BRAIN, PARKED, while what it sent the reader to is read here.
          The graph is still open, with its view: this returns to it. */}
      {graphParked && (
        <p className="q2-back-bar q2-space-return" role="status">
          <button type="button" className="q2-back-btn" onClick={backToSpace}>‹ {BACK_TO_SPACE}</button>
          <span className="q2-back-where">it keeps the view you left it in</span>
        </p>
      )}
      {/* ANOTHER BRAIN ANSWERED since this page was opened (../brainBinding): nothing decided here
          is recorded there, and a reload is the way to it */}
      {brainMoved && (
        <p className="q2-back-bar q2-brain-moved" role="alert" data-brain-moved>
          <span className="q2-back-where">{MOVED_WORDS}</span>
          <button type="button" className="q2-back-btn" onClick={() => location.reload()}>{RELOAD_WORDS}</button>
        </p>
      )}
      {/* WHAT THE ADDRESS NAMED AND THIS BRAIN DOES NOT HOLD, said plainly
          (in the Sources browser itself while that is over the page) */}
      {!sourcesOpen && saidLine}
      {/* THE RECORD THE READER CAME FROM, one step back, while they look at
          the post it pointed to */}
      {brainReturn && !entered && (
        <p className="q2-back-bar q2-brain-return" role="status">
          <button type="button" className="q2-back-btn" onClick={backToRecord}>‹ Back to the record</button>
          <button type="button" className="q2-link-quiet" aria-label="Dismiss" title="Stay here: forget the way back to the record" onClick={() => setBrainReturn(null)}>×</button>
        </p>
      )}
      {/* WHERE THE READER OPENED A RESULT FROM, offered by its own close: the
          conversation, the thread, the position, the reply target and the
          draft place it was pressed from. Dismissing it keeps the reader
          exactly where they are and forgets only the way back. */}
      {resultReturn && (
        <p className="q2-back-bar q2-result-return" role="status">
          <button type="button" className="q2-back-btn" data-control="result-return" onClick={() => backToResult(resultReturn)}>‹ Back to where you opened this</button>
          <button type="button" className="q2-link-quiet" aria-label="Dismiss" title="Stay here: forget the way back" onClick={() => setResultReturn(null)}>×</button>
        </p>
      )}
      {/* THE FILTER IN FORCE, above the conversation it views: a way of
          looking, not part of the conversation */}
      {(who || topic) && (
        <p className="q2-filter" role="status">
          <span className="q2-filter-what">
            <span className="q2-filter-kicker">Filtered</span>{' '}
            {who ? <>posts by or asked by <b>{who.name.replace(/^@/, '')}</b></> : null}{who && topic ? ' under ' : topic ? 'posts under ' : ''}{topic ? <b>#{topic}</b> : null}
            {!who && topicId && real.read?.topic === topicId && real.read.units !== null ? <span className="q2-filter-count"> · {real.read.units} {real.read.units === 1 ? 'post' : 'posts'}</span> : null}
          </span>
          <button className="q2-filter-clear" onClick={() => { setWho(null); setTopic(null) }}>Clear filter</button>
        </p>
      )}
      {/* EVERY TOPIC OF THE CONVERSATION as pills, under the filter and above
          the heading: the one in force marked, any other a click away */}
      {convTopics.length > 0 && !deleted && (
        <div className="q2-topics q2-conv-topics" role="group" aria-label="Topics in this conversation">
          {convTopics.map((t) => (
            <button key={t} className={'q2-pill' + (t === topic ? ' on' : '')} aria-pressed={t === topic}
              onClick={() => setTopic(topic === t ? null : t)}>#{t}</button>
          ))}
        </div>
      )}
      {/* THE END FOCUS ACTUALLY LANDS ON when the control a close came from
          has gone (independent rendered review adm-d4c77f502b8c, F5): the
          conversation's own heading. It was already the last fallback and a
          plain `<header>` cannot take focus, so `.focus()` did nothing and the
          reader was left on the document body with no keyboard place at all.
          `tabIndex={-1}` makes it focusable by script only -- it is not in the
          Tab order and nothing else about it changes. */}
      <header className="q2-conv-head" tabIndex={-1}>
        <h1>{deleted ? 'Deleted conversation' : name}</h1>
        {!deleted && <p className="q2-conv-meta">
          {content === 'long' ? <>{total} real posts from {LONG_REEL.length} dev-Brain conversations, chosen for long Markdown, replies, tables, code, pictures and annotations</>
            : content === 'real' ? <>{total} posts · the latest threads, read from {BRAIN?.brain === 'dev' ? 'the development Brain' : brain.name ?? 'the Brain'}{READ_ONLY ? ' (read-only)' : ''}</> : <>{total} posts · <button className="q2-link" onClick={() => setNotice('Earlier posts: not part of the Round 1 sample.')}>{total - POSTS.length} earlier</button></>}
        </p>}
        {conversationId && <ConversationState row={convRow} say={setNotice} />}
        {!deleted && <ConversationTools people={people} conversation={conversationId} name={name} who={who} setWho={setWho} say={setNotice} trashed={trashed}
          onNewInstruction={() => setAuthorNew({ kind: 'conversation-instruction', conversation: conversationId ? { id: conversationId, name } : null })}
          onOpenRecord={(id) => enterBrain({ page: 'record', entry: id }, { from: 'link' })}
          named={unnamed ? '' : real.read?.name ?? ''} onRenamed={() => setReread((n) => n + 1)} />}
      </header>
      {isReal && real.error && !deleted && <p className="q2-filter" role="alert">Could not read this conversation: {real.error}</p>}
      {deleted && conversationId ? (
        <div className="q2-stream"><TombstoneView id={conversationId} /></div>
      ) : entered ? (
        <div className="q2-stream">
          <div className="q2-back-bar">
            {brainReturn && <button type="button" className="q2-back-btn" onClick={backToRecord}>‹ Back to the record</button>}
            <button className="q2-back-btn" onClick={backToConversation}>← Back to conversation</button>
            <span className="q2-back-where">{name}</span>
            {page.onBeside && <button className="q2-link-quiet" onClick={() => openBeside({ kind: 'thread', root: entered })}>Open beside instead</button>}
          </div>
          <ThreadView root={entered} selected={replyTo?.id ?? null} onSelect={(id) => setReplyTo(postOf(id) ?? null)} />
        </div>
      ) : (
        <div className="q2-stream">
          {isReal && real.earlier && (
            <p className="q2-earlier"><button className="q2-link" onClick={() => { earlierFrom.current = document.querySelector('.q2-conv')?.scrollHeight ?? null; void real.earlier!() }}>
              Read earlier posts</button> <span>{real.read?.older} earlier {real.read?.topic ? (real.read.older === 1 ? 'post' : 'posts') : (real.read?.older === 1 ? 'thread' : 'threads')}</span></p>
          )}
          {rows.map((r) => 'hidden' in r
            ? <p key={r.key} className="q2-folded">{r.hidden} {r.hidden === 1 ? 'post' : 'posts'} folded by the filter</p>
            : <div key={r.post.id} className={'q2-flow-item' + (returned === r.post.id ? ' q2-returned' : '')}><Post post={r.post} threadMarks={<FoldedWork root={r.post.id} />} /><ReplyFold root={r.post.id} /></div>)}
        </div>
      )}
      <Dock dockRef={dock} beside={deleted ? null : jump} closed={trashed && convRow ? <TrashedComposer row={convRow} say={setNotice} /> : deleted ? <DeletedComposer /> : undefined}
        conversation={entered && enteredPost?.real ? enteredPost.conversation ?? null : composerTarget}
        thread={entered && enteredPost?.real ? entered : undefined}
        replyTo={replyTo} onClearReply={() => setReplyTo(null)} onPosted={onPosted}
        working={workingIn(working, content === 'sample' ? 'sample' : (entered && enteredPost?.conversation) || composerTarget)}
        why={why ?? undefined} />
    </div>
  )

  /* Settings, for the global dock's Settings panel */
  const settings = <Settings arr={arr} setArr={setArr} side={side} setSide={setSide} receded={receded} setReceded={setReceded}
    measure={measure} setMeasure={setMeasure} />
  /* THE GLOBAL DOCK opens a panel beside the conversation only in a free
     working column; an occupied one is never replaced behind the reader */
  const dockInColumn = surfacePanes.length ? (panel: DockPanel) => {
    const there = surfacePanes.find((s) => dockPanels[s] === panel)
    if (there) { setNotice(`${DOCK_NAMES[panel]} is already open in column ${there.slice(1)}.`); return }
    const free = surfacePanes.find((s) => !surfaces[s] && !inColumn(s) && !dockPanels[s])
    if (!free) { setNotice('Every working column is in use: close one to keep this beside the conversation.'); return }
    setDockPanels((d) => ({ ...d, [free]: panel }))
  } : null
  /* a conversation (and a post in it) opened from the dock: Mark 2's own navigation */
  /* AN ACTIVITY SOURCE BESIDE THE CONVERSATION: the post's own thread (its
     root as the server names it), or the conversation where there is no post,
     in a free working column through the usual placement -- the conversation
     shown, its reading position, drafts and occupied columns stay as they are */
  const besideFromDock = surfacePanes.length && isReal ? (conversation: string, post?: string) => {
    const ask = ++asking.current
    if (!post) { openBeside({ kind: 'conversation', conversation }); return }
    void threadRootOf(conversation, post).then(async (root) => {
      await readThread(conversation, root)
      if (ask === asking.current) now.current.openBeside({ kind: 'thread', root })
    }).catch(() => { if (ask === asking.current) setNotice('That post could not be read.') })
  } : null
  /* WHAT A NEEDS YOU ITEM NAMES, opened the way this page already opens it
     (needs/NeedsAbout.tsx): a Brain record on its own page, as a record's
     link opens one; a held file in the page's viewer, as a record's does. */
  const recordFromDock = isReal ? (entry: string) => enterBrain({ page: 'record', entry }, { from: 'link' }) : undefined
  /* A FILE PRESSED IN THE DOCK IS A RESULT PRESS LIKE ANY OTHER
     (HOST-INTEGRATION.md §1.3, B4.1): it goes through the one operation, so
     it is described again on the press and fails closed, exactly as a press
     from the chooser is. Before the mount exists it is the baseline's. */
  const fileFromDock = isReal && brain.key ? (entry: string, about: Parameters<typeof heldItem>[1]) => {
    const R = results.current
    if (R) {
      R.openResult(destinationOfRef({
        id: entry, type: 'file', available: !!about && about.state === 'held',
        state: about?.state ?? 'not-held', opens: 'file', file: about ?? null,
      }), launchNow({ control: `needs-ref:${entry}`, fallback: { kind: 'conversation' } }))
      return
    }
    const item = heldItem(entry, about)
    if (item) onView({ kind: 'file', item }, { kind: 'brain', brainKey: brain.key! })
    else setNotice('That file cannot be opened: Mentis does not hold its contents.')
  } : undefined
  /* THE MOUNTED RESULT OPENER, HANDED TO THE DOCK AS ONE OBJECT
     (HOST-INTEGRATION.md §2). The dock was the last documented surface opening
     a reference its own way: it had only {record, file} openers, so a decision's
     evidence was opened through a generic conversation launch with no decision
     identity, and the way back could restore the panel but not the Place.
     Each member reads `results.current` AT CALL TIME -- the mount is made again
     every render -- so this object's identity is stable and the dock's rows are
     not drawn again for nothing. The launch is read the same way, through a
     holder, because it closes over this render's centre, thread and draft. */
  const launchHold = useRef(launchNow)
  launchHold.current = launchNow
  const dockOpener = useRef<DockResultOpener | null>(null)
  dockOpener.current ??= {
    launch: (focus, decision) => launchHold.current(focus, decision),
    open: (d, launch, settled) => results.current?.openResult(d, launch, settled)
      ?? { what: 'unavailable', why: BRAIN_UNCONFIRMED },
    openAsking: (d, ask, launch, settled) => results.current?.openAsking(d, ask, launch, settled)
      ?? { what: 'unavailable', why: BRAIN_UNCONFIRMED },
    has: (d) => !!results.current?.has(d),
    /* A REFUSAL, NOT A SILENT STAY, where there is no mount to ask: the dock
       keeps its way back and the reader is not told they were returned. */
    back: (launch, settled) => { const R = results.current; if (R) R.takeReturn(launch, settled); else settled?.('refused') },
  }
  const resultOpener = isReal ? dockOpener.current : null
  /* THE CONVERSATION ROUTE'S TWO ENDS, EACH ASKED (HOST-INTEGRATION.md §1.2,
     F4/F5): `begin` guards the conversation move and answers with the
     reference to move to and the report to make; `may` is the same identity,
     asked where the asynchronous thread read lands. `done` says which of the
     route's three ends it reached. Every argument is optional, so the page's
     own callers are unchanged. */
  const openFromDock = (conversation: string, post?: string, _number?: number | null, done?: (n: Navigation) => void, begin?: BeginMove, may?: MayMove) => {
    const here = isReal && content === 'real' && conversation === realId
    const pick = (then?: () => void) => begin
      ? pickConversationFor(conversation, () => { const go = begin(); return go && { ref: go.ref, moved: () => then?.() } }, () => done?.({ how: 'cancelled' }))
      : pickConversation(conversation, then, () => done?.({ how: 'cancelled' }))
    /* THE CONVERSATION ALREADY SHOWN, under whatever holds the centre: going
       to it is still going somewhere, so the centre lets go of it first and
       the post is shown once it has. */
    if (here) {
      if (brainMain || sourceMain || brainOpen || sourcesOpen) {
        pick(post ? () => showPost(conversation, post, done, may) : () => done?.('completed'))
        return
      }
      /* already showing it: there is no move to make, so the press's own
         check was the only one -- and the thread read that follows still asks
         `may` before it touches the page */
      if (post) { showPost(conversation, post, done, may); return }
      done?.('completed')
      return
    }
    if (!pick(post ? undefined : () => done?.('completed'))) { done?.('failed'); return }
    if (post) pendingPost.current = { conversation, post, done, may }
  }
  /* WHAT A READ THAT FINISHES LATER ACTS ON: the page as it is then, and only
     for the latest request (an earlier one is dropped) */
  const asking = useRef(0)
  const now = useRef({
    openBeside: (_v: SurfaceView) => {}, page: null as unknown as PostPage, realId: null as string | null,
    goToPost: (_c: string, _p: string) => {},
    showPost: (_c: string, _p: string) => {},
    dispatchSpace: (_f: NodeFacts) => {},
  })
  now.current = { openBeside, page, realId, goToPost: (c, p) => openFromDock(c, p), showPost: (c, p) => showPost(c, p), dispatchSpace }
  /* a post asked for from the dock: shown once ITS conversation has been read */
  const pendingPost = useRef<{ conversation: string; post: string; done?: (n: Navigation) => void; may?: MayMove } | null>(null)
  useEffect(() => {
    const want = pendingPost.current
    if (!want || !real.read || real.read.conversation !== want.conversation) return
    pendingPost.current = null
    requestAnimationFrame(() => showPost(want.conversation, want.post, want.done, want.may))
  }, [real.read]) // eslint-disable-line react-hooks/exhaustive-deps
  /* a post shown where it is drawn; else its thread is read in the reading
     column at that post (Back returns to the conversation) */
  const showPost = (conversation: string, post: string, done?: (n: Navigation) => void, may?: MayMove) => {
    /* THE LAUNCH'S OWN BRAIN, ASKED WHERE THIS TOUCHES THE PAGE (F5). It says
       nothing to the reader itself: the result's own report is where those
       words are said, once, and this route has one. */
    const moved = () => { const why = may?.(); if (why) { done?.({ how: 'refused', why }); return true } return false }
    if (document.querySelector(`.q2-conv [data-post="${post}"]`)) {
      if (moved()) return
      revealPost(post); done?.('completed'); return
    }
    const ask = ++asking.current
    /* the thread is read first: the thread view draws a thread whose post it
       holds; entered only if this is still the conversation shown */
    void threadRootOf(conversation, post).then(async (root) => {
      await readThread(conversation, root)
      if (ask !== asking.current || now.current.realId !== conversation) { done?.({ how: 'cancelled' }); return }
      if (moved()) return                   // the Brain moved while the thread was read
      now.current.page.onEnter(root, post)
      done?.('completed')
      /* SAID ONCE, BY WHOEVER HAS THE WORDS (F6): `done` is a result's report
         and says its own words; where there is no report to carry them -- the
         page's own press -- this is still where they are said. */
    }).catch(() => {
      if (!done && ask === asking.current) setNotice('That post could not be read.')
      done?.({ how: 'failed', why: 'That post could not be read.' })
    })
  }
  /* a conversation opened from inside the page (a deep dive): Mark 2's own
     navigation, without reloading */
  const pickRef = useRef<(k: string) => boolean>(() => false)
  useEffect(() => {
    const on = (e: Event) => { const k = (e as CustomEvent<string>).detail; if (typeof k === 'string') pickRef.current(k) }
    window.addEventListener('q2:open-conversation', on)
    return () => window.removeEventListener('q2:open-conversation', on)
  }, [])
  /** THE CONVERSATION ITSELF, with everything over it let go of: the Brain
   *  and Sources browser cards, and whatever holds the centre reading column
   *  (a source, Add a source, a file read in place, a Brain record). Leaving
   *  the centre goes through `centre`, so this is one step BACK in the
   *  browser's own history where the conversation is behind -- Back and
   *  Forward keep walking the same entries, and the address (and with it the
   *  Mentis server this page is on) is never touched. */
  const arrive = (k: string, then?: () => void) => {
    setBrainOpen(false); setSourcesOpen(false); setBrainReturn(null)
    /* ANOTHER conversation starts in its own place: the place kept for the
       one that was under the centre is not its place (goToPost, below, does
       the same). Returning to the SAME one puts the reader back where they
       were reading. */
    if (k !== realId) brainLeft.current = null
    /* ANOTHER CONVERSATION IS A NEW ENTRY, with its own address (places.ts):
       Back returns to the one this was chosen from. The one already shown
       adds nothing. */
    centre.open(k, then)
    setRealId(k); setContent('real'); saveWorkspace({ conversation: k })
  }
  /* THE BROWSER'S BACK OR FORWARD LANDED ON ANOTHER CONVERSATION'S ENTRY: it
     is shown, exactly as a press on it shows it -- including giving up a
     column that held the same conversation, so no two composers ever write
     to one place. Nothing is asked here: what could be lost was asked about
     before the move was allowed (centreHistory `ask`). */
  showRef.current = (k) => {
    setBrainReturn(null)
    brainLeft.current = null
    const beside = surfacePanes.filter((s) => placeOf(surfaces[s]) === `conversation:${k}`)
    if (beside.length) setSurfaces((x) => ({ ...x, ...Object.fromEntries(beside.map((s) => [s, null])) }))
    setRealId(k); setContent('real'); saveWorkspace({ conversation: k })
  }
  /* THE ADDRESS NAMES THE CONVERSATION SHOWN, also where the page settled on
     it by itself: the most recent one when the address named none, the one a
     remembered conversation gave way to. The entry is corrected in place. */
  useEffect(() => { centre.settle(conversationId) }, [conversationId]) // eslint-disable-line react-hooks/exhaustive-deps
  /** OPENS CONVERSATION `k`, AND ASKS BEFORE IT MOVES (HOST-INTEGRATION.md
   *  §1.2, F4). There is still ONE route: the page's own form below is this
   *  one with a `begin` that always says yes, so every caller runs the same
   *  code and no second path can drift from it. The sample check and the
   *  surface given up beside the centre belong to the press and are unchanged;
   *  `begin()` is asked INSIDE the guard, where `arrive` would run, and the
   *  conversation arrived at is the reference that answer carries. An answer
   *  of null leaves the conversation, the history and the saved workspace
   *  exactly as they are: the reader has already been told which Brain the
   *  server serves now. Says whether there was a route at all. */
  const pickConversationFor = (k: string, begin: BeginMove, stay?: () => void): boolean => {
    if (!isReal) {
      if (k !== 'onboarding') setNotice(`“${CONVERSATIONS.find((c) => c.key === k)?.name}” is not part of the sample. Settings › Content reads real ones.`)
      return false
    }
    /* ALREADY OPEN BESIDE THE CONVERSATION: two composers on one place would
       share and overwrite a draft (`placeOf`), so the surface showing it
       closes as the conversation takes the centre. It is never a refusal:
       the press always goes there. */
    const beside = surfacePanes.filter((s) => placeOf(surfaces[s]) === `conversation:${k}`)
    if (beside.length) {
      setSurfaces((x) => ({ ...x, ...Object.fromEntries(beside.map((s) => [s, null])) }))
      setNotice('That conversation was open beside this one: it is shown here now.')
    }
    /* UNFINISHED WORK ON THE PAGE BEING LEFT (leaving.ts): asked once, with
       Stay and Discard; never a silent refusal, and never a cancelled run. */
    guarded(() => {
      const go = begin()
      if (!go) return                       // refused, and the reader told
      arrive(go.ref, go.moved)
    }, CENTRE, stay)
    return true
  }
  const pickConversation = (k: string, then?: () => void, stay?: () => void): boolean =>
    pickConversationFor(k, () => ({ ref: k, moved: () => then?.() }), stay)
  pickRef.current = pickConversation
  /* ===== THE PAGE, HANDED OVER ONCE (HOST-INTEGRATION.md §1.2) =============
     This is the mount itself. It runs on EVERY render, which is why nothing a
     reader's action is still waiting on lives in it: the viewer registry, the
     recovery flag, the centre generation and a pending close's marker are all
     module state in `mount.ts`, so a landing delivered to the newest mount is
     still the close's own. There is no Brain identity to wire (`serving.ts`
     is read by `mount.ts` itself at every gate) and no fresh read to wire
     (`refRead.ts`/`refNow.ts`, on every explicit press). */
  /** TWO FRAMES ON, so a restore's own render has happened and laid out. */
  const afterDrawn = (fn: () => void) => { requestAnimationFrame(() => requestAnimationFrame(fn)) }
  /** WITHOUT MOVING THE READER (independent mounted re-review adm-31ceb17555cf,
   *  R1). A restore's focus is given to a control so the keyboard has somewhere
   *  to be, not to take the reader somewhere: `focus()` scrolls the nearest
   *  scrollable ancestor to show what it focused, and the conversation header
   *  is at the TOP of the reading pane -- so the place this same restore had
   *  just put back was thrown away by the step after it, in every ordinary
   *  Close and explicit return. `preventScroll` is the one thing that keeps
   *  both: usable focus, and the reader's own place. (`markWhenDrawn` above
   *  already focuses this way, for the same reason.) */
  const take = (el: HTMLElement | null | undefined) => el?.focus({ preventScroll: true })
  /** the four ends a close can focus when the control it came from has gone */
  const focusFallback = (f: LaunchFocus['fallback']) => {
    if (f.kind === 'latest') { take(document.querySelector<HTMLElement>('[data-control="latest"]')); return }
    if (f.kind === 'decision') { take(document.querySelector<HTMLElement>(`[data-control="decision:${CSS.escape(f.item)}"]`)); return }
    if (f.kind === 'item') { take(document.querySelector<HTMLElement>(`[data-control="item:${CSS.escape(f.item)}"]`)); return }
    take(document.querySelector<HTMLElement>('.q2-conv-head'))
  }
  const resultPage: ResultHostPage = {
    /* THE GRAPH KEY, AND ONLY FOR THE VIEWER'S SOURCE (F2). There is no
       `brainKey` member: a render's own closure cannot answer for a page that
       has been rebound since, so the serving identity is read by `mount.ts`
       from the module binding store. */
    spaceKey: () => brain.key ?? null,
    origin: () => location.origin,
    conversation: () => realId,
    centreAt: () => centreAt.current,
    /* THE PAGE'S OWN TRACKER, SET BY WHOEVER APPLIES THE ENTRY (B4.2). */
    enterCentre: (to) => { centreAt.current = to },
    columns: () => surfacePanes as ('s1' | 's2')[],
    freeColumn: () => surfacePanes.find((s) => !surfaces[s] && !inColumn(s) && !dockPanels[s]) ?? null,
    /* the chooser's own state. Whoever asked owns `decide`; the page owns
       taking the veil down, once, whatever the answer was. */
    choose: (ask) => setChoosing({ ...ask, decide: (where) => { setChoosing(null); ask.decide(where) } }),
    invoker: () => document.activeElement as HTMLElement | null,
    hasControl: (control) => !!document.querySelector(`[data-control="${CSS.escape(control)}"]`),
    /* THE CLOSING VIEWER'S OWN INVOKER is handed in (N2): never `openedBy`,
       which the most recent open overwrites. */
    focus: (choice, invoker) => {
      if (choice.how === 'invoker') { take(invoker as HTMLElement | null); return }
      if (choice.how === 'control') { take(document.querySelector<HTMLElement>(`[data-control="${CSS.escape(choice.control)}"]`)); return }
      focusFallback(choice.fallback)
    },
    centreGo: (at) => centre.go(at),
    centreReplace: (at) => centre.replace(at),
    /* THE RETURN IS A CENTRE MOVE, SO IT IS ASKED ABOUT FIRST (B4.3), AND IT
       ASKS BEFORE IT WALKS (F7): `begin()` runs inside the guard, at the
       moment the history would move, and a refusal walks nothing. */
    backTo: (place, then, stay, begin) => guarded(() => {
      if (begin && !begin()) return         // refused, and the reader told
      centre.backTo({ c: place.conversation, at: place.centre }, then)
    }, CENTRE, stay),
    pickConversation: (k, begin, stay) => pickConversationFor(k, begin, stay),
    openPost: (c, p, done, begin, may) => openFromDock(c, p, null, done, begin, may),
    /* GUARDED LIKE EVERY OTHER CENTRE MOVE (F09), AND ASKED BEFORE IT MOVES
       (F4): the record to open and the report to make both come from the
       answer, so this cannot move without asking. */
    record: (begin, stay) => guarded(() => {
      const go = begin()
      if (!go) return                       // refused, and the reader told
      setBrainReturn(null)
      centre.go({ brain: { stack: [{ page: 'record', entry: go.ref }], origin: { from: 'link' } } }, go.moved)
    }, CENTRE, stay),
    goToPost: (c, p) => now.current.goToPost(c, p),
    /* the baseline viewer frame's own close, for the viewers this contract
       never registered (N3): back to the post it was drawn in */
    reveal: (post) => requestAnimationFrame(() => revealPost(post)),
    heldItem: (ref, about) => heldItem(ref, about),
    postOf: (post) => postOf(post) ?? null,
    pictures: (post) => picturesOf(post as Parameters<typeof picturesOf>[0]),
    /* a stored entry's target, back as a destination: what it points at, with
       availability left to the press's own fresh read (§3.2) */
    destinationOfTarget,
    /* WHO IS READING, for the result page P4 re-reads at the press */
    viewer: () => null,
    /* THE ASKING BLOCK'S OWN FRESH READ (independent review adm-10a5f284dde6,
       F2): Needs you's about-read, which is the only reader that resolves an
       input's response set, as the `Read` the opener's gate understands. The
       destination it answers with is built from the FRESHLY read reference, so
       what is opened is what the server said a moment ago -- and `formNow` has
       already refused anything that is not the same set, in the same post,
       part and block, still readable, in this page's own Brain. */
    askingNow: async (ask) => {
      const now = await readFormNow(ask.ask, { ref: ask.ref, conversation: ask.conversation, post: ask.post, part: ask.part, block: ask.block })
      return now.how === 'fresh' ? { how: 'fresh', destination: destinationOfRef(now.ref) } : { how: 'gone', why: now.why }
    },
    putBack: (step) => {
      /* THE THREAD, OR THE FLOW (F3): `root: null` is the conversation flow
         in no thread, and it is put back as deliberately as a thread is --
         which is also what points the composer at the launch's own draft
         place (`mainPlace` follows `entered`). Neither draft is touched: the
         draft store keeps one per place and this chooses between them. */
      if (step.do === 'thread') { setEntered(step.root); setEnteredAt(step.at); return }
      /* AND THE READING POSITION ONCE THE PANE IT BELONGS TO IS DRAWN (F3):
         the thread or flow above is a state change, so the pane this scrolls
         is the one React has not rendered yet -- scrolling the old one put
         the reader back nowhere. */
      /* AND NOTHING ELSE PUTS THE READER SOMEWHERE ELSE AFTERWARDS (R1). Two
         other mechanisms wrote this same pane in the same frames, so the place
         that was actually left was neither module's:

           * the close's own focus step, scheduled after this one -- answered
             by `take` above, which focuses without scrolling;
           * the host's OWN "back to where the thread was" restore (the
             `returned` effect below), which re-places the reader from the
             memory the Back BUTTON keeps, corrected by the anchor's offset,
             once on its commit and again two frames later. That memory is the
             right answer for its own press and the wrong one for this restore,
             which carries the exact place the launch saved. Leaving the thread
             is this restore's step (`thread` above, applied in the same React
             commit), so clearing its trigger here stops the second restore
             before it runs rather than racing it; a later Back press sets it
             again and keeps its own behaviour.

         The place is then checked once more in the frame after the focus step,
         and only put back if something did move it, so the DOM the reader is
         left with is the one this restore asked for. */
      /* AND ONCE THE CONVERSATION IT BELONGS TO HAS ITS POSTS (independent
         review adm-10a5f284dde6, F4).
         THE DEFECT THIS ANSWERS: two frames are enough for a restore inside
         the conversation already shown, and not for one that had to open
         ANOTHER conversation first -- its posts are fetched, and the pane that
         exists two frames after the move is a short one. `scrollTop = 1600`
         against a pane that cannot scroll that far is silently clamped to 0,
         so a reader returning to a decision from evidence read elsewhere came
         back to the right conversation at its top and had to find their place
         again. One frame's re-check could only re-apply the same clamped
         value, which is why it did not catch this.
         Wait for this conversation's posts, then apply its saved scroll once.
         A later centre move, Brain change, restore or reader input cancels it;
         `PLACE_MS` bounds the wait and unmount invalidates it. */
      if (step.do === 'reading') {
        setReturned(null)
        const mine = ++placing.current
        const want = step.scroll
        const conversation = readAddress(location.search).c ?? now.current.realId
        const brain = servingBrainKey()
        const moves = centreGeneration()
        const until = Date.now() + PLACE_MS
        const current = () => mine === placing.current && moves === centreGeneration() && brain === servingBrainKey()
        const theirs = () => { if (mine === placing.current) placing.current++ }
        const gestures = ['wheel', 'touchstart', 'pointerdown', 'keydown'] as const
        gestures.forEach((g) => window.addEventListener(g, theirs, { passive: true }))
        const done = () => gestures.forEach((g) => window.removeEventListener(g, theirs))
        afterDrawn(() => {
          const put = () => {
            if (!current() || Date.now() > until) { done(); return }
            /* A short pane before the read completes is not a shorter
               conversation. Wait for this conversation's actual posts. */
            const drawn = readingNow.current
            const pane = document.querySelector<HTMLElement>('.q2-conv')
            if (!pane || drawn.conversation !== conversation || drawn.read !== conversation) {
              requestAnimationFrame(put)
              return
            }
            pane.scrollTop = want
            const at = pane.scrollTop
            requestAnimationFrame(() => {
              if (current() && Math.abs(pane.scrollTop - at) > 1) pane.scrollTop = at
              done()
            })
          }
          put()
        })
        return
      }
      if (step.do === 'reply') { setReplyTo(step.post ? postOf(step.post) ?? null : null); return }
      /* 'draft': the composer is pointed at this place again; the draft store
         already holds what was typed under it. 'conversation' and 'centre'
         are made by `mount.ts` through the members above. */
    },
    /* WHEN THE PAGE HAS DRAWN WHAT WAS PUT BACK (F3, F5): two frames, as the
       Magnet's own origin restore uses -- the first lets React commit the
       state a restore step wrote, the second lets the pane it produced lay
       out, so focus and the reading position land on what is actually there. */
    after: (fn) => afterDrawn(fn),
    offerReturn: (l) => setResultReturn(l),
    leaveOn: (place) => { if (place.conversation && place.conversation !== realId) pickConversation(place.conversation); else centre.replace(place.centre) },
    external: (href) => !!window.open(href, EXTERNAL_LINK.target, EXTERNAL_LINK.rel),
    say: setNotice,
  }
  results.current = mountResults(resultPage)
  /** THE EXPLICIT WAY BACK out of a result, which its own close offers rather
   *  than taking (H4: browser Back never reopens anything; the pill is the
   *  only way back).
   *
   *  IT IS THE RESULT MODULE'S OPERATION, NOT A SECOND APPLICATION OF THE PLAN
   *  (independent rendered review adm-d4c77f502b8c, F2 and F3). This handler
   *  built `restoreSteps` and applied them itself, which put two things wrong
   *  that the module's own close path had right: nothing checked the launch's
   *  serving identity, so a page the server had moved under still restored the
   *  old Brain's place; and nothing restored the ABSENCE of a thread or
   *  waited for the pane before reading and focus. `takeReturn` is that one
   *  gated operation, and the only thing left here is what the host alone
   *  owns -- taking the bar down when the return was actually taken, and
   *  KEEPING it when it was refused. */
  const backToResult = (l: LaunchContext) => {
    const R = results.current
    if (!R) { setNotice('The way back is applied once this page knows which Brain it is on.'); return }
    R.takeReturn(l, (how) => { if (how === 'returned') setResultReturn(null) })
  }
  /* A NEW CONVERSATION, from discovery: Mentis's own creation, as Fluid's +
     makes it (unnamed until named), by the reader; opened where the rail
     opens one, its composer ready. One operation key per conversation, kept
     across a lost answer so a retry is the same operation; never offered
     where the page may not write. */
  const startOp = useRef<string | null>(null)
  const composeIn = useRef<string | null>(null)
  const newConversation = isReal && !READ_ONLY ? async () => {
    const author = me ?? await store.loadMe()
    const op = startOp.current ??= newOp()
    let made: string
    try {
      made = (await store.createConversation(author, op)).conversation
      startOp.current = null
    } catch (e: unknown) {
      if ((e as { serverAnswer?: boolean })?.serverAnswer) startOp.current = null
      throw e
    }
    setStarted((s) => [...s, made])
    composeIn.current = made
    pickConversation(made)
  } : undefined
  /* THE RAIL'S +: the same creation as the full list's New, one at a time;
     a refusal is said in the page's notice */
  const startingNew = useRef(false)
  const newFromRail = newConversation ? () => {
    if (startingNew.current) return
    startingNew.current = true
    newConversation().catch((e: unknown) => setNotice(`Could not start a conversation: ${e instanceof Error ? e.message : String(e)}`))
      .finally(() => { startingNew.current = false })
  } : undefined
  /* its composer, once the new conversation is read */
  useEffect(() => {
    if (!composeIn.current || real.read?.conversation !== composeIn.current) return
    composeIn.current = null
    requestAnimationFrame(() => dock.current?.querySelector<HTMLTextAreaElement>('textarea')?.focus())
  }, [real.read])
  /* SAVED MAGNETS use the same viewer placement and lifetime owner as the
     graph. The canvas puck covers nothing; details cover mounted readers.
     Reader/history changes below are committed only after every lost place
     has answered the existing leaving question. */
  const magnetKey = brainMoved ? null : brain.key ?? null
  const magnetViewer = (r: QuietMagnetResource) => viewersNow().find((v) => v.content.kind === 'magnet' && v.content.resourceId === r.id)
  const duplicateColumns = (c: string) => surfacePanes.filter((s) => placeOf(surfaces[s]) === `conversation:${c}`)
  const maxReturn = () => {
    const m = maximised(), col = m?.from
    return { maxReturn: col, returnOccupied: !!col && (!!surfaces[col] || !!dockPanels[col] || (!!inColumn(col) && inColumn(col)!.id !== m?.id)) }
  }
  const magnetLost = (centreLost: boolean, c?: string, into?: 's1' | 's2' | 'max' | 'canvas') =>
    magnetAffectedPlaces({ centre: centreLost, into, duplicates: c ? duplicateColumns(c) : [], ...maxReturn() }, room)
  const isLiveMagnet = (r: QuietMagnetResource) => !!magnetKey && r.brainKey === magnetKey && findMagnet(r.id) === r
  const captureMagnetOrigin = (): MagnetOrigin => {
    const pane = document.querySelector<HTMLElement>('.q2-conv')
    const anchor = pane ? [...pane.querySelectorAll<HTMLElement>('[data-post]')].find((el) => el.getBoundingClientRect().bottom >= pane.getBoundingClientRect().top) : null
    return { place: { c: realId, at: centreAt.current }, thread: entered, at: enteredAt,
      scroll: pane?.scrollTop ?? 0, anchor: anchor?.dataset.post ?? null,
      anchorOffset: pane && anchor ? anchor.getBoundingClientRect().top - pane.getBoundingClientRect().top : null,
      draftTarget: mainPlace, focus: document.activeElement as HTMLElement | null, replyId: replyTo?.id }
  }
  const restoreOriginNow = (r: QuietMagnetResource) => {
    if (!isLiveMagnet(r)) return
    setRestoreMagnetOrigin(r.id)
  }
  useEffect(() => {
    if (!restoreMagnetOrigin || !magnetKey) return
    const r = findMagnet(restoreMagnetOrigin)
    if (!r || r.brainKey !== magnetKey) { setRestoreMagnetOrigin(null); return }
    if (realId !== r.origin.place.c || real.read?.conversation !== r.origin.place.c) return
    setEntered(r.origin.thread); setEnteredAt(r.origin.at); setReplyTo(r.origin.replyId ? postOf(r.origin.replyId) ?? null : null)
    const put = () => {
      const pane = document.querySelector<HTMLElement>('.q2-conv')
      if (!isLiveMagnet(r)) return
      if (pane) {
        pane.scrollTop = r.origin.scroll
        const anchor = r.origin.anchor ? pane.querySelector<HTMLElement>(`[data-post="${CSS.escape(r.origin.anchor)}"]`) : null
        if (anchor && r.origin.anchorOffset !== null) pane.scrollTop += anchor.getBoundingClientRect().top - pane.getBoundingClientRect().top - r.origin.anchorOffset
      }
      if (centreAt.current?.magnet?.phase === 'details') { document.querySelector<HTMLElement>(`[data-magnet-resource="${r.id}"] .q2-magnet-card button`)?.focus(); return }
      if (r.origin.focus?.isConnected) r.origin.focus.focus({ preventScroll: true })
      else focusMagnetManagement()
    }
    requestAnimationFrame(() => requestAnimationFrame(put))
    setRestoreMagnetOrigin(null)
  }, [restoreMagnetOrigin, magnetKey, realId, real.read]) // eslint-disable-line react-hooks/exhaustive-deps
  const expandMagnet = (r: QuietMagnetResource) => {
    if (!isLiveMagnet(r)) return
    const v = magnetViewer(r)
    if (v) { if (v.place === 'parked') returnViewer(v.id, 'canvas', null); else moveViewer(v.id, 'canvas') }
    r.update({ expanded: true, pinned: true })
    requestAnimationFrame(() => document.querySelector<HTMLElement>(`[data-magnet-resource="${r.id}"] .q2-magnet-card button`)?.focus())
  }
  const collapseMagnet = (r: QuietMagnetResource) => {
    if (!isLiveMagnet(r)) return
    guardedAll(magnetLost(false), () => {
      const v = magnetViewer(r); if (v) { if (v.place === 'parked') returnViewer(v.id, 'canvas', null); else moveViewer(v.id, 'canvas') }
      r.update({ expanded: false, pinned: true })
      if (centreAt.current?.magnet?.resourceId === r.id && centreAt.current.magnet.phase === 'details') centre.back(r.origin.place.at)
    })
  }
  const originMagnet = (r: QuietMagnetResource) => {
    if (!isLiveMagnet(r)) return
    guardedAll(magnetLost(realId !== r.origin.place.c || centreAt.current !== r.origin.place.at, r.origin.place.c ?? undefined), () => {
      if (!isLiveMagnet(r)) return
      centre.returnTo(r.origin.place, () => restoreOriginNow(r))
    })
  }
  const conversationFromMagnet = (r: QuietMagnetResource, c: string, post?: string) => {
    if (!isLiveMagnet(r) || !/^ent-[a-z0-9]{6,40}$/i.test(c)) { setNotice('That conversation reference is unavailable. Nothing was created.'); return }
    guardedAll(magnetLost(true, c), () => {
      if (!isLiveMagnet(r)) return
      centre.navigate(c, magnetIntent(r, { conversation: c, ...(post ? { post } : {}) }), () => {
        if (post) { if (realId === c) requestAnimationFrame(() => now.current.showPost(c, post)); else pendingPost.current = { conversation: c, post } }
      })
    })
  }
  const closeMagnet = (r: QuietMagnetResource) => {
    if (!isLiveMagnet(r)) return
    if (hasMiniDraft(r) && !window.confirm('This Magnet has an unsent mini Conversation draft. Close it and discard that draft? Any message already sent may still be recorded in its Conversation.')) return
    guardedAll(magnetLost(false), () => {
      discardMiniDraft(r)
      const at = centreAt.current?.magnet
      const v = magnetViewer(r); if (v) closeViewer(v.id)
      releaseResource(r.id)
      if (at?.resourceId === r.id) centre.replace(at.phase === 'details' ? r.origin.place.at : null)
      requestAnimationFrame(focusMagnetManagement)
    })
  }
  magnetRef.current = {
    affected: (held) => {
      const p = held && typeof held === 'object' && 'at' in held ? held as { c?: string; at?: CentreAt } : null
      const intent = p?.at?.magnet
      const r = intent ? findMagnet(intent.resourceId) : null
      const from = centreAt.current?.magnet
      if (!intent && !from) return [CENTRE]
      const prior = from ? findMagnet(from.resourceId) : null
      const coveredOnly = (!!intent && intent.phase === 'details' && !!r && realId === r.origin.place.c && JSON.stringify(centreAt.current) === JSON.stringify(r.origin.place.at)) ||
        (!intent && from?.phase === 'details' && !!prior && p?.c === prior.origin.place.c && JSON.stringify(p?.at ?? null) === JSON.stringify(prior.origin.place.at))
      return magnetLost(!coveredOnly, p?.c, intent?.phase === 'details' ? 'max' : undefined)
    },
    apply: (to) => {
      for (const v of viewersNow()) if (v.content.kind === 'magnet' && v.place === 'max' && v.content.resourceId !== to?.resourceId) {
        moveViewer(v.id, 'canvas'); findMagnet(v.content.resourceId)?.update({ expanded: false, pinned: false })
      }
      if (!to) return null
      const resumed = resumeMagnet(to, magnetKey, findMagnet)
      if (resumed.how === 'other-brain') { setNotice('That Magnet belongs to another or unknown Brain.'); return null }
      if (resumed.how === 'expired') {
        setNotice('This local Magnet view expired. Open existing Magnet to start a new view.')
        requestAnimationFrame(() => centre.replace(null)); return null
      }
      const r = resumed.resource, v = magnetViewer(r)
      if (v) {
        const place = 'canvas'
        if (v.place === 'parked') returnViewer(v.id, place, null); else moveViewer(v.id, place)
      }
      r.update({ expanded: to.phase === 'details', pinned: false })
      if (to.phase === 'details') { restoreOriginNow(r); return r.origin.place.at }
      if (to.target?.post) pendingPost.current = { conversation: to.target.conversation, post: to.target.post }
      return null
    },
  }
  const fileFromMagnet = async (r: QuietMagnetResource, result: RouteResult) => {
    if (!isLiveMagnet(r)) return
    const value = result.value as Record<string, unknown> | null
    const preview = value?.preview as Record<string, unknown> | null
    const artifact = (preview?.artifact ?? value?.artifact ?? preview ?? value) as Record<string, unknown> | null
    const ref = String(artifact?.ref ?? preview?.ref ?? value?.ref ?? '')
    if (!/^adm-[a-z0-9]+$/i.test(ref)) { setNotice('These bytes are unavailable. Open the source post to inspect the item.'); return }
    let item: ReturnType<typeof returnedItemOf>
    try {
      const described = await readJson<Parameters<typeof returnedItemOf>[0]>(`/api/artifacts/${encodeURIComponent(ref)}?describe=1`)
      if (!isLiveMagnet(r)) return
      item = returnedItemOf({ ...described, ref, url: `/api/artifacts/${encodeURIComponent(ref)}` })
    } catch { if (isLiveMagnet(r)) setNotice('The held file could not be read. Open its source post to inspect it.'); return }
    const c = result.conversation, post = result.post
    if (!item || !c || !post) { setNotice('This item has no readable held bytes or source post.'); return }
    const v = magnetViewer(r)
    const source: ViewerSource = { kind: 'magnet-item', resourceId: r.id, brainKey: r.brainKey, conversation: c, post }
    // Collapsing the cover and opening the ordinary viewer is one guarded move.
    const free = surfacePanes.find((s) => room.free(s))
    if (surfacePanes.length && !free) { chooseWhere({ kind: 'file', item }, source); return }
    const into = free ?? 'max'
    guardedAll(magnetLost(false, undefined, into), () => {
      if (v) moveViewer(v.id, 'canvas'); r.update({ expanded: false, pinned: false })
      openViewer({ kind: 'file', item }, source, into)
    })
  }
  const besideConversation = isReal && surfacePanes.length ? (k: string) => openBeside({ kind: 'conversation', conversation: k }) : undefined
  /** THE PAGE'S OWN PICTURE, PLACED WHERE THE READER CHOSE. This is the TEST
   *  baseline's `chooseViewer` body, reached now through the chooser's own
   *  `decide` (HOST-INTEGRATION.md §1.3): the three buttons say only where,
   *  and whoever asked owns the placement -- `results/mount.ts` for a result,
   *  this for a picture. The Magnet's handling is unchanged. */
  const placeChosen = (chosen: { content: Viewable; source: ViewerSource }, into: 'max' | 's1' | 's2') => {
    const commit = () => {
      if (chosen.source.kind === 'magnet-item') {
        const r = findMagnet(chosen.source.resourceId)
        if (!r || !isLiveMagnet(r)) { setChoosing(null); return }
        const v = magnetViewer(r); if (v) moveViewer(v.id, 'canvas')
        r.update({ expanded: false, pinned: false })
      }
      // Open directly into the chosen column; a temporary max would evict
      // an unrelated viewer before the final placement.
      if (into !== 'max') {
        const there = inColumn(into); if (there) closeViewer(there.id)
        setSurfaces((x) => ({ ...x, [into]: null })); setDockPanels((x) => ({ ...x, [into]: null }))
      }
      openViewer(chosen.content, chosen.source, into); setChoosing(null)
    }
    if (chosen.source.kind === 'magnet-item') guardedAll(magnetLost(false, undefined, into), commit)
    else commit()
  }

  return (
    <PageContext.Provider value={page}>
    <SpaceHostContext.Provider value={spaceHost}>
    <div className={`q2 fx q2-arr-${arr} q2-side-${side} q2-measure-${measure} q2-topbar-${topBar}` + (receded ? ' q2-is-receded' : '') + (maxNow || choosing ? ' q2-modal' : '')
      /* A BROWSER CARD IS OPEN OVER THE PAGE: the Conversations rail stays
         above its veil, so a conversation can always be pressed (quiet2.css) */
      + (brainOpen || sourcesOpen ? ' q2-browsing' : '')}
      style={{ ['--q2-measure' as string]: MEASURES[measure].px + 'px', ...surfaceVars }}>
      <header className="q2-top">
        {/* THE LOGO IS THE BRAIN'S MENU (Fluid's own component), opened by
            click. Mark 2 replaces the older interfaces, so it carries no
            destination in them: the Brain-level pages (home, governance,
            sources, 3D) appear here once Mark 2 has its own. */}
        <span className="q2-brand">
          <BrandMenu clickOnly atBrain={graphShown} whyNot={brain.whyNot} path={brain.path}
            /* THE 3D BRAIN IS A BRAIN-LEVEL PLACE, and the logo's menu is
               where Mark 2's Brain-level places live: no new rail, no second
               navigation. Opening it again focuses or brings back the one
               graph (addendum §3). */
            onSpace={isReal ? () => openSpace() : undefined} atSpace={graphShown}
            /* the development Brain is a copy that keeps DAY-TO-DAY's own name:
               on the development server the logo says which one this is */
            name={BRAIN?.brain === 'dev' ? 'development Brain' : brain.name} />
        </span>
        <span className="q2-top-conv">{name}</span>
        {/* ON A PHONE the Brain icon sits in the top line (DESIGN-r2.md §6);
            the rail keeps its own at wider sizes. One or the other is shown. */}
        {isReal && !receded && (
          <button type="button" className={'q2-top-brain' + (brainOpen ? ' on' : '')} aria-label="Brain" title="Brain" onClick={() => setBrainOpen((o) => !o)}>
            <BrainGlyph size={18} />
          </button>
        )}
        {/* and the Sources icon beside it, on a phone only (the rail has it otherwise) */}
        {isReal && !receded && (
          <button type="button" className={'q2-top-brain q2-top-sources' + (sourcesOpen || sourceMain ? ' on' : '')} aria-label="Sources" title="Sources" onClick={toggleSources}>
            <SourcesGlyph size={18} />
          </button>
        )}
        {/* and the 3D Brain with them (owner ent-46aecf919fe8): wherever
            Manage Sources is offered by its icon, the 3D Brain is too */}
        {isReal && !receded && (
          <button type="button" className={'q2-top-brain q2-top-space' + (graphShown ? ' on' : '')} aria-label="3D Brain" title="3D Brain" onClick={() => openSpace()}>
            <SpaceGlyph size={18} />
          </button>
        )}
        <BrainState />
        {isReal && <button type="button" data-open-magnet className="q2-top-magnets q2-link-quiet" onClick={() => setMagnetSignal((n) => n + 1)}>Magnets</button>}
        <span className="q2-top-gap" />
      </header>
      {!receded && (
        <>
          {/* one way to open a conversation, from the rail or from discovery */}
          <Markers label="Conversations" side="left" items={railConversations} current={content === 'real' ? realId : content === 'long' ? null : 'onboarding'}
            card={isReal ? (ctl) => (
              <ConversationList current={content === 'real' ? realId : null} onPick={pickConversation}
                onLatest={latestOf} onClose={ctl.close} onHold={ctl.hold} onSay={setNotice}
                onDanger={setDanger} focusTab={ctl.focusInto} />
            ) : undefined} cardWidth={340} openSignal={listSignal}
            onBeside={besideConversation}
            onLatest={isReal ? latestOf : undefined}
            onBrain={isReal ? () => { setSourcesOpen(false); setBrainOpen((o) => !o) } : undefined} brainLabel="Brain" brainOn={brainOpen || !!brainMain}
            onSources={isReal ? toggleSources : undefined} sourcesOn={sourcesOpen || !!sourceMain}
            /* THE 3D BRAIN BESIDE THEM (owner ent-46aecf919fe8): the same one
               graph the Brain menu opens -- opening it again focuses it. */
            onSpace={isReal ? () => openSpace() : undefined} spaceOn={graphShown}
            onMagnets={isReal ? () => setMagnetSignal((n) => n + 1) : undefined}
            onNew={newFromRail} newLabel="New conversation"
            onPick={pickConversation} />
          <Markers label="Topics in this conversation" side="right" items={railTopics} current={topic} prefix="#"
            onPick={(k) => setTopic(topic === k ? null : k)} />
        </>
      )}
      <div className="q2-work">
        <div className="q2-work-row" inert={!!maxNow || !!choosing || !!danger}>
        <Panes panes={panes} sizes={paneSizes} setSizes={(s) => setSizesAll((all) => ({ ...all, [key]: s }))} onSettled={() => saveWorkspace({ sizes: sizesRef.current })}
          render={(p) => p === 'conv' ? conversation
            : inColumn(p) ? (inColumn(p)!.place === 'max'
                ? <div className="q2-viewer-away"><div><b>{inColumn(p)!.title}</b>is shown maximised.<br />
                    <button className="q2-link-quiet" onClick={() => moveViewer(inColumn(p)!.id, p)}>Restore it here</button></div></div>
                : <Viewer key={inColumn(p)!.id} id={inColumn(p)!.id} placement="column" actions={actionsFor(inColumn(p)!)} />)
            : dockPanels[p] ? (
                <div className="q2-dock-column">
                  <header className="q2-dock-column-head">
                    <span><b>{DOCK_NAMES[dockPanels[p]!]}</b><span className="q2-dock-column-kind">Mentis</span></span>
                    <button className="q2-surface-close" aria-label={`close ${DOCK_NAMES[dockPanels[p]!]}`} onClick={() => setDockPanels((d) => ({ ...d, [p]: null }))}>×</button>
                  </header>
                  <DockPanelBody panel={dockPanels[p]!} inSurface onOpenConversation={openFromDock} onOpenBeside={besideFromDock}
                    onOpenRecord={recordFromDock} onOpenFile={fileFromDock} resultOpener={resultOpener} />
                </div>
              )
            : surfaces[p] ? <SurfacePane key={`${p}:${JSON.stringify(surfaces[p])}`} working={working} place={p}
                n={p === 's1' ? 1 : 2} view={surfaces[p]!} page={page} onPosted={onPosted} onClose={() => closeSurface(p)} />
            : <Surface n={p === 's1' ? 1 : 2} />} />
        </div>
        {/* THE 3D BRAIN HAS ITS OWN FULL-SCREEN STAGE, on the canvas the reader
            is already on (owner ent-46aecf919fe8); every other kind of content
            is a document in the viewer frame, maximised over the page. */}
        {maxNow && (presentationOf(maxNow.content.kind) === 'space-stage'
          ? <SpaceStage key={maxNow.id} sessionId={(maxNow.state as SpaceState).sessionId} onClose={closeSpace} openedBy={openedBy} />
          : presentationOf(maxNow.content.kind) === 'magnet-stage' ? null : <MaxLayer key={maxNow.id} id={maxNow.id} actions={actionsFor(maxNow)} />)}
        <MagnetHost brainKey={magnetKey} conversation={realId} signal={magnetSignal} capture={captureMagnetOrigin} notice={setNotice}
          expand={expandMagnet} collapse={collapseMagnet} close={closeMagnet} origin={originMagnet}
          conversationTo={conversationFromMagnet} file={fileFromMagnet}
          post={(r, result) => { const c = result.conversation; if (c) conversationFromMagnet(r, c, result.kind === 'post' ? result.id : result.post) }} />
        {choosing && (
          <div className="q2-choose-veil" onPointerDown={(e) => { if (e.target === e.currentTarget) choosing.decide('cancelled') }}
            onKeyDown={(e) => { if (e.key === 'Escape') choosing.decide('cancelled') }}>
            <div className="q2-choose" role="dialog" aria-modal="true" aria-label="Where should it open?" ref={(el) => { el?.querySelector<HTMLButtonElement>('button')?.focus() }}>
              <h2>Where should it open?</h2>
              <p>Every working column is in use. Choose one to replace, or view it maximised.</p>
              {/* THE THREE BUTTONS SAY ONLY WHERE (HOST-INTEGRATION.md §1.3):
                  the placement, the registry row and the history entry are
                  made by whoever asked -- `results/mount.ts` for a result,
                  `onView` for the page's own picture. */}
              {surfacePanes.map((s) => (
                <button key={s} className="q2-choose-opt" onClick={() => choosing.decide(s)}>
                  <span>Column {s.slice(1)}</span><span className="q2v-menu-sub">replaces {holdsWords(s)}{surfaceDraft(s) ? ' (its unsent draft stays saved with its place)' : ''}</span>
                </button>
              ))}
              <button className="q2-choose-opt" onClick={() => choosing.decide('max')}>
                <span>Maximised</span><span className="q2v-menu-sub">over the conversation; nothing is replaced</span>
              </button>
              <button className="q2-link-quiet" onClick={() => choosing.decide('cancelled')}>Cancel</button>
            </div>
          </div>
        )}
      </div>
      {/* A RECEDED CONVERSATION waits as a tab at the outer edge of its side,
          holding no column. Restoring it returns the arrangement it left. */}
      {receded && (
        <button className={`q2-edge q2-edge-${side}`} onClick={() => setReceded(false)} title={`Restore ${name}`} aria-label={`Restore the conversation: ${name}`}>
          <span className="q2-edge-name">{name}</span>
          <span className="q2-edge-act">Restore</span>
        </button>
      )}
      {danger && (
        <DangerZone conversation={danger} name={repairText(danger.name) || 'Unnamed conversation'}
          onBack={() => { setDanger(null); setListSignal((n) => n + 1) }}
          /* DONE: back to the list, at the Trash tab it was asked from */
          onDeleted={(done) => { setNotice(deletedWords(repairText(danger.name) || 'Unnamed conversation', cleanupOf(done.physical_cleanup))); setDanger(null); setListSignal((n) => n + 1) }} />
      )}
      {/* UNFINISHED WORK IN THE WAY: the only thing between a conversation
          press and the conversation, and it is a question, not a refusal.
          Esc and Stay keep the reader exactly where they are. */}
      {leave && (
        /* STAY PUTS THE READER BACK EXACTLY WHERE THEY WERE. Where the
           browser's own Back brought the question, that means asking the
           browser to return to the entry they were on (`stay`); where one of
           the page's own controls did, they never moved at all. */
        <div className="q2-leave-veil" onPointerDown={(e) => { if (e.target === e.currentTarget) { leave.stay?.(); setLeave(null) } }}
          onKeyDown={(e) => {
            if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); leave.stay?.(); setLeave(null); return }
            if (e.key !== 'Tab') return
            const all = [...e.currentTarget.querySelectorAll<HTMLElement>('button:not(:disabled)')]
            if (!all.length) return
            const i = all.indexOf(document.activeElement as HTMLElement)
            const n = e.shiftKey ? (i <= 0 ? all.length - 1 : i - 1) : (i === -1 || i === all.length - 1 ? 0 : i + 1)
            e.preventDefault(); all[n].focus()
          }}>
          <div className="q2-leave" role="alertdialog" aria-modal="true" aria-labelledby="q2-leave-title">
            <h2 id="q2-leave-title">{leave.ask.title}</h2>
            {leave.ask.lines.map((l) => <p key={l}>{l}</p>)}
            <div className="q2-leave-acts">
              <button type="button" className="q2-src-btn" autoFocus onClick={() => { leave.stay?.(); setLeave(null) }}>{leave.ask.stay}</button>
              <button type="button" className="q2-src-btn go" data-leave-go onClick={() => { const go = leave.go; setLeave(null); go() }}>{leave.ask.leave}</button>
            </div>
          </div>
        </div>
      )}
      {isReal && authorNew && !READ_ONLY && (
        <AuthorModal key={authorNew.kind + ':' + (authorNew.basis ?? '') + ':' + (authorNew.conversation?.id ?? '')} request={authorNew} me={me}
          onClose={() => setAuthorNew(null)}
          onOpenRecord={(id) => { setBrainOpen(false); enterBrain({ page: 'record', entry: id }, { from: 'browser', label: BRAIN_TABS[brainFilter] }) }} />
      )}
      {isReal && (
        <BrainBrowser open={brainOpen} filter={brainFilter} query={brainQuery}
          onFilterChange={setBrainFilter} onQueryChange={setBrainQuery}
          onClose={() => setBrainOpen(false)} onOpenRecord={openBrainRecord}
          canWrite={!READ_ONLY}
          onNew={(kind) => setAuthorNew({ kind, conversation: hereNow })}
          onImport={() => enterBrain({ page: 'import' }, { from: 'browser', label: BRAIN_TABS[brainFilter] })}
          onPreview={() => { setBrainOpen(false); setBrainPreview({}) }} />
      )}
      {isReal && (
        <SourcesBrowser open={sourcesOpen} data={sourcesRead.data} error={sourcesRead.error} current={sourceLast} canWrite={!READ_ONLY}
          onClose={closeSources} said={sourcesOpen ? saidLine : null}
          onOpenSource={(col) => enterSources({ page: 'source', col })}
          onAdd={() => enterSources({ page: 'add', connector: null })} />
      )}
      {/* WHAT AN AGENT WOULD RECEIVE: Governance's own preview, over the page.
          It writes nothing. */}
      {brainPreview && (
        <ReceivePreview conversation={conversationId} conversationName={conversationId ? name : null} participant={me} persona={brainPreview.persona ?? null}
          onClose={() => setBrainPreview(null)}
          onOpenRecord={(id) => enterBrain({ page: 'record', entry: id }, { from: 'link' })} />
      )}
      {/* a selected passage: react, comment, deep dive, send to an agent */}
      <SelectionToolbar />
      <GlobalDock settings={settings} onOpenInSurface={dockInColumn} onOpenConversation={openFromDock} onOpenBeside={besideFromDock}
        onOpenRecord={recordFromDock} onOpenFile={fileFromDock} resultOpener={resultOpener} />
      {notice && <p className="q2-notice" role="status">{notice}</p>}
      <LookMaker />
      <Toasts />
      {/* where Fluid's sheets, the composer's palettes and Quiet's own
          margin cards are drawn: above every pane, placed against the window */}
      <div id="fx-layer"><Layer /></div>
      {/* THE GRAPH'S READS, for as long as a graph is open: one reader per
          session, in neither a column nor the maximised layer, so moving,
          maximising and parking the canvas never costs a read (addendum §1).
          It draws nothing. */}
      <SpaceReaders />
    </div>
    </SpaceHostContext.Provider>
    </PageContext.Provider>
  )
}
