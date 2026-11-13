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
import ConversationInstructions from '../fluid/conversation/Instructions'
import { Layer } from '../fluid/frame/layer'
import { Avatar } from '../fluid/identity/Who'
import { brainIdentity, newOp, store, type Conversation } from '../fluid/store'
import BrandMenu from '../surfaces/BrandMenu'
import Dock from './Dock'
import Viewer, { type ViewerActions } from './viewer/Viewer'
import { closeViewer, inColumn, maximised, moveViewer, openViewer, settleColumns, useViewerLayout, type OpenViewer } from './viewer/viewers'
import type { Viewable, ViewerSource } from './viewer/types'
import { LookGallery, LookMaker, Toasts, useSurfaceVars, useTopBar } from './Look'
import { useLook } from '../fluid/frame/look'
import ConversationList from './conversations/ConversationList'
import DangerZone from './conversations/DangerZone'
import ConversationState, { TrashedComposer, useConversationRow } from './conversations/ConversationState'
import GlobalDock, { DockPanelBody, type DockPanel } from './GlobalDock'
import SelectionToolbar from './annotate/Selection'
import Markers from './Markers'
import Post, { PageContext, type PostPage, type SurfaceView } from './Post'
import { LONG_REEL, heldIn, postOf, readThread, threadRootOf, usePosts, useRealFlow } from './real'
import { activityOf, newestOf, readNewest, type Activity } from './latest'
import JumpToLatest from './JumpToLatest'
import { CONVERSATION, CONVERSATIONS, PEOPLE, POSTS, TOPICS, type Id, type MarkerItem, type Person, type Post as PostT } from './sample'
import { repairText } from './text'
import { BRAIN, BRAIN_ERROR, READ_ONLY, brainNow, loadBrain, switchBrain } from './live'
import { useWorking, workingIn } from './presence'
import { SurfacePane } from './Surface'
import { FoldedWork, ReplyFold, ThreadView } from './Thread'
import { readPrefs, readWorkspace, savePrefs, saveWorkspace, type Arrangement, type Measure, type Side } from './prefs'

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

