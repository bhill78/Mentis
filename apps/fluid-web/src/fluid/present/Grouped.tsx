/* THE STAGE GROUPED BY POST (owner-approved: adm-f3a36808b64f, adm-b859a0e5a423).
 *
 * What a following zone shows of a thread -- its objects, and its words where
 * the zone shows the words as objects -- laid out as one ROW PER POST, in
 * thread order: the opening post first, then its replies. Each row has the
 * post's words on the left and the objects it carries on the right, a thin
 * numbered line down the left edge, and says which post it is. Many objects
 * are one stack, stepped through in their own order (1 / 10, Previous, Next,
 * Show all). Only the layout changes: the same items, each drawn by the same
 * card (Present.tsx), with its own Keep…, Focus, drag and caption.
 *
 * FOCUS AND OPEN IN PLACE. A click in a row focuses it (its cards still open
 * as they always did); the row's own ⤢ opens it in place: it takes the room
 * and the others fold to a line each, ↑ ↓ step from post to post, ✕ (or Esc) returns to
 * every row. A focused or opened row says where it is from ("Showing #855 ·
 * replying to #842", "Answering #842 · View parent's objects"), and the post
 * it came from is marked where it is drawn (workspace/origin.tsx). The Stage
 * follows only what is picked: scrolling the thread changes nothing here.
 *
 * THE ZONE'S LAYOUT STILL HOLDS. Each row draws its objects the way the zone
 * is set to (adm-9dc9dfbd89a5): Cards as a stack, Gallery as plates, Previews
 * as previews, Side by side as a row scrolled sideways, beside the words; List
 * is a line each, the words' lines first. Slides and Focused item fill the
 * whole zone with one object, which a row cannot: there "by reply" does not
 * apply, the Stage is drawn as now, and the switch says so (`drawnGrouping`).
 *
 * Kept items are not grouped (Zones.tsx draws them as before, under "Kept"):
 * no origin line and no mark for them. "as now" is the layout before this;
 * "by kind" is that layout with the words first, then the objects. */

import './grouped.css'
import { useEffect, useLayoutEffect, useMemo, useRef, useState, useSyncExternalStore, type FocusEvent as ReactFocus, type KeyboardEvent as ReactKey, type RefObject } from 'react'
import { liveRoot, store, type Id, type Post } from '../store'
import { usePost } from '../workspace/hooks'
import { said } from '../conversation/text'
import { trace } from '../workspace/from'
import { clearOnStage, markOnStage } from '../workspace/origin'
import { useArr } from '../workspace/place'
import type { Node, Show, Zone } from '../workspace/tree'
import Present, { Card } from './Present'
import type { ObjectRef, PresentMode, PresentProps } from './types'
import { useViewState } from '../surface/viewState'

const GAP = 12
/** what a card opens from the Stage: focus there has not left the Stage */
const OPENED_FROM = '.wk-overlay, .pz-viewer, .wk-focusbox, .wk-pop'
/** the row's left gutter (the numbered line) and its own padding, both sides */
const GUTTER = 30
const PADS = 26

/* -- how the Stage lays out what it follows: the header switch ------------- */

export type Grouping = 'reply' | 'kind' | 'now'
export const GROUPINGS: { g: Grouping; label: string; says: string }[] = [
  { g: 'reply', label: 'by reply', says: 'One row per post, in thread order: its words on the left, its objects on the right' },
  { g: 'kind', label: 'by kind', says: 'The words first, then the objects, each saying which post it is from' },
  { g: 'now', label: 'as now', says: 'Every item in one layout, as the Stage drew it before' },
]
const isGrouping = (v: unknown): v is Grouping => GROUPINGS.some((x) => x.g === v)

/* Each zone's choice, kept in this browser (by zone): the saved arrangement
   is not touched. By reply unless chosen otherwise. */
