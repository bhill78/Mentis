/* THE FOCUS LENS, DRAWN (focus/lens.ts; compose.ts decides, lensImpl.ts
 * keeps it).
 *
 * Over the main area of the Page shown, while Focus is on: the FOCUS AREA
 * (a quiet bar, then the target drawn by the renderer it has everywhere --
 * the zone body, the conversation itself, a run's panel, a whole post, a
 * Brain entry), the SHELF beside it in Docked and Mixed, and what the one
 * compact control reveals in Only Focus. The arrangement under it stays
 * drawn and untouched (hidden, so its scroll and state are there when Focus
 * ends); the conversation, which is drawn once, is lent to the lens
 * (hosts.tsx `claim`) and goes back to its place by itself.
 *
 * Keys: Shift+F focuses what the pointer or the keyboard is on (a card, a
 * section, a window), and switches while Focus is on; 1-9 switch to the
 * nth thing beside Focus; Esc steps back (fluid/escape.ts, ESC.lens). */

import { useEffect, useLayoutEffect, useMemo, useRef, useState, type CSSProperties } from 'react'
import { useNarrow } from '../frame/narrow'
import { store } from '../store'
import { kindOf } from '../../experimental/objectkinds'
import { isBrainRef } from '../brain/address'
import { PostView } from '../render/post'
import RunPanel from '../runs/RunPanel'
import * as nav from '../nav'
import { usePost } from '../workspace/hooks'
import { ESC, onEscape } from '../escape'
import { keepSlot, type Zone } from '../workspace/tree'
import { ObjectActions } from '../objects/ObjectActions'
import { PlacedZone } from './ColumnPlace'
import { FocusSplit } from './FocusSplit'
import { Mount } from './hosts'
import { lens, PRESENTATIONS, type FocusTarget } from './lens'
import { compose, hiddenOf, prefHeight, shapeOf, shelfOf, shelfWidth, surfacesOf, type Composition, type Lens, type Rect, type Room, type Surface } from './compose'
import { focusSurface, lensTitle, setLensRoom, stepForward, toggleHide, toggleReveal, toggleTidy, useLens } from './lensImpl'
import { locate } from './model'
import { useShownView } from './page'
import { CONVERSATION_ID, CONVERSATION_SHOW } from './types'
import type { Arr } from '../workspace/place'
import { RUN_SHOW } from './model'
import './lens.css'

const box = (r: Rect): CSSProperties => ({ left: r.x, top: r.y, width: r.w, height: r.h })
const typing = (t: EventTarget | null) => {
  const el = t as HTMLElement | null
  return !!el && (!!el.matches?.('input, textarea, select') || !!el.isContentEditable)
}

