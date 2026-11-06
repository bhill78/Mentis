/* PACKAGE G owns this module: choosing and persisting the atmosphere, in the
   header's right cell (Chrome.tsx -- package A -- mounts it there; this file
   only builds what it mounts). It reads the store Surface's call to
   `useLook` leaves behind (`useLookControls`, the same split production's
   own Look sheet uses) and offers exactly the 11 built-in atmospheres --
   not the picture-made looks production's own Look sheet also offers, which
   are outside what this package was asked to build. */
import { ATMOSPHERES, type Atmosphere } from '../../atmosphere'
import { useLookControls } from '../../fluid/frame/look'
import { setSurfaceTreatment, useSurfaceTreatment, type SurfaceTreatment } from './Surface'

const TREATMENTS: { id: SurfaceTreatment; label: string }[] = [
  { id: 'solid', label: 'Solid' },
  { id: 'glass', label: 'Glass' },
]

export default function BackgroundControl() {
  const controls = useLookControls()
  const surface = useSurfaceTreatment()
  if (!controls) return null
  return (
    <div className="qc-background">
      <label className="qc-background-pick">
        <span>Background</span>
        <select aria-label="Background" value={controls.current}
          onChange={(e) => void controls.choose(e.target.value as Atmosphere)}>
          {ATMOSPHERES.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
        </select>
      </label>
      <div className="qc-surface-pick" role="radiogroup" aria-label="Surface">
        {TREATMENTS.map((t) => (
          <button key={t.id} type="button" role="radio" aria-checked={surface === t.id}
            className={surface === t.id ? 'on' : ''}
            onClick={() => setSurfaceTreatment(t.id)}>{t.label}</button>
        ))}
      </div>
    </div>
  )
}