const KEY = 'fluid.stage.grouping:'
const chosen = new Map<string, Grouping>()
const told = new Set<() => void>()
function groupingOf(zone: string): Grouping {
  if (!chosen.has(zone)) {
    let v: unknown = null
    try { v = localStorage.getItem(KEY + zone) } catch { /* no storage: the default */ }
    chosen.set(zone, isGrouping(v) ? v : 'reply')
  }
  return chosen.get(zone)!
}
export function setGrouping(zone: string, g: Grouping) {
  chosen.set(zone, g)
  try { localStorage.setItem(KEY + zone, g) } catch { /* kept for this page only */ }
  told.forEach((fn) => fn())
}
export function useGrouping(zone: string): Grouping {
  return useSyncExternalStore((fn) => { told.add(fn); return () => { told.delete(fn) } }, () => groupingOf(zone))
}

/* -- where "by reply" applies ------------------------------------------------ */

/** The layouts that show one object filling the zone: a row per post cannot. */
const WHOLE_ZONE: Partial<Record<PresentMode, string>> = {
  slides: 'Slides shows one object at a time, filling the zone',
  focus: 'Focused item shows one object large, filling the zone',
}
/** Why "by reply" does not apply to this layout, or null where it does. */
export function replyNot(mode: PresentMode): string | null {
  const why = WHOLE_ZONE[mode]
  return why ? `By reply does not apply here: ${why}, so the Stage is drawn as now. Choose another layout in the zone's menu to group by reply.` : null
}
/** What the Stage draws: the choice, except "by reply" where it does not apply. */
export function drawnGrouping(g: Grouping, mode: PresentMode): Grouping {
  return g === 'reply' && replyNot(mode) ? 'now' : g
}

/** The switch, small, among the zone's own controls; `compact`, one choice
 *  that says which, where the three would take the caption's room. It shows
 *  what is drawn, never a choice the layout does not apply. */
export function GroupSwitch({ zone, name, mode, compact }: { zone: string; name: string; mode: PresentMode; compact?: boolean }) {
  const g = drawnGrouping(useGrouping(zone), mode)
  const not = replyNot(mode)
  const says = (x: (typeof GROUPINGS)[number]) => x.g !== 'reply' ? x.says
    : not ?? (mode === 'list' ? 'One row per post, in thread order: a line each for its words, then its objects' : x.says)
  if (compact) {
    return (
      <select className="pz-gswitch pz-gselect" value={g} aria-label={`How ${name} lays out what it follows`}
        title={says(GROUPINGS.find((x) => x.g === g)!) + (not ? `\n${not}` : '')}
        onChange={(e) => { if (isGrouping(e.target.value)) setGrouping(zone, e.target.value) }}>
        {GROUPINGS.map((x) => <option key={x.g} value={x.g} disabled={x.g === 'reply' && !!not}>{x.label}</option>)}
      </select>
    )
  }
  return (
    <span className="pz-gswitch" role="group" aria-label={`How ${name} lays out what it follows`}>
      {GROUPINGS.map((x) => (
        <button key={x.g} className={g === x.g ? 'on' : ''} aria-pressed={g === x.g} data-grouping={x.g} title={says(x)}
          disabled={x.g === 'reply' && !!not} onClick={() => setGrouping(zone, x.g)}>{x.label}</button>
      ))}
    </span>
  )
}

/** WHERE THE SWITCH GOES, so the caption keeps the room it had before the
 *  switch (adm-27f8c3a442df): the three choices in the caption row where they
 *  fit without cutting the caption or reaching the zone tools (which cover
 *  the caption row's end on hover); else one choice there; else the three in
 *  the zone's ⋯ sheet, and the caption row and the body are as they were. A
 *  line of its own would push the body down. Tried largest first, before
 *  paint, whenever the row's width or words change. */
export type SwitchRoom = 'full' | 'compact' | 'menu'
export function useSwitchRoom(cap: RefObject<HTMLElement | null>, words: string, on: boolean): SwitchRoom {
  const [w, setW] = useState(0)
  useLayoutEffect(() => {
    const el = cap.current
    if (!el || !on) return
    const ro = new ResizeObserver(() => setW(Math.round(el.clientWidth)))
    ro.observe(el)
    return () => ro.disconnect()
  }, [cap, on])
  const key = `${w}|${words}`
  const [fit, setFit] = useState<{ key: string; room: SwitchRoom }>({ key: '', room: 'full' })
  const room = fit.key === key ? fit.room : 'full'
  useLayoutEffect(() => {
    const el = cap.current
    if (!el || !on || room === 'menu') { if (fit.key !== key) setFit({ key, room }); return }
    const what = el.querySelector<HTMLElement>('.wk-what')
    const sw = el.querySelector<HTMLElement>('.pz-gswitch')?.getBoundingClientRect()
    const tools = el.querySelector<HTMLElement>('.sc-t1, .sc-t2')?.getBoundingClientRect()
    const cut = !!what && what.scrollWidth > what.clientWidth
    const under = !!sw && !!tools && tools.width > 0 && sw.right > tools.left
    if (cut || under) setFit({ key, room: room === 'full' ? 'compact' : 'menu' })
    else if (fit.key !== key) setFit({ key, room })
  })
  return room
}