export default function LensLayer() {
  const { page, view: a } = useShownView()
  const L = useLens(page)
  const narrow = useNarrow()
  const root = useRef<HTMLDivElement | null>(null)
  const [room, setRoom] = useState<Room>({ w: 0, h: 0 })
  useLayoutEffect(() => {
    const el = root.current
    if (!el) return
    const read = () => setRoom((r) => (r.w === el.clientWidth && r.h === el.clientHeight ? r : { w: el.clientWidth, h: el.clientHeight }))
    const ro = new ResizeObserver(read)
    ro.observe(el); read()
    return () => ro.disconnect()
  }, [])
  useEffect(() => setLensRoom(room), [room])
  const comp = L && room.w ? compose(room, shapeOf(L, narrow)) : null

  /* The main area knows Focus is on: what the lens covers is hidden there
     (lens.css), never unmounted. */
  const on = !!comp, floats = comp?.floats
  useLayoutEffect(() => {
    const main = root.current?.parentElement
    if (!main) return
    main.classList.toggle('fx-lens', on)
    if (floats) main.dataset.lensFloats = floats
    else delete main.dataset.lensFloats
  }, [on, floats])
  useEffect(() => () => {
    const main = root.current?.parentElement
    main?.classList.remove('fx-lens')
    if (main) delete main.dataset.lensFloats
  }, [])

  /* Esc: one step back through this Page's Focus history, then out. */
  useEffect(() => onEscape(ESC.lens, () => lens.stepBack()), [])
  useFocusKeys(a, L, comp)

  if (!L || !comp) return <div ref={root} className="fl-lens-root" aria-hidden="true" />
  const shelf = shelfOf(a, L.target, comp)
  const hidden = hiddenOf(a, L.target, comp)
  const title = lensTitle(L.target, page)
  const sw = shelfWidth(room.w)
  const reveal: Rect = narrow || comp.presentation === 'only' && room.w < 720
    ? { x: 0, y: Math.round(room.h * 0.35), w: room.w, h: room.h - Math.round(room.h * 0.35) }
    : { x: L.shelfSide === 'left' ? comp.area.x : comp.area.x + comp.area.w - sw, y: comp.stage.y + 4, w: sw, h: Math.max(160, comp.stage.h - 8) }
  return (
    <div ref={root} className="fl-lens-root on">
      <div className="fl-lens" data-presentation={comp.presentation} data-narrow={narrow ? '' : undefined}>
        <section className="fl-area" style={box(comp.area)} aria-label={`Focus: ${title}`}>
          <Bar L={L} comp={comp} title={title} hidden={hidden.length} narrow={narrow} />
          <div className="fl-stage" data-target={L.target.kind === 'surface' ? L.target.id : L.target.address}>
            <Target a={a} page={page} target={L.target} />
          </div>
        </section>
        {comp.shelf && (
          <aside className="fl-shelf" style={box(comp.shelf)} aria-label="Beside Focus">
            {shelf.map((s) => <Tile key={s.id} s={s} page={page} roomH={room.h} />)}
            {!shelf.length && <p className="fl-empty">Nothing else is on this Page.</p>}
          </aside>
        )}
        {L.reveal && hidden.length > 0 && (
          <aside className="fl-reveal" style={box(reveal)} aria-label="Hidden beside Focus">
            {hidden.map((s) => <Tile key={s.id} s={s} page={page} roomH={room.h} />)}
          </aside>
        )}
      </div>
    </div>
  )
}

/* -- the quiet indicator ----------------------------------------------------- */

function Bar({ L, comp, title, hidden, narrow }: { L: Lens; comp: Composition; title: string; hidden: number; narrow: boolean }) {
  const back = L.history.at(-1), fwd = L.forward[0]
  const spatial = comp.presentation === 'floating' || comp.presentation === 'mixed'
  const name = (t?: FocusTarget) => (t ? lensTitle(t, L.page) : '')
  return (
    <div className="fl-bar" role="toolbar" aria-label="Focus">
      <span className="fl-mark" aria-hidden="true">⛶</span>
      <span className="fl-name" title={title}>{title}</span>
      {L.target.kind === 'object' && L.target.from && <span className="fl-from">{L.target.from}</span>}
      <span className="fl-hist">
        <button type="button" className="ob-act" disabled={!back} aria-label="Back" title={back ? `Back to ${name(back)} (Esc)` : 'Nothing before this in Focus'} onClick={() => lens.stepBack()}>‹</button>
        <button type="button" className="ob-act" disabled={!fwd} aria-label="Forward" title={fwd ? `Forward to ${name(fwd)}` : 'Nothing after this in Focus'} onClick={() => stepForward()}>›</button>
      </span>
      {!narrow && (
        <span className="fl-pres" role="radiogroup" aria-label="Focus presentation">
          {PRESENTATIONS.map((p) => (
            <button key={p.id} type="button" className="ob-act" role="radio" aria-checked={comp.presentation === p.id} aria-label={p.label}
              title={`${p.label}: ${p.says}`} onClick={() => lens.setPresentation(p.id)}>{p.icon}</button>
          ))}
        </span>
      )}
      {!narrow && spatial && (
        <span className="fl-wins">
          <button type="button" className="ob-act" aria-pressed={!!L.tidy} aria-label="Tidy around Focus"
            title={L.tidy ? 'Put the windows back where they were' : 'Tidy around Focus: line the windows up beside it (press again to undo)'} onClick={toggleTidy}>⊞</button>
          <button type="button" className="ob-act" aria-pressed={L.hideOthers} aria-label="Hide other windows"
            title={L.hideOthers ? 'Show the other windows again' : 'Hide other windows (press again to show them)'} onClick={toggleHide}>◌</button>
        </span>
      )}
      {hidden > 0 && (
        <button type="button" className="ob-act fl-reveal-btn" aria-expanded={L.reveal} aria-label={`Show what is hidden: ${hidden}`}
          title={L.reveal ? 'Hide them again' : `Show the ${hidden} beside Focus that ${hidden === 1 ? 'is' : 'are'} hidden`} onClick={() => toggleReveal()}>☰<span className="fl-count">{hidden}</span></button>
      )}
      <span className="fl-grow" />
      {!narrow && <button type="button" className="ob-act" aria-label="Keep this layout" title="Keep this layout: make it the arrangement (Undo returns the one before)" onClick={() => lens.keepLayout()}>✓</button>}
      <button type="button" className="ob-act fl-restore" aria-label="Restore" title="Restore: back to the arrangement as it was" onClick={() => lens.restore()}>↺</button>
    </div>
  )
}

