/* BACKGROUNDS AND THEME, under Settings' palette (next refinement).
 *
 * Nothing here is a new theme engine. What is drawn is Fluid's look
 * (`fluid/frame/look.ts`, `useLook`): the Brain's atmospheres and the looks
 * made from pictures, chosen for this conversation or for all of them, the
 * light/dark/system theme, and production's "make a look from a picture"
 * panel (`LookMaker`, picture/Maker) for adding one from a file. "More…"
 * opens Fluid's own full collection (`LookBody`). The reading surface's
 * treatment -- solid or glass, its opacity and blur -- is Quiet's existing
 * store (`quiet/surface/Surface.tsx`), applied to Mark 2's columns.
 *
 * The gallery shows a few looks: the one in use, the looks made from
 * pictures, then ready-made ones. */
import { useEffect, useLayoutEffect, useRef, useState, useSyncExternalStore, type CSSProperties } from 'react'
import { READ_ONLY } from './live'
import type { Atmosphere } from '../atmosphere'
import { LookBody, LookMaker, atmosphereStyle, isBuiltIn } from '../fluid/frame/LookSheet'
import { setTheme, startMaking, useLookControls, useTheme, type Theme } from '../fluid/frame/look'
import { dismissToast, useToast } from '../fluid/frame/toasts'
import { setSurfaceAppearance, setSurfaceTreatment, useSurfaceAppearance, useSurfaceTreatment } from '../quiet/surface/Surface'

const SHOWN = 6

/** The page's reading surface, as Quiet's store has it, for the columns. */
export function useSurfaceVars(): CSSProperties {
  const treatment = useSurfaceTreatment()
  const look = useSurfaceAppearance()
  const alpha = treatment === 'solid' ? look.solidOpacity : look.glassOpacity
  return {
    ['--q2-surface-alpha' as string]: `${alpha}%`,
    ['--q2-surface-blur' as string]: treatment === 'glass' ? `${look.blur}px` : '0px',
    /* GLASS BLURS THE PICTURE, all of it: the background layer itself, never
       a region behind the words. Solid leaves the look's own blur alone. */
    ...(treatment === 'glass' ? { ['--q2-bg-blur' as string]: `${look.blur}px` } : {}),
  }
}

/** Fluid's toasts (a look's Undo), drawn as Fluid draws them. */
export function Toasts() {
  const t = useToast()
  return (
    <div className={'fx-toast' + (t ? ' on' : '')} role="status" aria-hidden={!t}>
      <span>{t?.text}</span>
      {t?.action && <button onClick={() => { const run = t.action!.run; dismissToast(); run() }}>{t.action.label}</button>}
    </div>
  )
}

/** Production's maker panel, mounted where Quiet 2 draws its layer. */
export { LookMaker }

function Tile({ id, name, on, onPick }: { id: Atmosphere; name: string; on: boolean; onPick: () => void }) {
  const c = useLookControls()!
  const style = atmosphereStyle(id, c.pictures)
  return (
    <button className={'q2-look-tile' + (on ? ' on' : '')} aria-pressed={on} title={name} data-look={id} onClick={onPick}>
      <span className="q2-look-swatch" style={style} aria-hidden="true"><i /><i /><b /></span>
      <span className="q2-look-name">{name}</span>
      {on && <span className="q2-look-tick" aria-label="in use">✓</span>}
    </button>
  )
}

/* THE HEADER BAR'S LOOK: solid, glass over the background, or clear.
   Kept on this computer, like the theme. */
export type TopBar = 'solid' | 'glass' | 'clear'
const TOP_KEY = 'q2:topbar'
let topBar: TopBar = (() => { try { const v = localStorage.getItem(TOP_KEY); return v === 'glass' || v === 'clear' ? v : 'solid' } catch { return 'solid' } })()
const topHeard = new Set<() => void>()
export function setTopBar(t: TopBar) { topBar = t; try { localStorage.setItem(TOP_KEY, t) } catch { /* this page only */ } topHeard.forEach((f) => f()) }
export const useTopBar = () => useSyncExternalStore((f) => { topHeard.add(f); return () => { topHeard.delete(f) } }, () => topBar)

const THEMES: { t: Theme; label: string }[] = [{ t: 'light', label: 'Light' }, { t: 'dark', label: 'Dark' }, { t: 'system', label: 'System' }]

