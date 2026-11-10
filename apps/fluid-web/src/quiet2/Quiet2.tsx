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
import { brainIdentity, store } from '../fluid/store'
import MediaLayer from '../quiet/media/MediaLayer'
import BrandMenu from '../surfaces/BrandMenu'
import Dock from './Dock'
import Viewer, { type ViewerActions } from './viewer/Viewer'
import { closeViewer, inColumn, maximised, moveViewer, openViewer, settleColumns, useViewerLayout, type OpenViewer } from './viewer/viewers'
import type { Viewable, ViewerSource } from './viewer/types'
import { LookGallery, LookMaker, Toasts, useSurfaceVars } from './Look'
import { useLook } from '../fluid/frame/look'
import Discover from './Discover'
import Markers from './Markers'
import Post, { PageContext, type PostPage, type SurfaceView } from './Post'
import { LONG_REEL, postOf, readThread, usePosts, useRealFlow } from './real'
import { CONVERSATION, CONVERSATIONS, PEOPLE, POSTS, TOPICS, type Id, type MarkerItem, type Person, type Post as PostT } from './sample'
import { repairText } from './text'
import { READ_ONLY } from './live'
import { useWorking, workingIn } from './presence'
import { SurfacePane } from './Surface'
import { FoldedWork, ReplyFold, ThreadView } from './Thread'

type Arrangement = 'one' | 'two' | 'three'
type Pane = 'conv' | 's1' | 's2'
type Side = 'left' | 'right'
type Measure = 'current' | 'wide'
type Content = 'sample' | 'real' | 'long'

/** The two reading measures compared this round. Neither is settled. */
const MEASURES: Record<Measure, { px: number; label: string }> = {
  current: { px: 680, label: 'Current · 680px' },
  wide: { px: 880, label: 'Wider · 880px' },
}

/** The least a pane can be dragged to. */
const MIN: Record<Pane, number> = { conv: 360, s1: 220, s2: 220 }


const params = new URLSearchParams(location.search)
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
    store.loadList().then(() => setList(store.list)).catch((e: unknown) => setWhy(`Could not reach a Mentis server: ${String(e)}`))
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

/* THE SETTINGS TOOLBAR: one control in the top line, opened by click. Its
   Layout section holds every layout control; nothing else in the header
   arranges the page. */
