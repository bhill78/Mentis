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
import { useEffect, useLayoutEffect, useRef, useState, type ReactNode } from 'react'
import { readAddress, writeAddress } from '../address'
import Composer from '../fluid/Composer'
import ConversationInstructions from '../fluid/conversation/Instructions'
import { Layer } from '../fluid/frame/layer'
import { Avatar } from '../fluid/identity/Who'
import { brainIdentity, store } from '../fluid/store'
import MediaLayer from '../quiet/media/MediaLayer'
import BrandMenu from '../surfaces/BrandMenu'
import { sourcesHash } from '../surfaces/sources/navigation'
import { SPACE_HASH } from '../surfaces/space/navigation'
import Markers from './Markers'
import Post, { PageContext, type PostPage, type SurfaceView } from './Post'
import { LONG_REEL, postOf, readThread, usePosts, useRealFlow } from './real'
import { CONVERSATION, CONVERSATIONS, PEOPLE, POSTS, TOPICS, type Id, type MarkerItem, type Person, type Post as PostT } from './sample'
import { repairText } from './text'
import { ReplyFold, ThreadView } from './Thread'

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

/** The real conversation drawn by default when real content is asked for:
 *  the dev Brain's Markdown renderer conversation (long reports, code,
 *  pictures, files). Any other is chosen from the rail. */
const DEFAULT_REAL = 'ent-128690b59552'

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
function Settings({ arr, setArr, side, setSide, receded, setReceded, measure, setMeasure, content, setContent }: {
  arr: Arrangement; setArr: (a: Arrangement) => void
  side: Side; setSide: (s: Side) => void
  receded: boolean; setReceded: (r: boolean) => void
  measure: Measure; setMeasure: (m: Measure) => void
  content: Content; setContent: (c: Content) => void
}) {
  const [open, setOpen] = useState(false)
  const box = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!open) return
    const away = (e: PointerEvent) => { if (!box.current?.contains(e.target as Node)) setOpen(false) }
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
            <Choice label="Content" value={content} onChange={setContent} options={[
              { v: 'sample', label: 'Sample' }, { v: 'long', label: 'Long posts', title: 'Real long posts from the dev Brain' }, { v: 'real', label: 'Latest', title: 'The latest posts of a real conversation; pick another on the rail' },
            ]} />
          </section>
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

/* THE COMPOSER, FLUID'S OWN, where a conversation or a thread is shown. A
   reply chosen with a post's Reply is Fluid's `replyTo`, read into Fluid's
   store first so the composer can say what it answers; inside a thread it is
   the thread's composer (`thread`), so what is posted lands under its root. */
