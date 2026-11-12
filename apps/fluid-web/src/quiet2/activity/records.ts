/* WHAT THE ACTIVITY PANEL READS ABOUT A RUN, A POST AND A CONVERSATION.
 *
 * Every helper here is a view over a read Fluid's store already makes; none
 * asks anything new of the server:
 *   a run          `/fluid/api/runs?ids=` (store.loadRuns / store.runs)
 *   a post         `/fluid/api/posts?ids=` (store.loadPosts / store.posts)
 *   a conversation `/fluid/api/conversations?ids=` (store.loadConversations)
 * and each re-renders on the store's own key for it (`run:`, `post:`,
 * `conv:`), so the change loop (store.follow) keeps them current.
 *
 * A RUN'S STATE IS THE SERVER'S (mentis/operational/runs.py `run_state`), not
 * a reading of it here. Closed by the record: ended (it returned; WS-C: an
 * older server said `completed` for the same thing), recovered (its end was
 * read back), stopped (the session was cancelled; the work stays open),
 * failed, superseded. Open by the record: running, no-event, not-launched,
 * not-running, runtime-ended (returned, its end not recorded yet) and unknown
 * (no process here holds it).
 *
 * A RUN ENDING IS NOT ITS WORK COMPLETING. Whether the work is done is the
 * claim's and reconciliation's to say (the post's status, status/), never
 * the run's: an ended run is said as ended, in a neutral ink. */
import { useEffect, useSyncExternalStore, useCallback } from 'react'
import { read } from '../../api'
import { EXECUTION_MODES, type RunConsent, type RuntimeCapacity, type RuntimeChoice } from '../../composer/execution'
import { availability, EXECUTION_WORDS } from '../../fluid/composer/execmode'
import { consentLine, executionLine, type ConsentRead } from '../../fluid/runs/consent'
import { store, type Id, type Post, type RunItem } from '../../fluid/store'
import { repairText } from '../text'

/** What `/fluid/api/runs` sends beyond the store's own type. */
export type Run = RunItem & { words?: string | null; expectation?: Id | null; source?: string | null }

/** States the record has closed: the run is over. `completed` is an older
 *  server's word for `ended`. */
export const ENDED = new Set(['ended', 'completed', 'recovered', 'stopped', 'failed', 'superseded'])
/** A run that simply returned: nothing more to say of how it ended. */
export const PLAIN_END = new Set(['ended', 'completed'])

/** A run state's word for a row: the server's, except an older server's
 *  `completed`, which meant only that the run returned (WS-C): `ended`. */
export const runStateWord = (state: string) => (state === 'completed' ? 'ended' : state)
/** Of the open states, the ones that are work going on now (Fluid's Home,
 *  sections/activity.tsx RUN_LIVE, with the server's `no-event`). */
export const ACTIVE = new Set(['running', 'no-event', 'active', 'performing'])

/** A run's line: closed runs by their end, open ones by their start. */
export const isEnded = (r: Pick<RunItem, 'state' | 'ended_at'>) => r.ended_at != null || ENDED.has(r.state)

/** "claude (claude-sonnet-5)"; a run that names no model says only its
 *  runtime (Home's RunCard says the same). */
export const runtimeModel = (runtime?: string | null, model?: string | null) =>
  [runtime, model ? `(${model})` : ''].filter(Boolean).join(' ') || null

/** The server's words for a state, without the clock time it ends with
 *  (" · 2026-11-08 21:58:57" or "· 21:58:57"): the row says the time itself. */
export const stateWords = (words: string | null | undefined) =>
  words ? repairText(words).replace(/\s*·\s*(\d{4}-\d{2}-\d{2} )?\d{2}:\d{2}:\d{2}\s*$/, '') : null

const subscribeKey = (key: string) => (fn: () => void) => store.subscribe(key, fn)

/** One run as the store holds it, read if it is not held. */
export function useRun(id: Id | null | undefined): Run | undefined {
  const sub = useCallback((fn: () => void) => (id ? store.subscribe('run:' + id, fn) : () => {}), [id])
  const run = useSyncExternalStore(sub, () => (id ? store.runs.get(id) : undefined)) as Run | undefined
  useEffect(() => { if (id && !store.runs.has(id)) void store.loadRuns([id]).catch(() => {}) }, [id])
  return run
}

