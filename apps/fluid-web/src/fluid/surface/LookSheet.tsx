/* LOOK, ON ITS OWN (amendment ent-56d18f7b54a5). A surface whose actions are
 * its frame's T2 alone -- a Magnet -- offers Look there (the `settings` verb,
 * group look) as a section's and a window's ⚙ does, and Look opens this: the
 * one shared Look column (workspace/zoneMenu.tsx lookGroup) -- Clear, Quiet,
 * Glass, Solid, opacity and the detail -- anchored at that T2. It is no menu
 * of the surface's own: what it sets is the shared Appearance, kept on the
 * zone as a thread window keeps its (focus/model.ts setThreadLook). */

import { Sheet } from '../frame/Sheet'
import { IconMenu } from '../frame/IconMenu'
import { lookGroup } from '../workspace/zoneMenu'
import { workspace } from '../workspace/place'
import { onPage } from '../focus/page'
import { setThreadLook } from '../focus/model'
import type { Appearance } from '../present/types'

/** Look for zone `zone` on `page`, at `appearance` now (`own`: one of its own
 *  is kept). `resetLabel` says what Back returns to, where that is not the
 *  place's look; `resetWords` is what is said when it does. */
export function LookSheet({ zone, page, name, appearance, own, anchor, onClose, resetLabel, resetWords }: {
  zone: string; page: string; name: string; appearance: Appearance; own: boolean
  anchor: HTMLElement | null; onClose: () => void
  resetLabel?: [string, string]; resetWords?: string
}) {
  const setLook = (a: Appearance | undefined, words?: string) => workspace.edit(onPage((v) => setThreadLook(v, zone, a), page), words)
  const g = lookGroup({
    value: appearance, onChange: (a) => setLook(a),
    reset: { run: () => setLook(undefined, resetWords ?? `${name} takes this place's look again.`), isDefault: !own },
    ...(resetLabel ? { resetLabel } : {}),
  })
  const group = { ...g, summary: [(g.items ?? []).find((it) => it.on)?.label, `${Math.round(appearance.opacity * 100)}%`].filter(Boolean).join(' · ') }
  if (!anchor) return null
  return <Sheet anchor={anchor} onClose={onClose} label={`${name}: look`}>
    <IconMenu groups={[group]} label={`${name} look`} onDone={onClose} layout="accordion" open="look" />
  </Sheet>
}
