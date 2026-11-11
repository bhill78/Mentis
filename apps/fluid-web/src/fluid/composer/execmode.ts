/* EXECUTION MODE, SAID THE SAME WAY EVERYWHERE (round 3).
 *
 * Two controls on one addressee, and neither changes the other:
 *   Permission  which operations need asking -- the existing consent modes
 *               (runs/consent.ts), unchanged in meaning and in what is sent.
 *   Execution   the technical environment the runtime runs in: Sandboxed,
 *               Unrestricted Host, or Container (not available yet).
 *
 * WHAT A RUNTIME CAN DO IS THE SERVER'S. The runtime catalogue
 * (`/api/execution`) carries each runtime's `execution_modes` from MARS's
 * contract; nothing here decides a runtime supports a mode. A catalogue
 * without them is a server without Execution Mode, and then there is no
 * control and nothing is sent -- the runtime's default, as before. */

import { executionSpec, type Addressee } from '../../composer/draft'
import type { ExecutionInfo, ExecutionMode, ExecutionModeState, ExecutionModes } from '../../composer/execution'

export const EXECUTION_WORDS: Record<ExecutionMode, string> = {
  sandboxed: 'Sandboxed',
  'unrestricted-host': 'Unrestricted Host',
  container: 'Container',
}

/** The chip's word for each. */
export const EXECUTION_SHORT: Record<ExecutionMode, string> = {
  sandboxed: 'sandboxed',
  'unrestricted-host': 'host',
  container: 'container',
}

export const EXECUTION_TIP = 'Where the runtime runs: confined by its sandbox, or directly on this machine. '
  + 'Independent of Permission, which says which operations need asking.'

/** Container is never offered: it is not available yet, whatever is reported. */
export const CONTAINER_WHY = 'not available yet'

/** The runtime's Execution Modes, or null where the server does not say
 *  (an older server, or no runtime known yet). */
export function modesFor(info: ExecutionInfo | null | undefined, runtime: string | null | undefined): ExecutionModes | null {
  if (!runtime) return null
  const modes = info?.runtimes.find((r) => r.kind === runtime)?.execution_modes ?? null
  // A server that holds no MARS report for this runtime sends `default: null`: treated as
  // not reported, so no Execution control is offered and nothing is sent.
  return modes && modes.default ? (modes as ExecutionModes) : null
}

/** Whether a mode may be chosen on this runtime, and if not, why. */
export function availability(modes: ExecutionModes, mode: ExecutionMode): { ok: boolean; why: string | null } {
  if (mode === 'container') return { ok: false, why: CONTAINER_WHY }
  const st = modes.modes[mode]
  if (!st) return { ok: false, why: 'not reported for this runtime' }
  if (st.state === 'supported') return { ok: true, why: null }
  return { ok: false, why: st.why ?? (st.state === 'unverified' ? 'not verified on this runtime' : 'not supported by this runtime') }
}

export interface EffectiveExecution {
  mode: ExecutionMode
  source: 'selected' | 'runtime-default'
  state: ExecutionModeState | null
}

/** WHAT WILL APPLY: the mode the dispatch carries (`executionSpec`, so an
 *  unaccepted Unrestricted Host is never said as chosen), else the runtime's
 *  default. Null when neither is known. */
export function effectiveExecution(a: Addressee, runtime: string | null | undefined,
  info: ExecutionInfo | null | undefined): EffectiveExecution | null {
  const modes = modesFor(info, runtime)
  const chosen = executionSpec(a).execution_mode
  if (chosen) return { mode: chosen, source: 'selected', state: modes?.modes[chosen] ?? null }
  if (!modes) return null
  return { mode: modes.default, source: 'runtime-default', state: modes.modes[modes.default] ?? null }
}

/** Permission Mode in the chip's few words. Always said for work: it is the
 *  effective mode, and "ask" is one. */
export const permissionShort = (mode?: string | null): string =>
  mode === 'task' ? 'routine' : mode === 'all' ? 'allow all' : mode === 'deny' ? 'never waits' : 'ask'

/** "routine · host": the effective Permission Mode and, where it is known,
 *  the effective Execution Mode. */
export function modesWords(a: Addressee, runtime: string | null | undefined, info?: ExecutionInfo | null): string {
  const e = effectiveExecution(a, runtime, info)
  return [permissionShort(a.consent?.mode), e ? EXECUTION_SHORT[e.mode] : null].filter(Boolean).join(' · ')
}

/** HOW PERMISSION IS ENFORCED, said beside the chip only where it matters:
 *  outside the sandbox, where a runtime may not ask at all. The sentence is
 *  the server's, never composed here. */
export function enforcementNote(a: Addressee, runtime: string | null | undefined, info?: ExecutionInfo | null): string | null {
  const e = effectiveExecution(a, runtime, info)
  return e && e.mode === 'unrestricted-host' ? e.state?.permission_enforcement ?? null : null
}

/** Whether the Unrestricted Host accepted on this addressee is the notice the
 *  server shows now. */
export const ackIsCurrent = (a: Addressee, info: ExecutionInfo | null | undefined): boolean =>
  !!a.executionAck && a.executionAck === info?.unrestricted_host_notice?.id

/** Choosing a mode that needs no notice: the runtime's default is "nothing
 *  sent", anything else is sent. Unrestricted Host is only ever set by
 *  `acceptUnrestricted`. */
export function chooseExecution(a: Addressee, mode: ExecutionMode, modes: ExecutionModes): Addressee {
  const { executionMode: _m, executionAck: _k, ...rest } = a
  return mode === modes.default ? rest : { ...rest, executionMode: mode }
}

/** Accept: the mode and the notice it was accepted under, together. */
export const acceptUnrestricted = (a: Addressee, noticeId: string): Addressee =>
  ({ ...a, executionMode: 'unrestricted-host', executionAck: noticeId })

/** THE RUNTIME CHANGED (or became the declared default, or unknown): a mode
 *  the new runtime does not support is CLEARED, and the reason is returned to
 *  be shown -- never kept and sent for the server to refuse, and never
 *  silently swapped for another. */
export function fitExecution(a: Addressee, runtime: string | null | undefined,
  info: ExecutionInfo | null | undefined): { who: Addressee; cleared: string | null } {
  if (!a.executionMode) return { who: a, cleared: null }
  const modes = modesFor(info, runtime)
  const said = EXECUTION_WORDS[a.executionMode]
  if (modes && availability(modes, a.executionMode).ok) return { who: a, cleared: null }
  const { executionMode: _m, executionAck: _k, ...rest } = a
  const why = modes ? availability(modes, a.executionMode).why : 'its Execution Modes are not known'
  const back = modes ? `${EXECUTION_WORDS[modes.default]}, its default` : "the runtime's default"
  return { who: rest, cleared: `${said} cleared: on ${runtime ?? 'a runtime Mentis picks'}, ${why}. Now ${back}.` }
}