/** One post as the store holds it, read if it is not held. */
export function usePost(id: Id | null | undefined): Post | undefined {
  const sub = useCallback((fn: () => void) => (id ? store.subscribe('post:' + id, fn) : () => {}), [id])
  const post = useSyncExternalStore(sub, () => (id ? store.posts.get(id) : undefined))
  useEffect(() => { if (id && !store.posts.has(id)) void store.loadPosts([id]).catch(() => {}) }, [id])
  return post
}

const askedConv = new Set<Id>()
/** A conversation's name as the store holds it, read once if it is not held. */
export function useConvName(id: Id | null | undefined, given?: string | null): string {
  const sub = useCallback((fn: () => void) => (id ? subscribeKey('conv:' + id)(fn) : () => {}), [id])
  const name = useSyncExternalStore(sub, () => (id ? store.conversations.get(id)?.name ?? null : null))
  useEffect(() => {
    if (!id || given || store.conversations.has(id) || askedConv.has(id)) return
    askedConv.add(id)
    void store.loadConversations([id]).catch(() => {})
  }, [id, given])
  return repairText(given || name || '') || (id ? 'A conversation' : 'No conversation')
}

/** A post's own first line, as written: its first text part's first line
 *  that says something, markdown's leading marks dropped. Null where the
 *  post has no text (or is not read yet). Never a summary. */
