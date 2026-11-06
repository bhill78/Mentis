/* PACKAGE G owns this module: the painted ground every other package sits
   on. It mounts the `.qc` element the rest of the shell is laid out by --
   that element and the class it carries do not change -- and paints it by
   calling production's own `useLook` (fluid/frame/look.ts), the same hook
   Fluid's Shell draws its frame with. An atmosphere is defined once, in
   atmosphere.css's `:root[data-atmosphere=...]` token blocks, which already
   reach `/quiet`; nothing here edits that file, and nothing here duplicates
   what it declares.

   `useLook` also publishes the shared `LookControls` store BackgroundControl
   reads (`useLookControls`), the same split Shell.tsx and LookSheet.tsx use:
   one component calls the hook that paints the frame, another reads the
   store it leaves behind. Surface mounts outside QuietChat's own state and
   is handed no conversation prop -- the seam's `SurfaceView` contract is
   `{ children }` only -- so it keeps its own small copy of the address,
   the way QuietChat.tsx keeps its own. */
import { useEffect, useState, useSyncExternalStore, type ReactNode } from 'react'
import { readAddress } from '../../address'
import { useLook } from '../../fluid/frame/look'
import './surface.css'

export type SurfaceTreatment = 'solid' | 'glass'

const TREATMENT_KEY = 'mentis:quiet-surface'

function readTreatment(): SurfaceTreatment {
  try {
    const v = localStorage.getItem(TREATMENT_KEY)
    if (v === 'solid' || v === 'glass') return v
  } catch { /* storage unavailable: solid is what Quiet always drew */ }
  return 'solid'
}

/* -- the surface treatment, one value for the page, read by BackgroundControl */
let treatment: SurfaceTreatment = readTreatment()
const heard = new Set<() => void>()
const tell = () => heard.forEach((fn) => fn())
const sub = (fn: () => void) => { heard.add(fn); return () => { heard.delete(fn) } }

/** Choose solid or glass for the ground every atmosphere paints under `.qc`,
 *  and persist it the way the theme is persisted: this browser, every page. */
export function setSurfaceTreatment(t: SurfaceTreatment) {
  treatment = t
  try { localStorage.setItem(TREATMENT_KEY, t) } catch { /* this page only */ }
  tell()
}
export const useSurfaceTreatment = () => useSyncExternalStore(sub, () => treatment)
/** The same value, read without a React tree -- for anything that is not a
 *  component, including `tests/quiet_surface_unit.mjs`. */
export const getSurfaceTreatment = () => treatment

/** Which conversation the atmosphere resolves for, kept the same way
 *  QuietChat.tsx keeps it -- Surface has no prop for it. */
function useConversation() {
  const [conversation, setConversation] = useState(() => readAddress().conversation)
  useEffect(() => {
    const changed = () => setConversation(readAddress().conversation)
    window.addEventListener('hashchange', changed)
    return () => window.removeEventListener('hashchange', changed)
  }, [])
  return conversation
}

export default function Surface({ children }: { children: ReactNode }) {
  const conversation = useConversation()
  useLook(conversation, null)
  const surface = useSurfaceTreatment()
  return <div className="qc" data-surface={surface}>{children}</div>
}