/* -- what is drawn ----------------------------------------------------------- */

/** What Focus is on, with the renderer it has everywhere. */
function Target({ a, page, target }: { a: Arr; page: string; target: FocusTarget }) {
  if (target.kind === 'surface') {
    const at = locate(a, target.id)
    return at ? <SurfaceBody zone={at.zone} page={page} /> : <p className="fl-empty">This is no longer on the Page.</p>
  }
  return <ObjectBodyIn address={target.address} title={target.title} page={page} from={target.from} />
}

/** One object in the Focus area: a whole post as full screen draws it; any
 *  other object (a Brain entry too) as a section holding it alone. */
function ObjectBodyIn({ address, title, page, from }: { address: string; title?: string; page: string; from?: string }) {
  const post = address.startsWith('post:') ? address.slice(5) : null
  const zone = useMemo<Zone>(() => ({
    type: 'zone', id: 'lens-' + address.replace(/[^A-Za-z0-9_-]/g, '-').slice(0, 80), show: 'object', name: title ?? 'Object',
    slot: keepSlot([address], 'focus'), ...(from ? { options: { says: from } } : {}),
  }), [address, title, from])
  if (post) return <PostIn id={post} />
  return <PlacedZone key={address} z={zone} page={page} why="Keep this layout, or Float it, to split it" />
}

function PostIn({ id }: { id: string }) {
  const post = usePost(id)
  useEffect(() => { if (!store.posts.has(id)) void store.loadPosts([id]).catch(() => {}) }, [id])
  if (!post) return <p className="fl-empty" aria-busy="true">Reading the post…</p>
  return (
    <div className="fl-post turn-body" data-address={'post:' + id}>
      <ObjectActions target={{ address: 'post:' + id, kind: 'post', title: post.number != null ? `#${post.number}` : 'Post' }} only={['peek', 'float', 'keep']} className="fl-post-acts" />
      <PostView post={post} context="full" here={null} />
    </div>
  )
}

/** A surface of the Page (the conversation, a run, a section or a window's
 *  zone) where the lens draws it. */
function SurfaceBody({ zone, page, tile = false }: { zone: Zone; page: string; tile?: boolean }) {
  if (zone.show === CONVERSATION_SHOW) return <div className="fq-conv-body fl-conv"><Mount id={CONVERSATION_ID} claim={1} /></div>
  if (zone.show === RUN_SHOW) return <RunPanel run={String(zone.options?.run ?? '')} who={String(zone.options?.who ?? zone.name ?? '')} floating onClose={() => {}} onOpenPost={(c, p) => nav.read(c, p, null)} />
  return <PlacedZone z={zone} page={page} ctl={tile ? { id: zone.id, lens: true } : undefined} />
}

/** What an object zone holds, for its height on the shelf. */
function kindOfZone(z: Zone): string {
  const a = z.slot?.items[0]
  if (!a) return 'object'
  if (isBrainRef(a)) return 'brain'
  if (a.startsWith('post:')) return 'post'
  const st = store.objects.get(a)
  return st && 'object' in st ? kindOf(st.object).word : 'object'
}

