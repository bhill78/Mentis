/* THE ONE SEAM A ZONE BODY DRAWS THROUGH (completion pack section 6, the A/C
 * contract). Stream A keeps, per zone slot, how it presents what it holds
 * (`present`) and how it looks (`appearance`), in saved arrangements and
 * named layouts, and draws the zone's objects with `Present` at the zone's
 * pixel size; the zone wrapper applies `zoneAppearanceStyle`, and the zone
 * sheet mounts the pickers. Stream C draws (all six modes, objects fitted to
 * their space). The props are the contract's, plus A's `onRemove`,
 * `appearance` and the `from` element on `onOpen` / `onKeep`. */

import './present.css'

export { default as Present } from './Present'
export { zoneAppearanceStyle } from './appearance'
export { AppearancePicker, PresentPicker } from './Pickers'
/* THE ONE INSPECTOR (render/inspect.ts): every object enlarged the same way. */
export { closeInspect, closeMedia, inspect, MediaViewerHost, openMedia, useMediaOpen } from './viewer'
/* Objects round, B2: a 'focus' detail, forwarded to the inspector (mounted by the shell). */
export { FocusView } from '../workspace/Detail'
export { useBox, fitFor, sizeOf } from './size'
export {
  APPEARANCE_PRESETS, DEFAULT_APPEARANCE, F6_APPEARANCE, PRESENT_MODES, isPresentMode, readAppearance,
  type Appearance, type Fill, type ObjectRef, type PresentMode, type PresentProps,
} from './types'