function Settings({ arr, setArr, side, setSide, receded, setReceded, measure, setMeasure }: {
  arr: Arrangement; setArr: (a: Arrangement) => void
  side: Side; setSide: (s: Side) => void
  receded: boolean; setReceded: (r: boolean) => void
  measure: Measure; setMeasure: (m: Measure) => void
}) {
  const [open, setOpen] = useState(false)
  const [tab, setTab] = useState<'layout' | 'look'>('layout')
  const box = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!open) return
    const away = (e: PointerEvent) => {
      /* the picture maker draws in the page's layer: using it is not leaving Settings */
      if (!box.current?.contains(e.target as Node) && !(e.target as Element).closest?.('#fx-layer')) setOpen(false)
    }
    const esc = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpen(false) }
    document.addEventListener('pointerdown', away); document.addEventListener('keydown', esc)
    return () => { document.removeEventListener('pointerdown', away); document.removeEventListener('keydown', esc) }
  }, [open])
  return (
    <div className="q2-settings" ref={box}>
      <button className="q2-settings-open" aria-expanded={open} aria-haspopup="dialog" onClick={() => setOpen(!open)} title="Settings">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true"><path d="M4 7h10M18 7h2M4 17h4M12 17h8" /><circle cx="16" cy="7" r="2" /><circle cx="10" cy="17" r="2" /></svg>
        <span>Settings</span>
      </button>
      {open && (
        <div className="q2-settings-panel" role="dialog" aria-label="Settings">
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
function Panes({ panes, sizes, setSizes, render }: {
  panes: Pane[]; sizes: number[]; setSizes: (s: number[]) => void; render: (p: Pane) => ReactNode
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
    const off = () => { el.removeEventListener('pointermove', on); el.removeEventListener('pointerup', off); el.classList.remove('dragging'); document.body.classList.remove('q2-resizing') }
    el.addEventListener('pointermove', on); el.addEventListener('pointerup', off)
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
              onKeyDown={(e) => { if (e.key === 'ArrowLeft' || e.key === 'ArrowRight') { e.preventDefault(); move(i, (e.key === 'ArrowLeft' ? -1 : 1) * room * 0.02) } }} />
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
function ConversationTools({ people, conversation, name, who, setWho, say }: {
  people: Person[]; conversation: Id | null; name: string; who: Person | null; setWho: (p: Person | null) => void; say: (w: string) => void
}) {
  const [open, setOpen] = useState<null | 'people' | 'instructions'>(null)
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
    </div>
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
  if (harness) return <Suspense fallback={null}><HarnessView kind={harness} /></Suspense>
  return <Quiet2Page />
}

function Quiet2Page() {
  usePosts()
  const [who, setWho] = useState<Person | null>(null)
  const [topic, setTopic] = useState<string | null>(null)
  const [arr, setArr] = useState<Arrangement>(pick('arr', ['one', 'two', 'three'], 'one'))
  const [side, setSide] = useState<Side>(pick('side', ['left', 'right'], 'left'))
  const [receded, setReceded] = useState(params.get('receded') === '1')
  const [measure, setMeasure] = useState<Measure>(pick('measure', ['current', 'wide'], 'current'))
  /* REAL CONTENT by default: the Brain's own conversations. The sample and
     the long-form reel are fixtures for isolated UI checks, asked for by
     address only (content=sample, content=long) */
  const [content, setContent] = useState<Content>(pick('content', ['sample', 'real', 'long'], 'real'))
  const [chosen, setRealId] = useState<string | null>(params.get('c'))
  const [sizes, setSizesAll] = useState<Record<string, number[]>>({})
  const [replyTo, setReplyTo] = useState<PostT | null>(null)
  /* a thread read in the reading column, in place of the flow */
  const [entered, setEntered] = useState<Id | null>(null)
  /* THE CONVERSATION AS IT WAS LEFT for a thread: where it was scrolled,
     what was being answered, which thread; Back puts all three back */
  const left = useRef<{ scroll: number; offset: number | null; replyTo: PostT | null; root: Id } | null>(null)
  const [enteredAt, setEnteredAt] = useState<Id | null>(null)
  const [returned, setReturned] = useState<Id | null>(null)
  const [surfaces, setSurfaces] = useState<Record<'s1' | 's2', SurfaceView | null>>({ s1: null, s2: null })
  const [notice, setNotice] = useState<string | null>(null)
  const brain = useBrain()
  const surfaceVars = useSurfaceVars()
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
  const named = (list ?? []).filter((c) => c.name && !/^unnamed/i.test(c.name))
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
  /* the whole collection of conversations, opened from the rail's chevron */
  const [discover, setDiscover] = useState(false)
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
  const name = isReal ? real.read?.name ?? (why ? 'No Brain' : 'Reading…') : CONVERSATION.name
  const total = isReal ? real.read?.total ?? 0 : CONVERSATION.total
  const conversationId = content === 'real' ? realId : null
  const people: Person[] = isReal
    ? (real.read?.participants ?? []).map((p) => ({ id: p.id, name: p.name, agent: !!top.map(postOf).find((x) => x?.by.id === p.id)?.by.agent }))
    : Object.values(PEOPLE)
  const railConversations: MarkerItem[] = isReal
    ? named.slice(0, 16).map((c) => ({ key: c.id, name: repairText(c.name), count: c.posts, idle: minutesSince(c.last_activity) }))
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
    const free = surfacePanes.find((s) => !surfaces[s] && !inColumn(s))
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
    moveViewer(id, s)
  }
  /* CONTENT OPENS where there is room: an empty working column; with none
     free, the reader chooses (replace a column, or maximise); with no
     columns at all, maximised over the conversation */
  const onView = (content: Viewable, source: ViewerSource) => {
    openedBy = document.activeElement as HTMLElement | null
    if (!surfacePanes.length) { openViewer(content, source, 'max'); return }
    const free = surfacePanes.find((s) => !surfaces[s] && !inColumn(s))
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
            : content === 'real' ? <>{total} posts · the latest threads, read from {brain.name ?? 'the Brain'}{READ_ONLY ? ' (read-only)' : ''}</> : <>{total} posts · <button className="q2-link" onClick={() => setNotice('Earlier posts: not part of the Round 1 sample.')}>{total - POSTS.length} earlier</button></>}
        </p>
        <ConversationTools people={people} conversation={conversationId} name={name} who={who} setWho={setWho} say={setNotice} />
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
      <Dock dockRef={dock}
        conversation={entered && enteredPost?.real ? enteredPost.conversation ?? null : composerTarget}
        thread={entered && enteredPost?.real ? entered : undefined}
        replyTo={replyTo} onClearReply={() => setReplyTo(null)} onPosted={onPosted}
        working={workingIn(working, content === 'sample' ? 'sample' : (entered && enteredPost?.conversation) || composerTarget)}
        why={why ?? undefined} />
    </div>
  )

  const pickConversation = (k: string) => {
    if (isReal && surfacePanes.some((s) => placeOf(surfaces[s]) === `conversation:${k}`)) { setNotice('That conversation is open in a working surface.'); return }
    if (isReal) { setRealId(k); setContent('real') }
    else if (k !== 'onboarding') setNotice(`“${CONVERSATIONS.find((c) => c.key === k)?.name}” is not part of the sample. Settings › Content reads real ones.`)
  }
  const besideConversation = isReal && surfacePanes.length ? (k: string) => openBeside({ kind: 'conversation', conversation: k }) : undefined

  return (
    <PageContext.Provider value={page}>
    <div className={`q2 fx q2-arr-${arr} q2-side-${side} q2-measure-${measure}` + (receded ? ' q2-is-receded' : '')}
      style={{ ['--q2-measure' as string]: MEASURES[measure].px + 'px', ...surfaceVars }}>
      <header className="q2-top">
        {/* THE LOGO IS THE BRAIN'S MENU (Fluid's own component), opened by
            click. Mark 2 replaces the older interfaces, so it carries no
            destination in them: the Brain-level pages (home, governance,
            sources, 3D) appear here once Mark 2 has its own. */}
        <span className="q2-brand">
          <BrandMenu clickOnly name={brain.name} whyNot={brain.whyNot} path={brain.path} atBrain={false} />
        </span>
        <span className="q2-top-conv">{name}</span>
        {READ_ONLY && <span className="q2-readonly-badge" title="This preview reads the Brain only: it cannot post, reply, edit or change looks">Read-only</span>}
        <span className="q2-top-gap" />
        <Settings arr={arr} setArr={setArr} side={side} setSide={setSide} receded={receded} setReceded={setReceded}
          measure={measure} setMeasure={setMeasure} />
      </header>
      {!receded && (
        <>
          {/* one way to open a conversation, from the rail or from discovery */}
          <Markers label="Conversations" side="left" items={railConversations} current={content === 'real' ? realId : content === 'long' ? null : 'onboarding'}
            onMore={isReal ? () => setDiscover((d) => !d) : undefined} moreOpen={discover}
            onBeside={besideConversation}
            onPick={pickConversation} />
          <Markers label="Topics in this conversation" side="right" items={railTopics} current={topic} prefix="#"
            onPick={(k) => setTopic(topic === k ? null : k)} />
        </>
      )}
      <div className="q2-work">
        <div className="q2-work-row" inert={!!maxNow || !!choosing}>
        <Panes panes={panes} sizes={paneSizes} setSizes={(s) => setSizesAll((all) => ({ ...all, [key]: s }))}
          render={(p) => p === 'conv' ? conversation
            : inColumn(p) ? (inColumn(p)!.place === 'max'
                ? <div className="q2-viewer-away"><div><b>{inColumn(p)!.title}</b>is shown maximised.<br />
                    <button className="q2-link-quiet" onClick={() => moveViewer(inColumn(p)!.id, p)}>Restore it here</button></div></div>
                : <Viewer key={inColumn(p)!.id} id={inColumn(p)!.id} placement="column" actions={actionsFor(inColumn(p)!)} />)
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
      {discover && !receded && <Discover current={content === 'real' ? realId : null} onPick={pickConversation} onBeside={besideConversation} onClose={() => setDiscover(false)} />}
      {notice && <p className="q2-notice" role="status">{notice}</p>}
      <MediaLayer />
      <LookMaker />
      <Toasts />
      {/* where Fluid's sheets, the composer's palettes and Quiet's own
          margin cards are drawn: above every pane, placed against the window */}
      <div id="fx-layer"><Layer /></div>
    </div>
    </PageContext.Provider>
  )
}