function Dock({ conversation, thread, replyTo, onClearReply, onPosted, note, dockRef }: {
  conversation: Id | null; thread?: Id; replyTo: PostT | null; onClearReply: () => void
  /** after a post is made here: read again whatever shows it */
  onPosted: (root: Id | null) => void
  note: ReactNode; dockRef?: React.Ref<HTMLDivElement>
}) {
  const [, setLoaded] = useState(0)
  const want = replyTo?.real ? replyTo.id : null
  /* the target is given at once (a quick send is still a reply); Fluid's
     store is read so the composer can name what it answers */
  useEffect(() => {
    const ids = [want, thread].filter((x): x is Id => !!x)
    if (!ids.length) return
    let live = true
    void store.loadPosts(ids).then(() => { if (live) setLoaded((n) => n + 1) }, () => {})
    return () => { live = false }
  }, [want, thread])
  /* Fluid's composer clears its reply after every post it makes */
  const cleared = () => {
    onClearReply()
    const root = thread ?? (replyTo?.real ? replyTo.root ?? replyTo.id : null)
    onPosted(root)
  }
  return (
    <div className="q2-dock" ref={dockRef}>
      {replyTo && !replyTo.real && (
        <p className="q2-dock-reply">“{replyTo.by.name.replace(/^@/, '')}” is a sample post: a reply can only be posted to a real one.
          <button className="q2-link" onClick={onClearReply}>Dismiss</button></p>
      )}
      {conversation ? (
        <>
          <Composer key={`${conversation}:${thread ?? ''}`} conversation={conversation} thread={thread}
            replyTo={want ?? thread ?? null} onClearReply={cleared} />
          <p className="q2-dock-note">{note}</p>
        </>
      ) : <p className="q2-dock-note">{note}</p>}
    </div>
  )
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
  const link = conversation ? `${location.origin}/fluid${writeAddress({ ...readAddress(''), conversation, topic: null, turn: null })}` : location.href
  return (
    <div className="q2-conv-tools" role="toolbar" aria-label="conversation tools" ref={box}>
      <button aria-expanded={open === 'people'} aria-haspopup="menu" onClick={() => setOpen(open === 'people' ? null : 'people')}
        className={who ? 'on' : undefined}>
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true"><circle cx="9" cy="8" r="3.5" /><path d="M2.5 20a6.5 6.5 0 0 1 13 0M16 4.5a3.5 3.5 0 0 1 0 7M18 14a6 6 0 0 1 3.5 6" /></svg>
        <span>{who ? who.name.replace(/^@/, '') : `${people.length} participants`}</span>
      </button>
      {conversation && <button aria-expanded={open === 'instructions'} aria-haspopup="dialog" onClick={() => setOpen(open === 'instructions' ? null : 'instructions')}>
        <span aria-hidden="true">≡</span><span>Instructions</span>
      </button>}
      <button onClick={() => { void navigator.clipboard?.writeText(link).then(() => say('Link to the conversation copied.'), () => say('Could not reach the clipboard.')) }}>
        <span>Copy link</span>
      </button>
      {conversation && <a href={link} target="_blank" rel="noreferrer">Open in Fluid</a>}
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

/** A working surface holding a thread or one post: the same posts the
 *  conversation holds, read from the same store, with its own scroll and,
 *  for a real thread, the thread's own composer. */
function SurfacePane({ n, view, onClose, page, onPosted }: { n: number; view: SurfaceView; onClose: () => void; page: PostPage; onPosted: (root: Id | null) => void }) {
  usePosts()
  const [selected, setSelected] = useState<Id | null>(null)
  const [replyTo, setReplyTo] = useState<PostT | null>(null)
  const root = view.kind === 'thread' ? view.root : null
  const p = postOf(view.kind === 'thread' ? view.root : view.id)
  /* a surface's own composer answers what the surface shows: the thread's
     root, or the one post, unless a reply in it is chosen */
  const shownId = view.kind === 'thread' ? view.root : view.id
  const here: PostPage = {
    ...page,
    onReply: (post) => { setReplyTo(post); setSelected(post.id) },
    openElsewhere: () => null,
  }
  const title = p ? (p.title ?? `${p.by.name.replace(/^@/, '')}${p.number ? ` · #${p.number}` : ''}`) : 'Reading…'
  return (
    <PageContext.Provider value={here}>
      <div className="q2-surface-view">
        <header className="q2-surface-head">
          <span className="q2-surface-kicker">Surface {n} · {view.kind === 'thread' ? 'thread' : 'post'}</span>
          <span className="q2-surface-title">{title}</span>
          {selected && selected !== root && view.kind === 'thread' && page.onBeside && (
            <button className="q2-link-quiet" onClick={() => page.onBeside!({ kind: 'post', id: selected })}>Open the chosen reply alone</button>
          )}
          <button className="q2-surface-close" onClick={onClose} aria-label={`close surface ${n}`} title="Close this surface (nothing in the conversation changes)">×</button>
        </header>
        <div className="q2-col q2-surface-col">
          {view.kind === 'thread'
            ? <ThreadView root={view.root} selected={selected} onSelect={setSelected} />
            : p ? <><Post post={p} /><ReplyFold root={p.id} /></> : <p className="q2-folded">Reading…</p>}
          {p?.real && p.conversation && (
            <Dock conversation={p.conversation} thread={shownId} replyTo={replyTo ?? (selected ? postOf(selected) ?? null : null)}
              onClearReply={() => { setReplyTo(null); setSelected(null) }} onPosted={onPosted}
              note={<>Posts into this thread{replyTo || selected ? ', as a reply to the chosen post' : ''}.</>} />
          )}
        </div>
      </div>
    </PageContext.Provider>
  )
}

export default function Quiet2() {
  usePosts()
  const [who, setWho] = useState<Person | null>(null)
  const [topic, setTopic] = useState<string | null>(null)
  const [arr, setArr] = useState<Arrangement>(pick('arr', ['one', 'two', 'three'], 'one'))
  const [side, setSide] = useState<Side>(pick('side', ['left', 'right'], 'left'))
  const [receded, setReceded] = useState(params.get('receded') === '1')
  const [measure, setMeasure] = useState<Measure>(pick('measure', ['current', 'wide'], 'current'))
  const [content, setContent] = useState<Content>(pick('content', ['sample', 'real', 'long'], 'sample'))
  const [realId, setRealId] = useState<string>(params.get('c') ?? DEFAULT_REAL)
  const [sizes, setSizesAll] = useState<Record<string, number[]>>({})
  const [replyTo, setReplyTo] = useState<PostT | null>(null)
  /* a thread read in the reading column, in place of the flow */
  const [entered, setEntered] = useState<Id | null>(null)
  const [surfaces, setSurfaces] = useState<Record<'s1' | 's2', SurfaceView | null>>({ s1: null, s2: null })
  const [notice, setNotice] = useState<string | null>(null)
  const brain = useBrain()
  const me = useMe()
  const { list, why } = useConversationList()
  const isReal = content !== 'sample'
  const [reread, setReread] = useState(0)
  const real = useRealFlow(isReal ? content : null, realId, reread)
  /* after a post: its thread is read again, or the flow for a new post */
  const onPosted = (root: Id | null) => {
    const r = root ? postOf(root) : undefined
    if (r?.real && r.conversation) void readThread(r.conversation, r.root ?? r.id).catch(() => {})
    else if (isReal) setReread((n) => n + 1)
  }
  const dock = useRef<HTMLDivElement>(null)

  const panes = panesOf(arr, side, receded)
  const key = panes.join(',')
  const paneSizes = sizes[key] ?? defaultSizes(panes)
  const surfacePanes = panes.filter((p): p is 's1' | 's2' => p !== 'conv')

  /* what is drawn: the sample, or real posts, all from the one store */
  const top: Id[] = isReal ? real.read?.top ?? [] : POSTS.filter((p) => !p.replyTo).map((p) => p.id)
  const name = isReal ? real.read?.name ?? 'Reading…' : CONVERSATION.name
  const total = isReal ? real.read?.total ?? 0 : CONVERSATION.total
  const conversationId = content === 'real' ? realId : null
  const people: Person[] = isReal
    ? (real.read?.participants ?? []).map((p) => ({ id: p.id, name: p.name, agent: !!top.map(postOf).find((x) => x?.by.id === p.id)?.by.agent }))
    : Object.values(PEOPLE)
  const named = (list ?? []).filter((c) => c.name && !/^unnamed/i.test(c.name))
  const railConversations: MarkerItem[] = isReal
    ? named.slice(0, 9).map((c) => ({ key: c.id, name: repairText(c.name), count: c.posts, idle: minutesSince(c.last_activity) }))
    : CONVERSATIONS
  const railTopics: MarkerItem[] = isReal
    ? (real.read?.topics ?? []).slice().sort((a, b) => b.count - a.count).slice(0, 8).map((t) => ({ ...t, idle: 60 * 24 * 3 }))
    : TOPICS
  /* where the conversation's composer writes: the conversation shown, or for
     the sample and the reel, the post being answered's own conversation, or
     else the dev Brain's first named one */
  const composerTarget = replyTo?.real && replyTo.conversation ? replyTo.conversation
    : conversationId ?? (named[0]?.id ?? list?.[0]?.id ?? null)
  const composerName = composerTarget ? repairText(store.conversations.get(composerTarget)?.name ?? (composerTarget === conversationId ? name : 'a conversation')) : null

  useEffect(() => { document.title = `${name} · Quiet` }, [name])
  useEffect(() => { setWho(null); setTopic(null); setEntered(null); setReplyTo(null) }, [content, realId])
  /* a surface that is no longer shown lets go of what it held */
  useEffect(() => {
    setSurfaces((s) => ({ s1: surfacePanes.includes('s1') ? s.s1 : null, s2: surfacePanes.includes('s2') ? s.s2 : null }))
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

  const openBeside = (v: SurfaceView) => {
    const free = surfacePanes.find((s) => !surfaces[s]) ?? surfacePanes[0]
    if (!free) return
    setSurfaces((s) => ({ ...s, [free]: v }))
    if (v.kind === 'thread' && entered === v.root) setEntered(null)
  }
  const holds = (v: SurfaceView | null, id: Id) => !!v && (v.kind === 'thread' ? v.root === id : v.id === id)
  const surfaceName = (s: 's1' | 's2') => surfacePanes.length > 1 ? `surface ${s.slice(1)}` : 'the working surface'
  const page: PostPage = {
    me, who, topic,
    onWho: (p) => setWho(who?.id === p.id ? null : p),
    onTopic: (t) => setTopic(topic === t ? null : t),
    onReply: (p) => { setReplyTo(p); dock.current?.querySelector<HTMLTextAreaElement>('textarea')?.focus() },
    onEnter: (root) => {
      setEntered(root); setReplyTo(null)
      /* read here, it is no longer also open in a surface */
      setSurfaces((s) => ({ s1: holds(s.s1, root) ? null : s.s1, s2: holds(s.s2, root) ? null : s.s2 }))
    },
    onBeside: surfacePanes.length ? openBeside : null,
    openElsewhere: (id) => {
      const s = surfacePanes.find((x) => holds(surfaces[x], id))
      return s ? surfaceName(s) : null
    },
    say: setNotice,
  }
  const enteredPost = entered ? postOf(entered) : undefined

  const conversation = (
    <div className="q2-col">
      <header className="q2-conv-head">
        <h1>{name}</h1>
        <p className="q2-conv-meta">
          {content === 'long' ? <>{total} real posts from {LONG_REEL.length} dev-Brain conversations, chosen for long Markdown, replies, tables, code, pictures and annotations</>
            : content === 'real' ? <>{total} posts · the latest threads, read from the dev Brain</> : <>{total} posts · <button className="q2-link" onClick={() => setNotice('Earlier posts: not part of the Round 1 sample.')}>{total - POSTS.length} earlier</button></>}
        </p>
        <ConversationTools people={people} conversation={conversationId} name={name} who={who} setWho={setWho} say={setNotice} />
      </header>
      {isReal && real.error && <p className="q2-filter" role="alert">Could not read this conversation: {real.error}</p>}
      {(who || topic) && (
        <p className="q2-filter" role="status">
          Showing {who ? <>posts by or asked by <b>{who.name.replace(/^@/, '')}</b></> : null}{who && topic ? ' under ' : topic ? 'posts under ' : ''}{topic ? <b>#{topic}</b> : null}
          {' '}<button className="q2-link" onClick={() => { setWho(null); setTopic(null) }}>Show everything</button>
        </p>
      )}
      {entered ? (
        <div className="q2-stream">
          <p className="q2-back"><button className="q2-link-quiet" onClick={() => { setEntered(null); setReplyTo(null) }}>← Back to the conversation</button>
            {page.onBeside && <> · <button className="q2-link-quiet" onClick={() => openBeside({ kind: 'thread', root: entered })}>Open beside instead</button></>}</p>
          <ThreadView root={entered} selected={replyTo?.id ?? null} onSelect={(id) => setReplyTo(postOf(id) ?? null)} />
        </div>
      ) : (
        <div className="q2-stream">
          {rows.map((r) => 'hidden' in r
            ? <p key={r.key} className="q2-folded">{r.hidden} {r.hidden === 1 ? 'post' : 'posts'} folded by the filter</p>
            : <div key={r.post.id} className="q2-flow-item"><Post post={r.post} /><ReplyFold root={r.post.id} /></div>)}
        </div>
      )}
      <Dock dockRef={dock}
        conversation={entered && enteredPost?.real ? enteredPost.conversation ?? null : composerTarget}
        thread={entered && enteredPost?.real ? entered : undefined}
        replyTo={replyTo} onClearReply={() => setReplyTo(null)} onPosted={onPosted}
        note={entered && enteredPost?.real ? <>Posts into this thread{replyTo && replyTo.id !== entered ? ', as a reply to the chosen post' : ''}.</>
          : replyTo?.real ? <>Replies to {replyTo.by.name.replace(/^@/, '')}{replyTo.number ? ` #${replyTo.number}` : ''} in “{composerName}”.</>
          : composerTarget ? (content === 'real' ? <>Fluid's composer, live: it posts to “{composerName}”.</> : <>Fluid's composer, live. It posts to “{composerName}” in the dev Brain, not to this {content === 'long' ? 'reel' : 'sample'}.</>)
          : (why ?? 'Reading the Brain…')} />
    </div>
  )

  const fluid = (hash: string) => () => location.assign('/fluid' + hash)

  return (
    <PageContext.Provider value={page}>
    <div className={`q2 fx q2-arr-${arr} q2-side-${side} q2-measure-${measure}` + (receded ? ' q2-is-receded' : '')}
      style={{ ['--q2-measure' as string]: MEASURES[measure].px + 'px' }}>
      <header className="q2-top">
        {/* THE LOGO IS THE BRAIN'S MENU (Fluid's own: Brain home, Manage
            Brain, Manage Sources, 3D Brain, Change brain), opened by click.
            Its destinations are Fluid's pages, which it opens. */}
        <span className="q2-brand">
          <BrandMenu clickOnly name={brain.name} whyNot={brain.whyNot} path={brain.path} atBrain={false}
            onBrainHome={() => location.assign('/fluid?home=1')} onManage={() => location.assign('/fluid?gov=1')}
            onSources={fluid(sourcesHash(''))} onSpace={fluid(SPACE_HASH)} />
        </span>
        <span className="q2-top-conv">{name}</span>
        <span className="q2-top-gap" />
        <Settings arr={arr} setArr={setArr} side={side} setSide={setSide} receded={receded} setReceded={setReceded}
          measure={measure} setMeasure={setMeasure} content={content} setContent={setContent} />
      </header>
      {!receded && (
        <>
          <Markers label="Conversations" side="left" items={railConversations} current={content === 'real' ? realId : content === 'long' ? null : 'onboarding'}
            onPick={(k) => {
              if (isReal) { setRealId(k); setContent('real') }
              else if (k !== 'onboarding') setNotice(`“${CONVERSATIONS.find((c) => c.key === k)?.name}” is not part of the sample. Settings › Content reads real ones.`)
            }} />
          <Markers label="Topics in this conversation" side="right" items={railTopics} current={topic} prefix="#"
            onPick={(k) => setTopic(topic === k ? null : k)} />
        </>
      )}
      <div className="q2-work">
        <Panes panes={panes} sizes={paneSizes} setSizes={(s) => setSizesAll((all) => ({ ...all, [key]: s }))}
          render={(p) => p === 'conv' ? conversation
            : surfaces[p] ? <SurfacePane key={`${p}:${surfaces[p]!.kind}:${surfaces[p]!.kind === 'thread' ? (surfaces[p] as { root: Id }).root : (surfaces[p] as { id: Id }).id}`}
                n={p === 's1' ? 1 : 2} view={surfaces[p]!} page={page} onPosted={onPosted} onClose={() => setSurfaces((s) => ({ ...s, [p]: null }))} />
            : <Surface n={p === 's1' ? 1 : 2} />} />
      </div>
      {/* A RECEDED CONVERSATION waits as a tab at the outer edge of its side,
          holding no column. Restoring it returns the arrangement it left. */}
      {receded && (
        <button className={`q2-edge q2-edge-${side}`} onClick={() => setReceded(false)} title={`Restore ${name}`} aria-label={`Restore the conversation: ${name}`}>
          <span className="q2-edge-name">{name}</span>
          <span className="q2-edge-act">Restore</span>
        </button>
      )}
      {notice && <p className="q2-notice" role="status">{notice}</p>}
      <MediaLayer />
      {/* where Fluid's sheets, the composer's palettes and Quiet's own
          margin cards are drawn: above every pane, placed against the window */}
      <div id="fx-layer"><Layer /></div>
    </div>
    </PageContext.Provider>
  )
}
