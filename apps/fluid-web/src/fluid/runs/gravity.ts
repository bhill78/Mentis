/* TASK GRAVITY, SAID THE SAME WAY EVERYWHERE (operating-model §6).
 *
 * The values are Mark IV's, unchanged, as the server records them on a
 * request (`detail.follow_up`): absent or "ask", `{depth: N}`, "unrestricted".
 * The composer's toggle, a run's line and the side-work panel all word them
 * here, so the setting asked with and the setting shown cannot drift apart.
 *
 * A RUN'S LINE IS WHO, AS WHAT, WHERE AND HOW FAR: Participant · Persona ·
 * runtime · Task Gravity, read from the run's own record (`asked_with`,
 * mentis/operational/runs.py). What the record does not say is left out,
 * never guessed: a run nobody gave a Persona ran as themselves. A Persona the
 * run wore because it is the participant's designated one, not because the
 * owner chose it (the owner's ruling, 2026-10-29: direct addressing uses the
 * designated Persona unless another is chosen), is said "(designated)" when
 * the record says so (`persona_from`). */

import type { GravityItem, Gravity } from '../../api'
import { consentShort } from './consent'

export type FollowUp = 'ask' | 'unrestricted' | { depth: number }

/** The composer's full explanation, Mark IV's words. */
export const GRAVITY_TIP = 'Ask afterward: it is recorded and put to you when this work is finished. '
  + 'A depth allows that many generations of independently pursued discovery; work necessary to this request does not count. '
  + 'Permission allows pursuit; it never starts anything by itself.'

/** The composer's draft value (draft.ts `followUp`) as the record's. */
export const followUpOf = (draft?: number | 'unrestricted'): FollowUp =>
  draft === undefined ? 'ask' : draft === 'unrestricted' ? 'unrestricted' : { depth: draft }

/** The setting in words. Anything unreadable is the default, as the server
 *  reads it (`follow_up_of`): asking is never widened by a bad value. */
export function gravityWords(f: FollowUp | null | undefined): string {
  if (f === 'unrestricted') return 'May pursue side work freely'
  if (f && typeof f === 'object' && Number.isInteger(f.depth) && f.depth >= 1)
    return `May pursue side work ${f.depth} generation${f.depth === 1 ? '' : 's'} deep`
  return 'Asks before pursuing side work'
}

export interface RunAsked {
  participant_name?: string | null
  persona?: string | null
  persona_name?: string | null
  /** why it wore that Persona, where the record says: `chosen`,
   *  `designation` or `intake` (designated), `none-chosen`, `unresolved` */
  persona_from?: string | null
  runtime?: string | null
  follow_up?: FollowUp | null
  generation?: number | null
  consent?: { mode?: string | null } | null
}

/** Participant · Persona · runtime · Task Gravity, for one run. A run pursued
 *  as side work says which generation of discovery it is; a run under a
 *  consent other than asking says so last, in its few words. */
export function runLine(r: RunAsked): string {
  const gravity = gravityWords(r.follow_up) + (r.generation ? ` (this is generation ${r.generation})` : '')
  const designated = r.persona_from === 'designation' || r.persona_from === 'intake'
  const persona = r.persona ? (r.persona_name || r.persona) + (designated ? ' (designated)' : '') : null
  return [r.participant_name?.replace(/^@/, ''), persona, r.runtime, gravity, consentShort(r.consent?.mode)]
    .filter(Boolean).join(' · ')
}

/** One deferred finding's head: who found it and how many generations below
 *  the original request it would be. */
export const foundWords = (x: GravityItem): string =>
  `${x.by.replace(/^@/, '')} · generation ${x.depth_from_root}`

/** Whether the trunk's deferred findings are to be put to the owner now:
 *  the server's answer (`reconsideration`), in words. */
export function reconsiderWords(g: Gravity): string | null {
  const r = g.reconsideration
  if (!r) return null
  if (r.due_for_reconsideration) return 'The work is finished: these are due for reconsideration.'
  if (!r.trunk.complete) return 'Put to you when this work is finished.'
  return null
}