/* -- which post, which kind ------------------------------------------------ */

/** The post an item is from: its object's, else its live address's. */
export function postOf(address: string): Id | null {
  const st = store.objects.get(address)
  return st && 'object' in st ? st.object.post : liveRoot(address)
}
/** Is it the post's words, drawn as an object? */
export function isWords(address: string): boolean {
  const st = store.objects.get(address)
  return !!st && 'object' in st && st.object.kind === 'post-text'
}
/** By kind: the words first, then the objects, each in thread order. */
export function byKind<T extends { address: string }>(items: T[]): T[] {
  return [...items.filter((i) => isWords(i.address)), ...items.filter((i) => !isWords(i.address))]
}

interface Row { id: Id; words: ObjectRef[]; objs: ObjectRef[] }

/** One row per post that carries something shown, in the thread's order. */
export function rowsOf(items: ObjectRef[], posts: Id[]): Row[] {
  const by = new Map<Id, Row>()
  const order: Id[] = [...posts]
  for (const it of items) {
    const id = postOf(it.address) ?? ''
    if (!by.has(id)) { by.set(id, { id, words: [], objs: [] }); if (!order.includes(id)) order.push(id) }
    by.get(id)![isWords(it.address) ? 'words' : 'objs'].push(it)
  }
  return order.filter((id) => by.has(id)).map((id) => by.get(id)!)
}

