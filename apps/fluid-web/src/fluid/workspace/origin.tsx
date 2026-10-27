/* WHERE A STAGE BLOCK CAME FROM, MARKED ON ITS POST (Stage grouped by post,
 * adm-f3a36808b64f / adm-b859a0e5a423). While a block on a following zone
 * is focused or opened in place (present/Grouped.tsx), the post it came from
 * is marked wherever that post is drawn -- its card in the conversation, the
 * root at the top of a thread, a reply in it -- with a gold edge and an
 * "on Stage · #N" tag. Additive only: a class and a tag laid over the card,
 * never a change to its size, its place or the column's scroll. Nothing is
 * marked for a kept item, nor for a post that is not drawn: a card that is
 * not mounted hears nothing. One zone marks at a time; the last to focus. */

import { useSyncExternalStore } from 'react'
import type { Id } from '../store'

let on: { zone: string; post: Id; number: number | null } | null = null
const heard = new Set<() => void>()
const emit = () => heard.forEach((fn) => fn())
const subscribe = (fn: () => void) => { heard.add(fn); return () => { heard.delete(fn) } }

/** Mark `post` as the origin of what `zone` has focused or opened. */
export function markOnStage(zone: string, post: Id, number: number | null) {
  if (on && on.zone === zone && on.post === post && on.number === number) return
  on = { zone, post, number }
  emit()
}

/** Focus left `zone`: its mark goes (another zone's stays). */
export function clearOnStage(zone: string) {
  if (!on || on.zone !== zone) return
  on = null
  emit()
}

/** The post marked now, for tests and the zone itself. */
export const onStageNow = () => on?.post ?? null

/** Is this post the origin of the Stage's focused block? Its number (or -1
 *  without one) when it is, else null. */
export const useOnStage = (id: Id): number | null =>
  useSyncExternalStore(subscribe, () => (on && on.post === id ? on.number ?? -1 : null))

/** The class a marked card takes. */
export const onStageClass = (n: number | null) => (n === null ? '' : ' fw-on-stage')

/** The tag over a marked card's top edge: positioned, so it moves nothing. */
export function OnStageTag({ n }: { n: number | null }) {
  if (n === null) return null
  return (
    <span className="fw-on-stage-tag" title="What the Stage has focused came from this post">
      on Stage{n >= 0 ? ` · #${n}` : ''}
    </span>
  )
}
