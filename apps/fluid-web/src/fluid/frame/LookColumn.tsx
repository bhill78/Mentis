/* LOOK & BACKGROUND, AS SETTINGS COLUMNS (seam). The Settings panel (the bar's
 * one Settings entry) draws these groups beside its Page / Layouts / Focus
 * columns. The Look workstream fills this in from LookSheet.tsx (light, dark,
 * the system's; the atmosphere / background) and the place's surface look
 * (present/AppearancePicker: Clear, Quiet, Glass, Solid, opacity) and the
 * "objects open over / beside" preference. Until then: nothing. */

import type { IconGroup } from './IconMenu'

export function useLookGroups(): IconGroup[] {
  return []
}