const at = (name: string) => '@' + name.replace(/^@/, '')
const num = (p: Post | undefined) => (p?.number != null ? `#${p.number}` : 'this post')
/** A post's first words, on one line. */
function firstWords(p: Post | undefined): string {
  if (!p) return ''
  const w = said(p).words.replace(/[`*_>#[\]|]/g, '').replace(/\s+/g, ' ').trim()
  return w.length > 110 ? w.slice(0, 108).trimEnd() + '…' : w
}

/* -- the grouped Stage ----------------------------------------------------- */

export interface GroupedProps {
  /** the zone, which owns the origin mark it sets */
  zone: string
  /** the followed items (not the kept), in thread order */
  items: ObjectRef[]
  /** the posts followed, the opening post first */
  posts: Id[]
  /** the zone's layout, which each row draws its objects in (never one that
   *  fills the zone: `replyNot`) */
  mode: PresentMode
  width: number
  height: number
  onOpen: PresentProps['onOpen']
  onKeep: PresentProps['onKeep']
  onRemove?: PresentProps['onRemove']
  /** A reply being read is marked without narrowing the grouped thread. */
  highlight?: Id | null
}

const FILTER_LABELS: Record<string, string> = {
  objects: 'Objects',
  everything: 'Words and objects',
  sections: 'Its blocks',
  media: 'Media',
  files: 'Files',
  forms: 'Forms',
  fillable: 'Things to fill in',
  kinds: 'Kinds',
  'needs-you': 'What needs you',
}

function findZoneInArr(a: { tree: Node; pages: { tree: Node }[]; focus?: { column?: Zone; floats?: { zone: Zone }[] } }, id: string): Zone | undefined {
  const fromNode = (n: Node): Zone | undefined => {
    if (n.type === 'zone') return n.id === id ? n : undefined
    for (const k of n.kids) {
      const z = fromNode(k)
      if (z) return z
    }
    return undefined
  }
  const main = fromNode(a.tree)
  if (main) return main
  for (const p of a.pages) {
    const z = fromNode(p.tree)
    if (z) return z
  }
  if (a.focus?.column && a.focus.column.id === id) return a.focus.column
  for (const f of a.focus?.floats ?? []) {
    if (f.zone.id === id) return f.zone
  }
  return undefined
}

export default function Grouped({ zone, items, posts, mode, width, height, onOpen, onKeep, onRemove, highlight }: GroupedProps) {
  const arr = useArr()
  const currentZone = findZoneInArr(arr, zone)
  const show = currentZone?.slot?.show
  const rows = useMemo(() => rowsOf(items, posts), [items, posts])
  const stateKey = { surface: zone, resource: 'grouped' }
  const [focus, setFocus] = useViewState<Id | null>(stateKey, 'focus', null)
  const [open, setOpen] = useViewState<Id | null>(stateKey, 'open', null)
  /* which object of each post's stack is shown (by address), and which show all */
  const [cur, setCur] = useViewState<Record<Id, string>>(stateKey, 'cur', {})
  const [all, setAll] = useViewState<Record<Id, boolean>>(stateKey, 'all', {})
  const root = useRef<HTMLDivElement | null>(null)
  const ids = rows.map((r) => r.id)
  const openNow = open && ids.includes(open) ? open : null
  const focusNow = focus && ids.includes(focus) ? focus : null
  const active = openNow ?? focusNow ?? (highlight && ids.includes(highlight) ? highlight : null)

  /* The post it came from is marked where it is drawn; cleared as focus goes. */
  const activePost = usePost(active ?? '')
  useEffect(() => {
    if (active) markOnStage(zone, active, activePost?.number ?? null)
    else clearOnStage(zone)
  }, [zone, active, activePost?.number])
  useEffect(() => () => clearOnStage(zone), [zone])

  /* FOCUS LEAVES when the pointer goes down, or focus moves, outside the
     Stage's rows -- not into what a card opened from here (its detail, the
     viewer, Keep…'s menu), which still shows that post's object; an opened
     row stays open until it is closed. */
  useEffect(() => {
    if (!focusNow) return
    const away = (t: EventTarget | null) => t instanceof Element
      ? !root.current?.contains(t) && !t.closest(OPENED_FROM)
      : t instanceof Node && !root.current?.contains(t)
    const down = (e: PointerEvent) => { if (away(e.target)) setFocus(null) }
    const moved = (e: FocusEvent) => { if (away(e.target)) setFocus(null) }
    document.addEventListener('pointerdown', down, true)
    document.addEventListener('focusin', moved, true)
    return () => { document.removeEventListener('pointerdown', down, true); document.removeEventListener('focusin', moved, true) }
  }, [focusNow])

  /* An opened row is brought into view inside the Stage, and keyboard focus
     goes with it: the control pressed (⤢, a folded line, ↑ ↓) is replaced
     as the rows change, and ↑ ↓ and Esc must still reach the Stage. Closed,
     focus stays in the Stage. Focus elsewhere on the page is not taken. */
  const wasOpen = useRef<Id | null>(null)
  useEffect(() => {
    const el = root.current
    const had = wasOpen.current
    wasOpen.current = openNow
    if (!el || had === openNow) return
    const here = !document.activeElement || document.activeElement === document.body || el.contains(document.activeElement)
    const row = openNow ? el.querySelector<HTMLElement>(`.pz-grow[data-post="${CSS.escape(openNow)}"]`) : null
    row?.scrollIntoView({ block: 'nearest' })
    if (here) (row ?? el).focus({ preventScroll: true })
  }, [openNow])

  const openRow = (id: Id, address?: string) => {
    if (address) setCur((c) => ({ ...c, [id]: address }))
    setOpen(id)
    setFocus(id)
  }
  const close = () => { const was = openNow; setOpen(null); setFocus(was) }
  const step = (d: number) => {
    const i = openNow ? ids.indexOf(openNow) : -1
    const next = ids[i + d]
    if (next) openRow(next)
  }
  const keys = (e: ReactKey) => {
    const t = e.target as HTMLElement
    if (t.closest('input, textarea, select, [contenteditable="true"]')) return
    if (openNow && (e.key === 'ArrowUp' || e.key === 'ArrowDown')) {
      e.preventDefault(); e.stopPropagation(); step(e.key === 'ArrowDown' ? 1 : -1)
    } else if (openNow && e.key === 'Escape') {
      e.preventDefault(); e.stopPropagation(); close()
    }
  }
  /* "View parent's objects": the parent's row, opened or focused as this one
     is; a parent not on the Stage is read, which is a pick. */
  const toParent = (parent: Id) => {
    if (!ids.includes(parent)) { trace(parent); return }
    if (openNow) openRow(parent)
    else {
      setFocus(parent)
      root.current?.querySelector(`.pz-grow[data-post="${CSS.escape(parent)}"]`)?.scrollIntoView({ block: 'nearest' })
    }
  }

  if (!(width > 0) || !rows.length) return null
  const inner = Math.max(120, width - GUTTER - PADS)
  return (
    <div ref={root} className="pz pz-grouped" data-grouping="reply" data-present={mode} data-rows={rows.length} data-open={openNow ?? undefined}
      data-focused={focusNow ?? undefined} onKeyDown={keys} tabIndex={-1}>
      {rows.map((r, i) => (
        <PostRow key={r.id} row={r} n={i + 1} index={posts.indexOf(r.id)} mode={mode} show={show}
          inner={inner} height={height} folded={!!openNow && openNow !== r.id} opened={openNow === r.id} focused={active === r.id}
          canUp={i > 0} canDown={i < rows.length - 1} up={rows[i - 1]?.id ?? null} down={rows[i + 1]?.id ?? null}
          parentObjects={(id) => rows.find((x) => x.id === id)?.objs.length ?? null}
          at={cur[r.id] ?? null} setAt={(a) => setCur((c) => ({ ...c, [r.id]: a }))}
          all={!!all[r.id]} setAll={(on) => setAll((x) => ({ ...x, [r.id]: on }))}
          onFocus={() => setFocus(r.id)} onOpenRow={(a) => openRow(r.id, a)} onClose={close} onStep={step} onParent={toParent}
          onOpen={onOpen} onKeep={onKeep} onRemove={onRemove} />
      ))}
    </div>
  )
}

/* -- one post's row -------------------------------------------------------- */

function PostRow({ row, n, index, mode, show, inner, height, folded, opened, focused, canUp, canDown, up, down, parentObjects,
  at: atAddress, setAt, all, setAll, onFocus, onOpenRow, onClose, onStep, onParent, onOpen, onKeep, onRemove }: {
  row: Row; n: number; index: number; mode: PresentMode; show?: Show; inner: number; height: number
  folded: boolean; opened: boolean; focused: boolean
  canUp: boolean; canDown: boolean; up: Id | null; down: Id | null
  parentObjects: (id: Id) => number | null
  at: string | null; setAt: (a: string) => void; all: boolean; setAll: (on: boolean) => void
  onFocus: () => void; onOpenRow: (address?: string) => void; onClose: () => void; onStep: (d: number) => void; onParent: (id: Id) => void
  onOpen: PresentProps['onOpen']; onKeep: PresentProps['onKeep']; onRemove?: PresentProps['onRemove']
}) {
  const post = usePost(row.id)
  const parent = usePost(post?.reply_to ?? '')
  const upPost = usePost(up ?? '')
  const downPost = usePost(down ?? '')
  const opening = !post?.reply_to
  const role = !post ? '' : !post.reply_to ? 'opening post' : index > 0 ? `reply ${index}` : `reply to ${post.reply_to_number != null ? '#' + post.reply_to_number : 'a post'}`
  const who = post ? `${num(post)} · ${at(post.author_name)}` : '…'
  const { words, objs } = row
  const counted = [
    words.length ? `${words.length} text` : null,
    objs.length ? `${objs.length} ${objs.length === 1 ? 'object' : 'objects'}` : words.length ? 'words only' : null,
  ].filter(Boolean).join(' · ')

  if (folded) {
    return (
      <button className="pz-grow pz-gfold" data-post={row.id} data-row={n} onClick={() => onOpenRow()}
        title={`Open ${who} in place`}>
        <span className="pz-gnum" aria-hidden="true">{n}</span>
        <b className="pz-gwho">{who}</b> <span className="pz-grole">{role}</span>
        <span className="pz-gfirst">{firstWords(post) ? ` — ${firstWords(post)}` : ''}</span>
        <span className="pz-gcount">{objs.length || ''}</span>
      </button>
    )
  }

  /* List is a line each, the words' too; every other layout has the words
     left and draws the objects right in it (Cards as one stack) */
  const lines = mode === 'list'
  const two = !lines && words.length > 0 && inner >= 480
  const wordsW = two ? Math.floor((inner - GAP) * 0.58) : inner
  const objsW = two ? inner - GAP - wordsW : inner
  const wordsH = opened ? 100000 : 150
  const objsH = opened ? Math.max(220, height - 200) : mode === 'cards' ? 150 : 320
  const postNum = post?.number != null ? `#${post.number}` : (opening ? 'this post' : 'this reply')
  const noneText = (show && show !== 'objects' && show !== 'everything')
    ? `Nothing here matches ${FILTER_LABELS[show] ?? show}`
    : `No objects in ${postNum}`
  const none = <p className={'pz-gnone' + (lines ? ' pz-gnone-line' : '')}>{noneText}</p>
  const shown = focused || opened
  const parentN = post?.reply_to ? parentObjects(post.reply_to) : null
  const origin = !post ? null : opening
    ? `Showing ${num(post)} · the opening post of this thread`
    : `Showing ${num(post)} · replying to ${post.reply_to_number != null ? `#${post.reply_to_number}` : 'a post'}`

  /* A CARD DOES WHAT IT ALWAYS DID: a click, ⤢ or Enter opens it over the
     arrangement, Keep…, Focus, its caption and fold act as before (only the
     layout is this change's). A click anywhere in the row also focuses the
     row -- on the click, not the press, and its origin line takes the
     counts' place in the header, so nothing moves under the pointer -- as
     does keyboard focus arriving in it. The row opens in place by its own
     ⤢, its folded line, or ↑ ↓. */
  const click = () => onFocus()
  const keyFocus = (e: ReactFocus) => { if ((e.target as HTMLElement).matches?.(':focus-visible')) onFocus() }

  return (
    <section className={'pz-grow' + (shown ? ' on' : '') + (opened ? ' open' : '')} data-post={row.id} data-row={n}
      data-focused={focused ? '' : undefined} data-opened={opened ? '' : undefined}
      /* opened, a click anywhere in it keeps ↑ ↓ and Esc with it */
      tabIndex={opened ? -1 : undefined}
      aria-label={`${who}, ${role}${opened ? ', opened in place' : ''}`}
      onClickCapture={click} onFocusCapture={keyFocus}>
      <span className="pz-gnum" aria-hidden="true">{n}</span>
      <header className="pz-ghead">
        <b className="pz-gwho">{who}</b>
        <span className="pz-grole">{role}{opened ? ' · opened in place' : ''}</span>
        <span className="pz-ggrow" />
        {/* focused, the row says where it is from in the counts' place, so
            nothing below the header moves under the pointer */}
        {!opened && (focused && origin
          ? <span className="pz-gorigin pz-gorigin-top" data-origin="top">{origin}</span>
          : <span className="pz-gcount">{counted}</span>)}
        {opened ? (
          <span className="pz-gsteps">
            <button data-act="row-up" disabled={!canUp} onClick={() => onStep(-1)}
              title={canUp ? `The post before: ${num(upPost)} (↑)` : 'This is the first post'} aria-label="The post before">{'↑'}{canUp && upPost ? ` ${num(upPost)}` : ''}</button>
            <button data-act="row-down" disabled={!canDown} onClick={() => onStep(1)}
              title={canDown ? `The post after: ${num(downPost)} (↓)` : 'This is the last post'} aria-label="The post after">{canDown && downPost ? `${num(downPost)} ` : ''}{'↓'}</button>
            <button data-act="row-close" onClick={onClose} title="Close: back to every post (Esc)" aria-label="Close: back to every post">{'✕'}</button>
          </span>
        ) : (
          <button className="pz-gopen" data-act="row-open" onClick={() => onOpenRow()} title={`Expand ${who} in place: it takes the section's room, nothing else moves`} aria-label={`Expand ${who} in place`}>{'⤢'}</button>
        )}
      </header>
      {opened && origin && <p className="pz-gorigin pz-gorigin-top" data-origin="top">{origin}</p>}
      {lines ? (
        <div className="pz-gbody pz-glines">
          <Present items={[...words, ...objs]} mode="list" width={inner} height={objsH} onOpen={onOpen} onKeep={onKeep} onRemove={onRemove} />
          {objs.length === 0 && none}
        </div>
      ) : (
        <div className={'pz-gbody' + (two ? ' two' : '')}>
          {words.length > 0 && (
            <div className="pz-gwords" style={two ? { width: wordsW } : undefined}>
              {words.map((it) => <Card key={it.address} item={it} w={wordsW} h={wordsH} onOpen={onOpen} onKeep={onKeep} onRemove={onRemove} className="pz-gword" />)}
            </div>
          )}
          <div className="pz-gobjs" style={two ? { width: objsW } : undefined}>
            {objs.length === 0 ? none
              : mode === 'cards'
                ? <Stack objs={objs} w={objsW} h={objsH} at={atAddress} setAt={setAt} all={all} setAll={setAll} onOpen={onOpen} onKeep={onKeep} onRemove={onRemove} />
                : <Present items={objs} mode={mode} width={objsW} height={objsH} onOpen={onOpen} onKeep={onKeep} onRemove={onRemove} />}
          </div>
        </div>
      )}
      {shown && post && !opening && (
        <p className="pz-gorigin pz-gorigin-foot" data-origin="foot">
          Answering {post.reply_to_number != null ? `#${post.reply_to_number}` : 'a post'}{parent ? ` · ${at(parent.author_name)}` : ''}
          {post.reply_to && (
            <button className="pz-gparent" data-act="view-parent" onClick={(e) => { e.stopPropagation(); onParent(post.reply_to!) }}>
              View parent's {parentN ? `${parentN} ${parentN === 1 ? 'object' : 'objects'}` : 'objects'} {'↑'}
            </button>
          )}
        </p>
      )}
    </section>
  )
}

/* -- many objects, one stack ----------------------------------------------- */

function Stack({ objs, w, h, at, setAt, all, setAll, onOpen, onKeep, onRemove }: {
  objs: ObjectRef[]; w: number; h: number; at: string | null; setAt: (a: string) => void; all: boolean; setAll: (on: boolean) => void
  onOpen: PresentProps['onOpen']; onKeep: PresentProps['onKeep']; onRemove?: PresentProps['onRemove']
}) {
  if (objs.length === 1) return <Card item={objs[0]} w={w} h={h} onOpen={onOpen} onKeep={onKeep} onRemove={onRemove} />
  if (all) {
    return (
      <div className="pz-gall" data-stack="all">
        {objs.map((it) => <Card key={it.address} item={it} w={w} h={150} onOpen={onOpen} onKeep={onKeep} onRemove={onRemove} />)}
        <button className="pz-gstackbtn" data-act="stack-one" onClick={() => setAll(false)}>One at a time</button>
      </div>
    )
  }
  const i = Math.max(0, at ? objs.findIndex((x) => x.address === at) : 0)
  const it = objs[i]
  const go = (d: number) => setAt(objs[(i + d + objs.length) % objs.length].address)
  return (
    <div className="pz-gstack" role="group" aria-roledescription="stack" aria-label={`${i + 1} of ${objs.length}`} data-stack="one">
      <Card key={it.address} item={it} w={w} h={h} onOpen={onOpen} onKeep={onKeep} onRemove={onRemove} />
      <div className="pz-gstackbar">
        <button className="pz-gstackbtn" data-act="stack-prev" onClick={() => go(-1)} aria-label="Previous object">{'‹'} Previous</button>
        <span className="pz-gstackn" aria-live="polite">{i + 1} / {objs.length}</span>
        <button className="pz-gstackbtn" data-act="stack-next" onClick={() => go(1)} aria-label="Next object">Next {'›'}</button>
        <button className="pz-gstackbtn pz-gstackall" data-act="stack-all" onClick={() => setAll(true)}>Show all</button>
      </div>
    </div>
  )
}