export function firstLine(p: Post | undefined, max = 160): string | null {
  if (!p || p.deleted) return null
  for (const part of p.parts ?? []) {
    if (typeof part.text !== 'string') continue
    for (const raw of part.text.split('\n')) {
      const line = raw.replace(/^\s*(#{1,6}\s+|[-*>]\s+|\d+[.)]\s+)/, '').replace(/[*_`]{1,3}/g, '').trim()
      if (!line) continue
      const s = repairText(line)
      return s.length > max ? s.slice(0, max - 1).trimEnd() + '…' : s
    }
  }
  return null
}

/* -- a run's Permission and Execution -----------------------------------------
   `GET /api/runs/<run>/consent`: the Permission Mode in force, the Execution
   Mode the run has (selected or the runtime's default, its mechanism and the
   isolation MARS reported), and how its consent is enforced. Said with
   Fluid's own words for them (fluid/runs/consent.ts `consentLine`,
   `executionLine`); the enforcement sentence is the server's, and it is never
   said as enforced unless `enforced` is true. Read once per run while shown;
   an older server that says none of it shows nothing. */

/** The server's enforcement, as `consent.enforcement` carries it. */
export interface Enforcement { by: string | null; enforced: boolean; words: string }

export interface RunModes {
  /** "Permission: Ask for permission", "Execution: Sandboxed (runtime's default) · in a sandbox · …" */
  lines: string[]
  enforcement: Enforcement | null
}

/** What a consent read says of a run's modes, as lines. */
export function runModesOf(c: ConsentRead | null | undefined): RunModes | null {
  if (!c) return null
  const consent = c.consent as (RunConsent & { enforcement?: Enforcement | null }) | null
  const lines = [
    consent ? `Permission: ${consentLine(consent)}` : null,
    c.execution ? executionLine(c.execution) : null,
  ].filter((s): s is string => !!s)
  const e = consent?.enforcement
  const enforcement = e && typeof e.words === 'string' ? { by: e.by ?? null, enforced: e.enforced === true, words: repairText(e.words) } : null
  return lines.length || enforcement ? { lines, enforcement } : null
}

const modesHeld = new Map<Id, RunModes | null>()
const modesAsked = new Set<Id>()
const modesHeard = new Set<() => void>()
let modesVer = 0
const modesSub = (fn: () => void) => { modesHeard.add(fn); return () => { modesHeard.delete(fn) } }

/** A run's Permission and Execution, read once while something shows it. */
export function useRunModes(run: Id | null | undefined): RunModes | null {
  useSyncExternalStore(modesSub, () => modesVer)
  useEffect(() => {
    if (!run || modesAsked.has(run)) return
    modesAsked.add(run)
    void read<ConsentRead>(`/api/runs/${encodeURIComponent(run)}/consent`)
      .then((c) => { modesHeld.set(run, runModesOf(c)) }, () => { modesAsked.delete(run) })
      .then(() => { modesVer++; modesHeard.forEach((fn) => fn()) })
  }, [run])
  return run ? modesHeld.get(run) ?? null : null
}

/* -- a runtime's availability ---------------------------------------------- */

/** WHETHER A RUNTIME CAN TAKE WORK NOW, as `/api/execution` says it: not
 *  installed; installed, with each Execution Mode in the runtime contract's
 *  own state (supported, unsupported, unverified, or temporarily unavailable
 *  -- signed out, its probe failed, its quota exhausted or held -- with the
 *  server's why), in Fluid's words for them (execmode.ts `availability`); and
 *  why its models could not be read. Nothing is assumed of any runtime. */
export function availabilityLines(rt: RuntimeChoice | undefined): { lines: string[]; unavailable: boolean } {
  if (!rt) return { lines: [], unavailable: false }
  if (!rt.present) return { lines: ['Not installed on this machine: it cannot take work here.'], unavailable: true }
  const lines: string[] = []
  const m = rt.execution_modes
  let unavailable = false
  if (m && m.default) {
    const modes = m as Parameters<typeof availability>[0]
    const said = EXECUTION_MODES.map((x) => {
      const can = availability(modes, x)
      if (modes.modes[x]?.state === 'temporarily-unavailable') unavailable = true
      return `${EXECUTION_WORDS[x]}${x === modes.default ? ' (default)' : ''}: ${can.ok ? 'supported' : can.why}`
    })
    lines.push(`Execution: ${said.join(' · ')}`)
  } else lines.push('Execution modes: not reported for this runtime')
  if (rt.models_why_not) lines.push(rt.models_why_not)
  return { lines, unavailable }
}

/* -- Capacity's one-word readings (Mark 2 round 1) --------------------------
   The Capacity tab answers one question on sight -- which runtime can I use,
   and how much of it is left -- so its closed rows carry no prose. The three
   helpers below are the ONLY derivations that presentation makes, and each is
   a reading of something the server already reported, never a new concept.
   They are plain functions so the readings can be asserted without a browser. */

/** Which dot a reading draws: available, cannot run now, not installed, or
 *  not reported at all. Never a claim -- 'unknown' is said, not guessed. */
export type Availability = 'ok' | 'paused' | 'off' | 'unknown'

/** ONE WORD FOR A RUNTIME, derived from `/api/execution` and nothing else:
 *
 *    `present: false`                      -> Not installed
 *    any mode `temporarily-unavailable`    -> Not available now (its why)
 *    otherwise                             -> Available
 *    no catalogue row for this name at all -> Not reported
 *
 *  The last case is a runtime that capacity named and execution did not: what
 *  it could run was never read, which is not the same as it being unavailable,
 *  so it is neither offered as available nor marked as a problem. The four
 *  per-mode states stay distinguishable in `executionModeReadings`, which is
 *  where this word is expanded. */
export function runtimeAvailability(rt: RuntimeChoice | undefined): { word: string; state: Availability; why: string | null } {
  if (!rt) return { word: 'Not reported', state: 'unknown', why: 'Whether this runtime can run was not reported.' }
  if (!rt.present) return { word: 'Not installed', state: 'off', why: 'Not installed on this machine: it cannot take work here.' }
  const m = rt.execution_modes
  if (m && m.default) {
    const held = EXECUTION_MODES.filter((x) => m.modes[x]?.state === 'temporarily-unavailable')
    if (held.length) {
      const why = held.map((x) => m.modes[x]?.why).find((w): w is string => !!w) ?? null
      return { word: 'Not available now', state: 'paused', why }
    }
  }
  return { word: 'Available', state: 'ok', why: null }
}

/** One Execution Mode in ordinary language, for a runtime's expansion. The
 *  state word keeps the server's four states apart; the sentence is the
 *  server's `why` wherever it gave one, and only where it said nothing does a
 *  plain fallback stand in for it. */
export interface ModeReading {
  mode: string
  /** Sandboxed / Unrestricted Host / Container */
  name: string
  /** Available · Not available now · Not verified · Not available · Not reported */
  word: string
  state: Availability
  sentence: string
  isDefault: boolean
}

const MODE_SENTENCE: Record<string, Partial<Record<Availability, string>>> = {
  sandboxed: {
    ok: 'Runs confined by the runtime\'s own sandbox.',
    unknown: 'Mentis cannot confirm it would be isolated.',
    off: 'This runtime does not offer a sandbox.',
  },
  'unrestricted-host': {
    ok: 'Can work directly on this computer. You accept the notice each time you choose it.',
    unknown: 'Mentis cannot confirm what it would reach.',
    off: 'This runtime cannot run outside its sandbox.',
  },
  container: { off: 'Container execution is not supported yet.' },
}

export function executionModeReadings(rt: RuntimeChoice | undefined): ModeReading[] {
  const m = rt?.execution_modes
  if (!rt || !m || !m.default) return []
  return EXECUTION_MODES.map((mode) => {
    const st = m.modes[mode]
    /* CONTAINER IS NEVER AVAILABLE, whatever is reported (execmode.ts
       CONTAINER_WHY): its own sentence says why, and is not the server's. */
    const state: Availability = mode === 'container' ? 'off'
      : !st ? 'unknown'
        : st.state === 'supported' ? 'ok'
          : st.state === 'temporarily-unavailable' ? 'paused'
            : st.state === 'unverified' ? 'unknown' : 'off'
    const word = mode === 'container' ? 'Not available'
      : !st ? 'Not reported'
        : state === 'ok' ? 'Available'
          : state === 'paused' ? 'Not available now'
            : st.state === 'unverified' ? 'Not verified' : 'Not available'
    const given = mode === 'container' ? null : st?.why ?? null
    return {
      mode,
      name: EXECUTION_WORDS[mode],
      word,
      state,
      sentence: given || MODE_SENTENCE[mode]?.[state]
        || (state === 'paused' ? 'It supports this, and cannot run in it now.' : 'The runtime did not say.'),
      isDefault: mode === m.default,
    }
  })
}

/** WHERE A RUNTIME'S FIGURES CAME FROM, in ordinary words, for its expansion:
 *  how old the reading is, and -- said rather than implied -- that a runtime
 *  which reported nothing reported NOTHING, which is not zero. Local
 *  resources are not a quota and say so. */
export function capacityReading(c: RuntimeCapacity | undefined, readWords: string | null): string[] {
  if (!c) return ['This runtime reported no capacity. Nothing was reported: not zero.']
  const lines: string[] = []
  lines.push(c.observed_at ? (readWords ? `Read ${readWords.replace(/^read /, '')}.` : 'Read just now.')
    : 'When it was read was not reported.')
  if (!c.established) lines.push(`Its allowance was not established${c.why_not ? `: ${c.why_not}` : ''}. Nothing was reported: not zero.`)
  else if (c.why_not) lines.push(c.why_not)
  if (c.local) lines.push('It runs on this computer, so it has no allowance: what follows is what its model servers hold right now.')
  return lines
}

/** THE TECHNICAL STRINGS, IN ONE PLACE. Everything the rows and the plain
 *  expansion deliberately do not say, verbatim, behind its own disclosure:
 *  the raw window labels and the reported `used_percent` (not the derived
 *  remainder), the observation time, each mode's state, mechanism and
 *  enforcement sentence, and why a catalogue could not be read. */
export function capacityDiagnostics(name: string, c: RuntimeCapacity | undefined, rt: RuntimeChoice | undefined): string {
  const out: string[] = [`runtime ${name}${rt?.version ? ' ' + rt.version : ''}${rt && !rt.present ? ' (not present)' : ''}`]
  if (!c) out.push('capacity not reported')
  else {
    out.push(`established ${c.established}`)
    if (c.plan) out.push(`plan ${c.plan}`)
    if (c.why_not) out.push(`why_not ${c.why_not}`)
    for (const w of c.windows) {
      out.push(`window ${w.label}${w.group ? ` group ${w.group}` : ''}`)
      out.push(`  used_percent ${w.used_fraction === null ? 'not reported' : Math.round(w.used_fraction * 100)}`)
      if (w.resets_at) out.push(`  resets_at ${new Date(w.resets_at * 1000).toISOString().slice(0, 16).replace('T', ' ')}`)
    }
    out.push(`observed_at ${c.observed_at ? new Date(c.observed_at * 1000).toISOString().slice(0, 16).replace('T', ' ') : 'not reported'}`)
  }
  const m = rt?.execution_modes
  if (m && m.default) {
    for (const mode of EXECUTION_MODES) {
      const st = m.modes[mode]
      out.push(`${mode} ${st?.state ?? 'not reported'}${mode === m.default ? ' (default)' : ''}`)
      if (st?.mechanism) out.push(`  mechanism ${st.mechanism}`)
      if (st?.permission_enforcement) out.push(`  enforcement ${st.permission_enforcement}`)
      if (st?.why) out.push(`  why ${st.why}`)
    }
  } else if (rt) out.push('execution_modes not reported')
  if (rt?.models_why_not) out.push(`models_why_not ${rt.models_why_not}`)
  return out.join('\n')
}
