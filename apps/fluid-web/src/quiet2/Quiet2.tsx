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
import { useEffect, useLayoutEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import Composer from '../fluid/Composer'
import { Layer } from '../fluid/frame/layer'
import { brainIdentity, store } from '../fluid/store'
import MediaLayer from '../quiet/media/MediaLayer'
import BrandMenu from '../surfaces/BrandMenu'
import { sourcesHash } from '../surfaces/sources/navigation'
import { SPACE_HASH } from '../surfaces/space/navigation'
import Markers from './Markers'
import Post from './Post'
import { LONG_REEL, useLongReel, useRealConversation } from './real'
import { CONVERSATION, CONVERSATIONS, POSTS, TOPICS, type MarkerItem, type Person, type Post as PostT } from './sample'

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

export default function Quiet2() {
  const [who, setWho] = useState<Person | null>(null)
  const [topic, setTopic] = useState<string | null>(null)
  const [arr, setArr] = useState<Arrangement>(pick('arr', ['one', 'two', 'three'], 'one'))
  const [side, setSide] = useState<Side>(pick('side', ['left', 'right'], 'left'))
  const [receded, setReceded] = useState(params.get('receded') === '1')
  const [measure, setMeasure] = useState<Measure>(pick('measure', ['current', 'wide'], 'current'))
  const [content, setContent] = useState<Content>(pick('content', ['sample', 'real', 'long'], 'sample'))
  const [realId, setRealId] = useState<string>(params.get('c') ?? DEFAULT_REAL)
  const [sizes, setSizesAll] = useState<Record<string, number[]>>({})
  const [replying, setReplying] = useState<PostT | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const brain = useBrain()
  const { list, why } = useConversationList()
  const latest = useRealConversation(content === 'real' ? realId : null)
  const reel = useLongReel(content === 'long')
  const real = content === 'long' ? reel : latest
  const isReal = content !== 'sample'
  const dock = useRef<HTMLDivElement>(null)

  const panes = panesOf(arr, side, receded)
  const key = panes.join(',')
  const paneSizes = sizes[key] ?? defaultSizes(panes)

  /* what is drawn: the sample, or the real conversation's latest posts */
  const shownPosts = isReal ? real.read?.posts ?? [] : POSTS
  const name = isReal ? real.read?.name ?? 'Reading…' : CONVERSATION.name
  const total = isReal ? real.read?.total ?? 0 : CONVERSATION.total
  const byId = useMemo(() => new Map(shownPosts.map((p) => [p.id, p])), [shownPosts])
  const named = (list ?? []).filter((c) => c.name && !/^unnamed/i.test(c.name))
  const railConversations: MarkerItem[] = isReal
    ? named.slice(0, 9).map((c) => ({ key: c.id, name: c.name, count: c.posts, idle: minutesSince(c.last_activity) }))
    : CONVERSATIONS
  const railTopics: MarkerItem[] = isReal
    ? (real.read?.topics ?? []).slice().sort((a, b) => b.count - a.count).slice(0, 8).map((t) => ({ ...t, idle: 60 * 24 * 3 }))
    : TOPICS
  const composerTarget = content === 'real' ? realId : (named[0]?.id ?? list?.[0]?.id ?? null)
  const composerName = composerTarget ? store.conversations.get(composerTarget)?.name ?? name : null

  useEffect(() => { document.title = `${name} · Quiet` }, [name])
  useEffect(() => { setWho(null); setTopic(null) }, [content, realId])
  useEffect(() => {
    if (!notice) return
    const t = setTimeout(() => setNotice(null), 3200)
    return () => clearTimeout(t)
  }, [notice])

  const shown = (p: PostT) => (!who || p.by.id === who.id || p.requestedBy?.id === who.id) && (!topic || p.topics?.includes(topic))
  /* posts that do not match the filter fold into one quiet line per run */
  const rows: ({ post: PostT } | { hidden: number; key: string })[] = []
  for (const p of shownPosts) {
    if (shown(p)) rows.push({ post: p })
    else {
      const last = rows[rows.length - 1]
      if (last && 'hidden' in last) last.hidden++; else rows.push({ hidden: 1, key: 'h-' + p.id })
    }
  }

  const reply = (p: PostT) => {
    setReplying(p)
    dock.current?.querySelector<HTMLTextAreaElement>('textarea')?.focus()
  }
  const replyingTo = (p: PostT) => {
    if (!p.replyTo) return undefined
    const to = byId.get(p.replyTo)
    if (to) return { name: to.by.name, title: to.title }
    return p.replyNumber ? { name: `#${p.replyNumber}` } : undefined
  }

  const conversation = (
    <div className="q2-col">
      <header className="q2-conv-head">
        <h1>{name}</h1>
        <p className="q2-conv-meta">
          {content === 'long' ? <>{total} real posts from {LONG_REEL.length} dev-Brain conversations, chosen for long Markdown: headings, code, tables, pictures</>
            : content === 'real' ? <>{total} posts · the latest {shownPosts.length}, read from the dev Brain</> : <>{total} posts · 6 participants · <button className="q2-link" onClick={() => setNotice('Earlier posts: not part of the Round 1 sample.')}>{total - shownPosts.length} earlier</button></>}
        </p>
      </header>
      {isReal && real.error && <p className="q2-filter" role="alert">Could not read this conversation: {real.error}</p>}
      {(who || topic) && (
        <p className="q2-filter" role="status">
          Showing {who ? <>posts by or asked by <b>{who.name.replace(/^@/, '')}</b></> : null}{who && topic ? ' under ' : topic ? 'posts under ' : ''}{topic ? <b>#{topic}</b> : null}
          {' '}<button className="q2-link" onClick={() => { setWho(null); setTopic(null) }}>Show everything</button>
        </p>
      )}
      <div className="q2-stream">
        {rows.map((r) => 'hidden' in r
          ? <p key={r.key} className="q2-folded">{r.hidden} {r.hidden === 1 ? 'post' : 'posts'} folded by the filter</p>
          : <Post key={r.post.id} post={r.post} who={who} topic={topic}
              replyingTo={replyingTo(r.post)}
              onWho={(p) => setWho(who?.id === p.id ? null : p)}
              onTopic={(t) => setTopic(topic === t ? null : t)}
              onReply={reply} />)}
      </div>
      <div className="q2-dock" ref={dock}>
        {replying && (
          <p className="q2-dock-reply">Replying to {replying.by.name.replace(/^@/, '')}{replying.title ? `: ${replying.title}` : ''} <span>(the composer below does not yet reply to a chosen post)</span>
            <button className="q2-link" onClick={() => setReplying(null)}>Cancel</button></p>
        )}
        {composerTarget ? (
          <>
            <Composer key={composerTarget} conversation={composerTarget} replyTo={null} onClearReply={() => setReplying(null)} />
            <p className="q2-dock-note">{content === 'real'
              ? <>Fluid's composer, live: it posts to “{composerName}” in the dev Brain.</>
              : <>Round 1: Fluid's composer, live. It posts to “{composerName}” in the dev Brain, not to this sample.</>}</p>
          </>
        ) : <p className="q2-dock-note">{why ?? 'Reading the Brain…'}</p>}
      </div>
    </div>
  )

  const fluid = (hash: string) => () => location.assign('/fluid' + hash)

  return (
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
              else if (k !== 'onboarding') setNotice(`“${CONVERSATIONS.find((c) => c.key === k)?.name}” is not part of the Round 1 sample. Settings › Content › Dev Brain reads real ones.`)
            }} />
          <Markers label="Topics in this conversation" side="right" items={railTopics} current={topic} prefix="#"
            onPick={(k) => setTopic(topic === k ? null : k)} />
        </>
      )}
      <div className="q2-work">
        <Panes panes={panes} sizes={paneSizes} setSizes={(s) => setSizesAll((all) => ({ ...all, [key]: s }))}
          render={(p) => p === 'conv' ? conversation : <Surface n={p === 's1' ? 1 : 2} />} />
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
  )
}