/** A secondary beside Focus: live, at a height for what it holds; ⛶ on it
 *  switches Focus to it (the zone's own tools carry it; the conversation and
 *  a run, which have none of those, get a slim head). */
function Tile({ s, page, roomH }: { s: Surface; page: string; roomH: number }) {
  const h = prefHeight(s.kind === 'object' ? kindOfZone(s.zone) : s.kind, roomH)
  const head = s.kind === 'conversation' || s.kind === 'run'
  return (
    <section className="fl-tile" data-lens-tile={s.id} data-place={s.place} style={{ height: h }} aria-label={s.name}>
      {head && (
        <header className="fl-tile-head">
          <span className="fl-tile-name">{s.name}</span>
          <span className="fl-grow" />
          <FocusSplit surface={{ id: s.id, title: s.name }} />
        </header>
      )}
      <div className="fl-tile-body"><SurfaceBody zone={s.zone} page={page} tile /></div>
    </section>
  )
}

/* -- keys -------------------------------------------------------------------- */

/** What Shift+F is about: the card, window or section under the keyboard's
 *  focus, else under the pointer. */
function aboutNow(a: Arr, el: Element | null): FocusTarget | null {
  if (!el || el.closest('.fl-bar, .pz-viewer')) return null
  const card = el.closest<HTMLElement>('[data-address]')
  if (card?.dataset.address) {
    const address = card.dataset.address
    const title = card.querySelector('h4, h3')?.textContent?.trim() || undefined
    return { kind: 'object', address, ...(title ? { title } : {}) }
  }
  const tile = el.closest<HTMLElement>('[data-lens-tile]')
  if (tile?.dataset.lensTile) return { kind: 'surface', id: tile.dataset.lensTile }
  const fl = el.closest<HTMLElement>('[data-float-id]')
  const f = fl && a.focus?.floats?.find((x) => x.id === fl.dataset.floatId)
  if (f) return { kind: 'surface', id: f.zone.id, title: f.zone.name }
  const cell = el.closest<HTMLElement>('.wt-cell[data-zone-id]')
  if (cell?.dataset.zoneId && locate(a, cell.dataset.zoneId)) return { kind: 'surface', id: cell.dataset.zoneId }
  const col = el.closest<HTMLElement>('.fq-col, #conv')
  if (col) {
    const id = col.querySelector<HTMLElement>('[data-content]')?.dataset.content ?? CONVERSATION_ID
    if (locate(a, id)) return { kind: 'surface', id }
  }
  return null
}

function useFocusKeys(a: Arr, L: Lens | null, comp: Composition | null) {
  const now = useRef({ a, L, comp })
  now.current = { a, L, comp }
  useEffect(() => {
    let hovered: Element | null = null
    const over = (e: PointerEvent) => { hovered = e.target as Element | null }
    const key = (e: KeyboardEvent) => {
      if (e.defaultPrevented || typing(e.target) || e.ctrlKey || e.metaKey || e.altKey) return
      if ((e.target as Element | null)?.closest?.('[role=dialog]:not(.wk-float), .sheet, .fx-pop')) return
      const { a, L, comp } = now.current
      if (e.key === 'F' && e.shiftKey) {
        const active = document.activeElement && document.activeElement !== document.body ? document.activeElement : null
        const t = aboutNow(a, active) ?? aboutNow(a, hovered)
        if (!t) return
        e.preventDefault()
        if (t.kind === 'surface') focusSurface(t.id, t.title)
        else lens.enter(t)
        return
      }
      if (L && comp && /^[1-9]$/.test(e.key) && !e.shiftKey) {
        const beside = surfacesOf(a).filter((x) => !(L.target.kind === 'surface' && L.target.id === x.id))
        const s = beside[Number(e.key) - 1]
        if (!s) return
        e.preventDefault()
        focusSurface(s.id, s.name)
      }
    }
    document.addEventListener('pointerover', over, { passive: true })
    window.addEventListener('keydown', key)
    return () => { document.removeEventListener('pointerover', over); window.removeEventListener('keydown', key) }
  }, [])
}
