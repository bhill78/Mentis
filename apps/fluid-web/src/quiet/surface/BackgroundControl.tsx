/* The existing header mount stays a single Settings button. The atmosphere
 * uses Fluid's presentation store; local appearance stays in this browser. */
import { useEffect, useRef, useState } from 'react'
import { ATMOSPHERES, type Atmosphere } from '../../atmosphere'
import { setTheme, useLookControls, useTheme, type Theme } from '../../fluid/frame/look'
import { setSurfaceAppearance, setSurfaceTreatment, useSurfaceAppearance, useSurfaceTreatment } from './Surface'

export default function BackgroundControl() {
  const controls = useLookControls()
  const theme = useTheme()
  const surface = useSurfaceTreatment()
  const look = useSurfaceAppearance()
  const [open, setOpen] = useState(false)
  const root = useRef<HTMLDivElement>(null)
  const trigger = useRef<HTMLButtonElement>(null)
  useEffect(() => {
    if (!open) return
    const outside = (event: PointerEvent) => {
      if (event.target instanceof Node && !root.current?.contains(event.target)) setOpen(false)
    }
    const escape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') { setOpen(false); trigger.current?.focus() }
    }
    document.addEventListener('pointerdown', outside)
    document.addEventListener('keydown', escape)
    return () => {
      document.removeEventListener('pointerdown', outside)
      document.removeEventListener('keydown', escape)
    }
  }, [open])
  if (!controls) return null
  const opacity = surface === 'solid' ? look.solidOpacity : look.glassOpacity
  return <div ref={root} className="qc-background">
    <button ref={trigger} type="button" className="qc-settings-button" aria-label="Settings" title="Settings"
      aria-expanded={open} aria-controls="qc-appearance" onClick={() => setOpen(!open)}>
      <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
        <path d="m10 3-.6 2.3-1.5.9-2.3-.6-2 3.4 1.7 1.7v1.8L3.6 14l2 3.4 2.3-.6 1.5.9.6 2.3h4l.6-2.3 1.5-.9 2.3.6 2-3.4-1.7-1.5v-1.8L20.4 9l-2-3.4-2.3.6-1.5-.9L14 3Z" />
        <circle cx="12" cy="11.5" r="3" />
      </svg>
    </button>
    {open && <section id="qc-appearance" className="qc-appearance" aria-label="Appearance settings">
      <div className="qc-appearance-heading"><h2>Appearance</h2>
        <button type="button" aria-label="Close settings" onClick={() => { setOpen(false); trigger.current?.focus() }}>×</button></div>
      <label className="qc-background-pick">Theme
        <select aria-label="Theme" value={theme} onChange={(e) => setTheme(e.target.value as Theme)}>
          <option value="system">System</option><option value="light">Light</option><option value="dark">Dark</option>
        </select>
      </label>
      <label className="qc-background-pick">Background
        <select aria-label="Background" value={controls.current} onChange={(e) => void controls.choose(e.target.value as Atmosphere)}>
          {ATMOSPHERES.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
          {controls.pictures.looks.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
        </select>
      </label>
      <fieldset className="qc-surface-pick"><legend>Surface</legend>
        {(['solid', 'glass'] as const).map((id) => <label key={id}>
          <input type="radio" name="qc-surface" checked={surface === id} onChange={() => setSurfaceTreatment(id)} />
          {id === 'solid' ? 'Solid' : 'Glass'}
        </label>)}
      </fieldset>
      <label className="qc-appearance-range">Surface opacity <output>{opacity}%</output>
        <input aria-label="Surface opacity" type="range" min="0" max="100" value={opacity} onChange={(e) => setSurfaceAppearance(
          surface === 'solid' ? { solidOpacity: Number(e.target.value) } : { glassOpacity: Number(e.target.value) })} />
      </label>
      {surface === 'glass' && <label className="qc-appearance-range">Glass blur <output>{look.blur}px</output>
        <input aria-label="Glass blur" type="range" min="0" max="32" value={look.blur}
          onChange={(e) => setSurfaceAppearance({ blur: Number(e.target.value) })} />
      </label>}
      <div className="qc-appearance-pins">
        <label><input type="checkbox" checked={look.pinHeader} onChange={(e) => setSurfaceAppearance({ pinHeader: e.target.checked })} />Pin header</label>
        <label><input type="checkbox" checked={look.pinMargins} onChange={(e) => setSurfaceAppearance({ pinMargins: e.target.checked })} />Pin margins</label>
      </div>
    </section>}
  </div>
}