export function LookGallery() {
  const c = useLookControls()
  const theme = useTheme()
  const treatment = useSurfaceTreatment()
  const look = useSurfaceAppearance()
  const bar = useTopBar()
  const [more, setMore] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  /* EVERY BACKGROUND IS A PAGE OF SETTINGS, WITH A WAY BACK (owner,
     2026-11-20, navigation A4). It was drawn as a dialog fixed over the
     window, but Settings' panel is glass (a backdrop filter), and a fixed box
     inside one is placed against the panel, not the window: it filled the
     panel, its header -- the only close control, a small x -- was cut off
     above the top, and its tiles were cut off at the right. So there was no
     visible way back at all. It is now what it looked like: the gallery, in
     Settings, in place of the short one, under a Back that stays in view.
     Leaving it puts Settings where it was scrolled and the focus back on
     "More…"; Escape leaves it too, without closing Settings. The look
     chosen is the Brain's, so nothing chosen here is lost by going back. */
  const box = useRef<HTMLDivElement>(null)
  const moreBtn = useRef<HTMLButtonElement>(null)
  const backBtn = useRef<HTMLButtonElement>(null)
  const left = useRef<number | null>(null)
  /** what scrolls Settings: the panel's own body, wherever it is hosted */
  const scroller = (): HTMLElement | null => {
    for (let el = box.current?.parentElement ?? null; el; el = el.parentElement) {
      const o = getComputedStyle(el).overflowY
      if (o === 'auto' || o === 'scroll') return el
    }
    return null
  }
  const openMore = () => { left.current = scroller()?.scrollTop ?? null; setMore(true) }
  const was = useRef(false)
  useLayoutEffect(() => {
    if (more === was.current) return
    was.current = more
    const s = scroller()
    if (more) { if (s) s.scrollTop = 0; backBtn.current?.focus({ preventScroll: true }); return }
    if (s && left.current !== null) s.scrollTop = left.current
    left.current = null
    moreBtn.current?.focus({ preventScroll: true })
  }, [more])
  useEffect(() => {
    if (!more) return
    const esc = (e: KeyboardEvent) => { if (e.key === 'Escape') { e.stopPropagation(); e.preventDefault(); setMore(false) } }
    window.addEventListener('keydown', esc, true)
    return () => window.removeEventListener('keydown', esc, true)
  }, [more])
  if (!c) return <p className="q2-set-note">Reading the Brain's looks…</p>
  /* the one in use first, then pictures, then ready-made */
  const order = [
    ...c.choices.filter((x) => x.id === c.current),
    ...c.choices.filter((x) => x.id !== c.current && !isBuiltIn(x.id)),
    ...c.choices.filter((x) => x.id !== c.current && isBuiltIn(x.id)),
  ].slice(0, SHOWN)
  const where = c.conversation ? 'this conversation' : 'all conversations'
  const pick = (id: Atmosphere) => {
    if (READ_ONLY) { setErr('Read-only preview: the Brain\'s look is shown, not changed.'); return }
    setErr(null)
    void c.choose(id).catch((e: Error) => setErr(e.message || 'Could not reach the Brain.'))
  }
  const opacity = treatment === 'solid' ? look.solidOpacity : look.glassOpacity
  return (
    <div className="q2-look" ref={box} data-look-view={more ? 'every' : 'few'}>
      {more && (
        <div className="q2-look-more" role="group" aria-label="Every background">
          <p className="q2-back-bar q2-look-more-head">
            <button type="button" className="q2-back-btn" data-look-back ref={backBtn} onClick={() => setMore(false)}>‹ Back</button>
            <span className="q2-back-where">Every background</span>
          </p>
          <LookBody />
        </div>
      )}
      {/* the short gallery and the rest of the tab wait underneath, as they were */}
      <div hidden={more}>
      <div className="q2-look-grid" role="group" aria-label={`Backgrounds, for ${where}`}>
        {order.map((x) => <Tile key={x.id} id={x.id} name={x.name} on={x.id === c.current} onPick={() => pick(x.id)} />)}
      </div>
      <p className="q2-look-now">
        <span>In use: <b>{c.choices.find((x) => x.id === c.current)?.name ?? 'Mentis'}</b> · for {where}{c.conversation && !c.explicit ? ' (its usual look)' : ''}</span>
      </p>
      <div className="q2-look-acts">
        <button className="q2-look-act" ref={moreBtn} onClick={openMore} aria-expanded={more} title="Every background">More…</button>
        {!READ_ONLY && <button className="q2-look-act" onClick={() => startMaking(c.conversation ? 'conversation' : 'everywhere')}>Add from file…</button>}
      </div>
      {err && <p className="q2-editor-err" role="alert">{err}</p>}
      <div className="q2-set-row">
        <span className="q2-set-label">Theme</span>
        <span className="q2-seg" role="radiogroup" aria-label="Theme">
          {THEMES.map((x) => <button key={x.t} role="radio" aria-checked={theme === x.t} onClick={() => setTheme(x.t)}>{x.label}</button>)}
        </span>
      </div>
      <div className="q2-set-row">
        <span className="q2-set-label">Reading surface</span>
        <span className="q2-seg" role="radiogroup" aria-label="Reading surface">
          {(['solid', 'glass'] as const).map((t) => (
            <button key={t} role="radio" aria-checked={treatment === t} onClick={() => setSurfaceTreatment(t)}>{t === 'solid' ? 'Solid' : 'Glass'}</button>
          ))}
        </span>
      </div>
      <div className="q2-set-row">
        <span className="q2-set-label">Header bar</span>
        <span className="q2-seg" role="radiogroup" aria-label="Header bar">
          {(['solid', 'glass', 'clear'] as const).map((t) => (
            <button key={t} role="radio" aria-checked={bar === t} onClick={() => setTopBar(t)}>{t === 'solid' ? 'Solid' : t === 'glass' ? 'Glass' : 'Clear'}</button>
          ))}
        </span>
      </div>
      <label className="q2-set-range"><span className="q2-set-label">Opacity</span>
        <input type="range" min="0" max="100" value={opacity} aria-label="Reading surface opacity"
          onChange={(e) => setSurfaceAppearance(treatment === 'solid' ? { solidOpacity: Number(e.target.value) } : { glassOpacity: Number(e.target.value) })} />
        <output>{opacity}%</output>
      </label>
      {treatment === 'glass' && (
        <label className="q2-set-range"><span className="q2-set-label">Blur</span>
          <input type="range" min="0" max="32" value={look.blur} aria-label="Glass blur" onChange={(e) => setSurfaceAppearance({ blur: Number(e.target.value) })} />
          <output>{look.blur}px</output>
        </label>
      )}
      </div>
    </div>
  )
}