/** The Brain's name, for the logo's menu. */
function useBrain() {
  const [b, setB] = useState<{ name: string | null; whyNot?: string | null; path?: string | null }>({ name: null })
  useEffect(() => {
    void brainIdentity().then((x) => { if (x) setB({ name: x.corpus_name ?? null, whyNot: x.corpus_name_why_not ?? null, path: x.corpus_path ?? null }) })
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
function ConversationTools({ people, conversation, name, named, who, setWho, say, onRenamed, trashed }: {
  people: Person[]; conversation: Id | null; name: string
  /** in Trash: no Rename here (restore it first) */
  trashed?: boolean
  /** the name to start a rename from: empty while it is still unnamed */
  named: string
  who: Person | null; setWho: (p: Person | null) => void; say: (w: string) => void
  /** a rename was recorded: whatever shows the name reads it again */
  onRenamed: () => void
}) {
  const [open, setOpen] = useState<null | 'people' | 'instructions' | 'rename'>(null)
  const box = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!open) return
    const away = (e: PointerEvent) => { if (!box.current?.contains(e.target as Node)) setOpen(null) }
    const esc = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpen(null) }
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
          <ConversationInstructions conversation={conversation} name={name} />
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

function MaxLayer({ id, actions }: { id: string; actions: ViewerActions }) {
  const box = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const opener = openedBy
    box.current?.querySelector<HTMLElement>('.q2v-head button')?.focus()
    /* after the row behind is no longer inert: the next frame */
    return () => { requestAnimationFrame(() => { if (opener?.isConnected) opener.focus() }) }
  }, [])
  return (
    <div className="q2-max-layer" ref={box} role="dialog" aria-modal="true" aria-label="Viewer"
      onKeyDown={(e) => { if (e.key === 'Escape' && !e.defaultPrevented) { e.preventDefault(); (actions.restore ?? actions.close)() } }}>
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
  const setArr = (a: Arrangement) => { setArrNow(a); saveWorkspace({ arr: a }) }
  const setSide = (s: Side) => { setSideNow(s); saveWorkspace({ side: s }) }
  const setReceded = (r: boolean) => { setRecededNow(r); saveWorkspace({ receded: r }) }
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
  const brain = useBrain()
  const surfaceVars = useSurfaceVars()
  const topBar = useTopBar()
  useViewerLayout()
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
  const at = params.get('at') && realId === params.get('c') ? Number(params.get('at')) : undefined
  /* A TOPIC IN FORCE is read from the Brain (its posts, not only those of the
     latest threads): its id from the topics this conversation was read with */
  const topicIds = useRef(new Map<string, string>())
  const topicId = content === 'real' && topic ? topicIds.current.get(topic) : undefined
  const real = useRealFlow(isReal ? content : null, realId, reread, at, topicId)
  for (const t of real.read?.topics ?? []) if (t.id) topicIds.current.set(t.name, t.id)
  /* A REMEMBERED CONVERSATION THAT CANNOT BE READ (gone from this Brain, a
     fresh development copy): forgotten, and the Brain's most recent read */
  useEffect(() => {
    if (!restoredC.current || chosen !== restoredC.current) return
    if (real.read) { restoredC.current = null; return }
    if (real.error && /\b404\b|not found|no such|unknown conversation/i.test(real.error)) { restoredC.current = null; saveWorkspace({ conversation: null }); setRealId(null) }
  }, [real.read, real.error, chosen])
  /* PERMANENT DELETION'S CONFIRMATION, over the whole workspace: reachable
     only when the server says deletion is available (it does not) */
  const [danger, setDanger] = useState<Conversation | null>(null)
  /* bumped to open the conversation list again, focus in it (back from it) */
  const [listSignal, setListSignal] = useState(0)
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

  /* what is drawn: the sample, or real posts, all from the one store */
  const top: Id[] = isReal ? real.read?.top ?? [] : POSTS.filter((p) => !p.replyTo).map((p) => p.id)
  /* a conversation still unnamed reads as Fluid shows it ("Unnamed · started …") */
  const unnamed = isReal ? (list ?? []).find((c) => c.provisional && c.id === real.read?.conversation) : undefined
  const name = isReal ? unnamed?.name ?? real.read?.name ?? (why ? 'No Brain' : 'Reading…') : CONVERSATION.name
  const total = isReal ? real.read?.total ?? 0 : CONVERSATION.total
  const conversationId = content === 'real' ? realId : null
  /* WHERE IT IS LISTED: an archived or trashed one says so under its title,
     and in Trash its composer gives way to Restore */
  const convRow = useConversationRow(conversationId)
  const trashed = (convRow?.state ?? 'active') === 'trashed'
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
  /* -- VIEWERS: where content opens, and what each viewer may do ---------- */
  const [choosing, setChoosing] = useState<{ content: Viewable; source: ViewerSource } | null>(null)
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
    setChoosing({ content, source })
  }
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
  const actionsFor = (v: OpenViewer): ViewerActions => ({
    columns: surfacePanes.filter((s) => v.place !== s).map((s) => ({ s, label: `Column ${s.slice(1)}`, holds: inColumn(s)?.id === v.id ? null : holdsWords(s), draft: surfaceDraft(s) })),
    moveTo: (s) => placeIn(v.id, s),
    maximise: v.place === 'max' ? null : () => moveViewer(v.id, 'max'),
    restore: v.place === 'max' && v.from && surfacePanes.includes(v.from) ? () => moveViewer(v.id, v.from!) : null,
    close: () => { closeViewer(v.id); if (v.place === 'max') requestAnimationFrame(() => revealPost(v.source.post)) },
    /* the source is shown beside the viewer: a maximised viewer goes back
       to its column if it has one; otherwise it stays open and the post is
       shown in the conversation once the viewer is closed or moved */
    toSource: () => {
      if (v.place === 'max' && v.from && surfacePanes.includes(v.from)) moveViewer(v.id, v.from)
      else if (v.place === 'max') { setNotice('Close the viewer to return to the post it came from; it stays open until then.'); return }
      requestAnimationFrame(() => revealPost(v.source.post))
    },
    sourceName: v.source.conversation ? repairText(store.conversations.get(v.source.conversation)?.name ?? '') || null : 'Sample conversation',
  })
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
  }
  const enteredPost = entered ? postOf(entered) : undefined
  const backToConversation = () => {
    const was = left.current
    setEntered(null); setEnteredAt(null)
    setReplyTo(was?.replyTo ?? null)
    setReturned(was?.root ?? null)
  }
  /* entering: the thread is read from its top, or from the post asked for */
  useLayoutEffect(() => {
    if (!entered) return
    const pane = document.querySelector<HTMLElement>('.q2-conv')
    if (!pane) return
    if (enteredAt) {
      const el = pane.querySelector<HTMLElement>(`[data-post="${enteredAt}"]`)
      if (el) { pane.scrollTop += el.getBoundingClientRect().top - pane.getBoundingClientRect().top - 90; return }
    }
    pane.scrollTop = 0
  }, [entered, enteredAt, real.read])
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

  const conversation = (
    <div className="q2-col">
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
      {convTopics.length > 0 && (
        <div className="q2-topics q2-conv-topics" role="group" aria-label="Topics in this conversation">
          {convTopics.map((t) => (
            <button key={t} className={'q2-pill' + (t === topic ? ' on' : '')} aria-pressed={t === topic}
              onClick={() => setTopic(topic === t ? null : t)}>#{t}</button>
          ))}
        </div>
      )}
      <header className="q2-conv-head">
        <h1>{name}</h1>
        <p className="q2-conv-meta">
          {content === 'long' ? <>{total} real posts from {LONG_REEL.length} dev-Brain conversations, chosen for long Markdown, replies, tables, code, pictures and annotations</>
            : content === 'real' ? <>{total} posts · the latest threads, read from {BRAIN?.brain === 'dev' ? 'the development Brain' : brain.name ?? 'the Brain'}{READ_ONLY ? ' (read-only)' : ''}</> : <>{total} posts · <button className="q2-link" onClick={() => setNotice('Earlier posts: not part of the Round 1 sample.')}>{total - POSTS.length} earlier</button></>}
        </p>
        {conversationId && <ConversationState row={convRow} say={setNotice} />}
        <ConversationTools people={people} conversation={conversationId} name={name} who={who} setWho={setWho} say={setNotice} trashed={trashed}
          named={unnamed ? '' : real.read?.name ?? ''} onRenamed={() => setReread((n) => n + 1)} />
      </header>
      {isReal && real.error && <p className="q2-filter" role="alert">Could not read this conversation: {real.error}</p>}
      {entered ? (
        <div className="q2-stream">
          <div className="q2-back-bar">
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
      <Dock dockRef={dock} beside={jump} closed={trashed && convRow ? <TrashedComposer row={convRow} say={setNotice} /> : undefined}
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
  const openFromDock = (conversation: string, post?: string) => {
    const here = isReal && content === 'real' && conversation === realId
    if (here) { if (post) showPost(conversation, post); return }
    if (!pickConversation(conversation)) return
    if (post) pendingPost.current = { conversation, post }
  }
  /* WHAT A READ THAT FINISHES LATER ACTS ON: the page as it is then, and only
     for the latest request (an earlier one is dropped) */
  const asking = useRef(0)
  const now = useRef({ openBeside: (_v: SurfaceView) => {}, page: null as unknown as PostPage, realId: null as string | null })
  now.current = { openBeside, page, realId }
  /* a post asked for from the dock: shown once ITS conversation has been read */
  const pendingPost = useRef<{ conversation: string; post: string } | null>(null)
  useEffect(() => {
    const want = pendingPost.current
    if (!want || !real.read || real.read.conversation !== want.conversation) return
    pendingPost.current = null
    requestAnimationFrame(() => showPost(want.conversation, want.post))
  }, [real.read]) // eslint-disable-line react-hooks/exhaustive-deps
  /* a post shown where it is drawn; else its thread is read in the reading
     column at that post (Back returns to the conversation) */
  const showPost = (conversation: string, post: string) => {
    if (document.querySelector(`.q2-conv [data-post="${post}"]`)) { revealPost(post); return }
    const ask = ++asking.current
    /* the thread is read first: the thread view draws a thread whose post it
       holds; entered only if this is still the conversation shown */
    void threadRootOf(conversation, post).then(async (root) => {
      await readThread(conversation, root)
      if (ask === asking.current && now.current.realId === conversation) now.current.page.onEnter(root, post)
    }).catch(() => { if (ask === asking.current) setNotice('That post could not be read.') })
  }
  /* a conversation opened from inside the page (a deep dive): Mark 2's own
     navigation, without reloading */
  const pickRef = useRef<(k: string) => boolean>(() => false)
  useEffect(() => {
    const on = (e: Event) => { const k = (e as CustomEvent<string>).detail; if (typeof k === 'string') pickRef.current(k) }
    window.addEventListener('q2:open-conversation', on)
    return () => window.removeEventListener('q2:open-conversation', on)
  }, [])
  /** opens conversation `k`; says whether it did */
  const pickConversation = (k: string): boolean => {
    if (isReal && surfacePanes.some((s) => placeOf(surfaces[s]) === `conversation:${k}`)) { setNotice('That conversation is open in a working surface.'); return false }
    if (isReal) { setRealId(k); setContent('real'); saveWorkspace({ conversation: k }); return true }
    if (k !== 'onboarding') setNotice(`“${CONVERSATIONS.find((c) => c.key === k)?.name}” is not part of the sample. Settings › Content reads real ones.`)
    return false
  }
  pickRef.current = pickConversation
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
  const besideConversation = isReal && surfacePanes.length ? (k: string) => openBeside({ kind: 'conversation', conversation: k }) : undefined

  return (
    <PageContext.Provider value={page}>
    <div className={`q2 fx q2-arr-${arr} q2-side-${side} q2-measure-${measure} q2-topbar-${topBar}` + (receded ? ' q2-is-receded' : '') + (maxNow || choosing ? ' q2-modal' : '')}
      style={{ ['--q2-measure' as string]: MEASURES[measure].px + 'px', ...surfaceVars }}>
      <header className="q2-top">
        {/* THE LOGO IS THE BRAIN'S MENU (Fluid's own component), opened by
            click. Mark 2 replaces the older interfaces, so it carries no
            destination in them: the Brain-level pages (home, governance,
            sources, 3D) appear here once Mark 2 has its own. */}
        <span className="q2-brand">
          <BrandMenu clickOnly atBrain={false} whyNot={brain.whyNot} path={brain.path}
            /* the development Brain is a copy that keeps DAY-TO-DAY's own name:
               on the development server the logo says which one this is */
            name={BRAIN?.brain === 'dev' ? 'development Brain' : brain.name} />
        </span>
        <span className="q2-top-conv">{name}</span>
        <BrainState />
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
                  <DockPanelBody panel={dockPanels[p]!} inSurface onOpenConversation={openFromDock} onOpenBeside={besideFromDock} />
                </div>
              )
            : surfaces[p] ? <SurfacePane key={`${p}:${JSON.stringify(surfaces[p])}`} working={working}
                n={p === 's1' ? 1 : 2} view={surfaces[p]!} page={page} onPosted={onPosted} onClose={() => setSurfaces((s) => ({ ...s, [p]: null }))} />
            : <Surface n={p === 's1' ? 1 : 2} />} />
        </div>
        {maxNow && <MaxLayer key={maxNow.id} id={maxNow.id} actions={actionsFor(maxNow)} />}
        {choosing && (
          <div className="q2-choose-veil" onPointerDown={(e) => { if (e.target === e.currentTarget) setChoosing(null) }}
            onKeyDown={(e) => { if (e.key === 'Escape') setChoosing(null) }}>
            <div className="q2-choose" role="dialog" aria-modal="true" aria-label="Where should it open?" ref={(el) => { el?.querySelector<HTMLButtonElement>('button')?.focus() }}>
              <h2>Where should it open?</h2>
              <p>Every working column is in use. Choose one to replace, or view it maximised.</p>
              {surfacePanes.map((s) => (
                <button key={s} className="q2-choose-opt" onClick={() => { const id = openViewer(choosing.content, choosing.source, 'max'); placeIn(id, s); setChoosing(null) }}>
                  <span>Column {s.slice(1)}</span><span className="q2v-menu-sub">replaces {holdsWords(s)}{surfaceDraft(s) ? ' (its unsent draft stays saved with its place)' : ''}</span>
                </button>
              ))}
              <button className="q2-choose-opt" onClick={() => { openViewer(choosing.content, choosing.source, 'max'); setChoosing(null) }}>
                <span>Maximised</span><span className="q2v-menu-sub">over the conversation; nothing is replaced</span>
              </button>
              <button className="q2-link-quiet" onClick={() => setChoosing(null)}>Cancel</button>
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
        <DangerZone name={repairText(danger.name) || 'Unnamed conversation'}
          onBack={() => { setDanger(null); setListSignal((n) => n + 1) }}
          onConfirm={() => { setDanger(null); setNotice('Permanent deletion is not available on this server.') }} />
      )}
      {/* a selected passage: react, comment, deep dive, send to an agent */}
      <SelectionToolbar />
      <GlobalDock settings={settings} onOpenInSurface={dockInColumn} onOpenConversation={openFromDock} onOpenBeside={besideFromDock} />
      {notice && <p className="q2-notice" role="status">{notice}</p>}
      <LookMaker />
      <Toasts />
      {/* where Fluid's sheets, the composer's palettes and Quiet's own
          margin cards are drawn: above every pane, placed against the window */}
      <div id="fx-layer"><Layer /></div>
    </div>
    </PageContext.Provider>
  )
}
