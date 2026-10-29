import { useEffect, useState } from 'react'
import { useApi } from '../api'

/* ------------------------------------------------------------------------ *
 * WHAT THIS MACHINE CAN ACTUALLY RUN.
 *
 * Discovered, not configured, and not cached across a reload: a runtime can
 * be installed or removed between one sitting and the next, and a picker that
 * offers something no longer present is worse than one that is briefly empty.
 *
 * A runtime that is PRESENT but has no machine-readable model catalogue is
 * not the same as one with no models. The first is Unknown, the second is
 * Empty, and `models_why_not` is how the distinction survives to the picker.
 * ------------------------------------------------------------------------ */

export interface ModelChoice {
  slug: string
  name: string
  efforts: string[]
  default_effort: string | null
  locality: string
  /** WHO SERVES IT, which is not who HARNESSES it. `null` means the runtime
   *  serves the model itself — the ordinary hosted case, and a real answer
   *  rather than a missing one. Never inferred from the model's name. */
  provider: string | null
  /** the names that reach this model, where the runtime has them (Claude's
   *  aliases: `opus`, `default`) */
  aliases?: string[]
  /** what this catalogue is and is not, as the runtime's adapter says it */
  catalogue?: string | null
}

/** `llama3.2:latest · Ollama via Codex · local`, or the hosted equivalent with
 *  no clutter.
 *
 *  WHY THIS EXISTS. The picker is runtime-first, so a model served by Ollama
 *  was listed under the heading `codex` with only a small `local` note — and
 *  "Codex" reads as the thing that answered rather than the thing that ran it.
 *  An owner spent twenty minutes believing an experiment was local when it was
 *  not. Four facts, and the one that was missing is the provider. */
export const modelSays = (m: ModelChoice, runtime: string): string => {
  const pretty = (s: string) =>
    ({ codex: 'Codex', claude: 'Claude', antigravity: 'Antigravity',
       ollama: 'Ollama', lmstudio: 'LM Studio' })[s] ?? s
  const via = m.provider ? `${pretty(m.provider)} via ${pretty(runtime)}` : pretty(runtime)
  return m.locality && m.locality !== 'unknown' ? `${via} · ${m.locality}` : via
}

export interface RuntimeChoice {
  kind: string
  present: boolean
  version: string | null
  capabilities: string[]
  notes: string[]
  models: ModelChoice[]
  models_why_not?: string
}

export interface LiveInstance {
  name: string
  instance: string
  runtime: string
  /** as the runtime reported it, where it has reported one yet */
  model: string | null
  /** where this run belongs, from the act that started it */
  conversation: string | null
  turn: string | null
  actor: string | null
  liveness: string
}

/** THE CONSENT IN FORCE ON A RUN, as every run row carries it: the mode
 *  and the server's words for it, the task's workspaces and routine
 *  categories, the tools allowed for this run only, where it came from, and
 *  what MARS reported it could apply (`enforced_by: "none"` is a runtime that
 *  neither asks nor confines). Absent from a server that does not say. */
export interface RunConsent {
  mode: 'ask' | 'task' | 'deny'
  label?: string | null
  workspaces?: string[]
  categories?: string[]
  tools?: string[]
  source?: 'request' | 'owner-changed' | 'inherited' | 'none'
  applied?: { enforced_by: 'client' | 'sandbox+client' | 'sandbox' | 'none'; workspaces?: string[]; mode?: string } | null
}

/** ONE RUN, as `/api/working` words it. A run is its recorded start, never a
 *  session handle; `words` is the server's one sentence for it, with the time
 *  of the observation that supports it already in it. Nothing here re-derives
 *  a state -- the surface shows what it is given. */
export interface RunRow {
  run: string
  instance: string | null
  runtime: string | null
  name: string
  actor: string | null
  conversation: string | null
  turn: string | null
  expectation: string | null
  /** completed | failed | unknown | not-launched | no-event | tool-running |
   *  helper-outstanding | model-outstanding | runtime-ended */
  state: string
  words: string
  /** when the supporting observation was made */
  at: number | null
  /** recorded (an act says so) · runtime (this process observed it) · unknown */
  source: 'recorded' | 'runtime' | 'unknown'
  held_here: boolean
  model_requested: string | null
  /** the Persona it wore and the Task Gravity in force, from the record
   *  (`asked_with`); absent from a server that does not say */
  persona?: string | null
  persona_name?: string | null
  follow_up?: 'ask' | 'unrestricted' | { depth: number } | null
  generation?: number | null
  /** the execution consent in force (docs/run-consent.md §2) */
  consent?: RunConsent | null
  /** Mentis-delegated work this run's request still waits on, from the record */
  delegated: { outstanding: string[]; words: string; source: string } | null
}

export interface Working {
  open: RunRow[]
  ended: RunRow[]
  why_not?: string | null
  observed_at?: number
}

export interface ExecutionInfo {
  runtimes: RuntimeChoice[]
  workspace: string
  /** verified against this machine; absent if the service could not be asked */
  live?: LiveInstance[]
  live_why_not?: string
}

/** What this machine can run -- ASKED ONLY WHEN SOMETHING IS GOING TO SHOW IT.
 *
 *  THIS IS NOT A CHEAP READ AND NEVER WAS. `/api/execution` discovers runtimes
 *  by looking for real executables and then asks each present one for its
 *  catalogue, which means subprocesses. Measured on the live machine: 5.3s and
 *  6.8s for a single call, and 21.7s when two ran at once against a busy
 *  server. `useWorking` below already says in its own words that polling this
 *  "would be absurd".
 *
 *  WHAT IT USED TO DO. It was called unconditionally whenever a Composer
 *  mounted. Four surfaces mount one -- Awaited, BrainHome, ConversationSurface,
 *  ThreadRail -- and `useApi` holds no shared cache and does not deduplicate,
 *  so every mounted Composer asked this machine what it could run. Measured on
 *  a cold conversation load: 2 calls, 41.4s of request time between them, the
 *  largest single cost on the page. Nobody had opened a picker.
 *
 *  SO THE CALLER SAYS WHEN IT IS WANTED. `want` false makes no request at all
 *  -- `useApi` treats a null path as "ask nothing" -- and the data stays null,
 *  which both consumers already render: the Picker says "asking this machine
 *  what it can run" and the Dispatch panel has its own loading branch. They
 *  were written for this to arrive late.
 *
 *  NO CACHE, DELIBERATELY. A process-lifetime cache would make installing a
 *  runtime, or a catalogue changing, invisible until reload, and it would need
 *  invalidation machinery to be honest about it. There is none here: the
 *  request happens when a picker is first opened, which is strictly LATER than
 *  page load and so strictly fresher than what this replaced. */
export const useExecution = (want = true) =>
  useApi<ExecutionInfo>(want ? '/api/execution' : null, { live: false })

/** Only what could actually take work. An absent runtime stays in the data so
 *  a reader can be told it is absent, but it is never offered as a choice. */
export const runnable = (e: ExecutionInfo | null) =>
  (e?.runtimes ?? []).filter((r) => r.present)

/** Models that run on this machine, whichever runtime reports them.
 *
 *  LOCALITY IS DISCOVERED, NOT LISTED HERE. A model says where its compute
 *  happens and this groups by that answer; nothing in the interface decides
 *  that a particular slug is local. It is a fact about execution and never a
 *  claim about capability -- a local model is not assumed weaker, and
 *  selection is forbidden from reasoning about locality at all. */
export const localModels = (e: ExecutionInfo | null) =>
  runnable(e).flatMap((r) =>
    r.models.filter((m) => m.locality === 'local').map((m) => ({ runtime: r.kind, model: m })),
  )

/** Names with something actually running on this machine right now. A name
 *  missing from this set has nothing running -- which is NOT a claim that
 *  whoever bears it is idle, available or willing. */
export const runningNames = (e: ExecutionInfo | null) =>
  new Set((e?.live ?? []).map((l) => l.name.toLowerCase()))

/* ---- capacity, asked for separately ------------------------------------- *
 * OBSERVING IT COSTS SECONDS. Reading rate-limit events and rollout session
 * files for three runtimes was measured at seven, which is why it is not part
 * of the execution reading the composer takes when it mounts. It is fetched
 * only once somebody actually looks at runtimes, and the rows render fine
 * without it.
 * ------------------------------------------------------------------------ */

export interface CapacityWindow {
  label: string
  used_fraction: number | null
  resets_at: number | null
  /** the pool this window belongs to, as the runtime names it; null where
   *  the runtime has one pool (Claude, Codex) */
  group?: string | null
}

export interface RuntimeCapacity {
  established: boolean
  plan: string | null
  why_not: string | null
  windows: CapacityWindow[]
  /** when the runtime was asked, in epoch seconds -- a reading may be reused */
  observed_at?: number
  /** which model draws on which group; null where the runtime's own grouping
   *  does not place it. Only present for a runtime whose windows have groups. */
  model_groups?: Record<string, string | null>
  /** A local-model runtime's resources as its model servers report them now
   *  (MARS `local`). Not quota: never a window, never a percentage of a plan. */
  local?: LocalResources
}

export interface LocalModel {
  id: string
  loaded: boolean
  sizeBytes?: number | null
  contextLength?: number | null
  contextLoaded?: number | null
  memoryBytes?: number | null
  vramBytes?: number | null
  unloadsAt?: number | null
}

export interface LocalServer {
  name: string
  url: string
  reachable: boolean
  version?: string | null
  why?: string
  models?: LocalModel[]
  loadedMemoryBytes?: number | null
  loadedVramBytes?: number | null
  unavailable?: Record<string, string>
}

export interface LocalResources {
  servers: LocalServer[]
  /** MARS's own local turns running now; null when MARS did not say */
  runningTurns: number | null
  /** each figure no server exposes, and why: said, never guessed */
  unavailable: Record<string, string>
}

const SERVER_NAMES: Record<string, string> = { ollama: 'Ollama', lmstudio: 'LM Studio' }
export const serverName = (s: LocalServer): string => SERVER_NAMES[s.name] ?? s.name

/** Bytes as people read memory: one decimal in GB, whole MB below that. */
export const bytesSaid = (n: number): string =>
  n >= 1e9 ? `${(n / 1e9).toFixed(1)} GB` : `${Math.max(1, Math.round(n / 1e6))} MB`

/** One server in a line: what it has, what is loaded and what that holds.
 *  A figure the server did not give is left out of the line, not shown as 0. */
export function localServerSays(s: LocalServer): string {
  const name = serverName(s)
  if (!s.reachable) return `${name}: not running`
  const models = s.models ?? []
  const loaded = models.filter((m) => m.loaded)
  const parts = [`${loaded.length} of ${models.length} model${models.length === 1 ? '' : 's'} loaded`]
  if (typeof s.loadedMemoryBytes === 'number' && loaded.length) {
    parts.push(bytesSaid(s.loadedMemoryBytes)
      + (typeof s.loadedVramBytes === 'number' ? ` (${bytesSaid(s.loadedVramBytes)} VRAM)` : ''))
  }
  return `${name}${s.version ? ' ' + s.version : ''}: ${parts.join(', ')}`
}

/** A loaded or installed model in a line: memory, VRAM, context in use of the
 *  model's maximum. Missing figures are omitted. */
export function localModelSays(m: LocalModel): string {
  const bits: string[] = []
  if (typeof m.memoryBytes === 'number') bits.push(bytesSaid(m.memoryBytes)
    + (typeof m.vramBytes === 'number' ? `, ${bytesSaid(m.vramBytes)} VRAM` : ''))
  if (typeof m.contextLoaded === 'number' && typeof m.contextLength === 'number')
    bits.push(`context ${m.contextLoaded.toLocaleString()} of ${m.contextLength.toLocaleString()}`)
  else if (typeof m.contextLength === 'number') bits.push(`context up to ${m.contextLength.toLocaleString()}`)
  return bits.length ? `${m.id}: ${bits.join(' · ')}` : m.id
}

/** The windows of one group only, as a reading of its own.
 *
 *  A MODEL SEES ITS OWN GROUP AND NO OTHER. Antigravity's quota belongs to
 *  groups of models, so a model's row carries the meters of the group agy
 *  placed it in -- and a model agy did not place gets none, rather than a
 *  neighbour's. */
export const capacityOfGroup = (
  c: RuntimeCapacity | undefined,
  group: string,
): RuntimeCapacity | undefined =>
  c && { ...c, windows: c.windows.filter((w) => w.group === group) }

/** Which group a model draws on, or why it has none. Undefined when this
 *  runtime has no groups at all (or was not read).
 *
 *  Two different absences, said differently: agy's own description of its
 *  groups names this model in none of them, or the server never matched the
 *  model at all (its catalogue could not be listed when quota was read). */
export function modelGroup(
  c: RuntimeCapacity | undefined,
  slug: string,
): { group: string } | { why: string } | undefined {
  if (!c?.established || !c.windows.some((w) => w.group)) return undefined
  const g = c.model_groups?.[slug]
  if (g) return { group: g }
  return {
    why: g === null ? 'in no quota group agy reported' : 'quota group not matched',
  }
}

/** How old a reading is, in words, once that is worth saying. A reading is
 *  reused for a while rather than asked for every time the picker opens, and
 *  Codex's is read from its last session file, which may be days old. */
export const readAgo = (at: number | undefined, now = Date.now() / 1000): string | null => {
  if (!at) return null
  const s = Math.max(0, now - at)
  if (s < 60) return null
  const d = Math.floor(s / 86400)
  const h = Math.floor((s % 86400) / 3600)
  const m = Math.floor((s % 3600) / 60)
  // Single unit, deliberately. The two-unit form `resetsIn` uses understates
  // nothing, but this wording is what the capacity acceptance evidence pins
  // ("read 4d ago"), and it is agy/codex staleness, not a countdown. Reviewed
  // 2026-10-01: coarsening can flatter freshness by up to one unit (1h 59m
  // reads as "1h ago"). Left as-is rather than silently re-cutting an agreed
  // wording; if it should change, the acceptance criterion changes with it.
  return `read ${d > 0 ? `${d}d ago` : h > 0 ? `${h}h ago` : `${m}m ago`}`
}

export const useCapacity = (wanted: boolean) =>
  useApi<{ capacity: Record<string, RuntimeCapacity> }>(
    wanted ? '/api/capacity' : null, { live: false })

/** What a runtime has left, in its own units, as words.
 *
 *  REMAINING IS DERIVED, NOT RELABELLED. Both providers report UTILISATION of
 *  a BOUNDED window that resets: Claude's `utilization` over five_hour and
 *  seven_day, Codex's `used_percent` over a window of a stated length, each
 *  with its own `resets_at`. For a bounded allowance that refills, `1 - used`
 *  is arithmetic on the provider's own quantity, not a rename of it -- which
 *  is why it is only done where `used_fraction` was actually established and
 *  the window has not passed its reset. The reported figure is kept beside it
 *  so nothing is lost in the conversion.
 *
 *  STILL NOT BLENDED AND STILL NOT SCORED. Two windows are two promises of
 *  different lengths; there is no single number that honestly stands for
 *  both, so both are said. A runtime that establishes nothing says nothing
 *  here -- not zero, not full.
 */
export interface CapacityWords {
  /** short enough to sit on a picker row */
  short: string
  /** what the provider actually reported, for the row's title */
  reported: string | null
}

/** A window's name as a length: `five_hour` is 5h, Codex's
 *  `primary:10080min` is 7d. A label that states no length is kept as said. */
export const windowName = (label: string) => {
  const mins = /(\d+)\s*min$/.exec(label)?.[1]
  if (mins) {
    const m = Number(mins)
    return m % 1440 === 0 ? `${m / 1440}d` : m % 60 === 0 ? `${m / 60}h` : `${m}m`
  }
  return label
    .replace(/_/g, ' ')
    .replace(/^five hour$/, '5h')
    .replace(/^seven day$/, '7d')
}

/** How long until a window resets, in words; null when not reported. */
export const resetsIn = (at: number | null, now = Date.now() / 1000): string | null => {
  if (!at) return null
  const s = Math.max(0, at - now)
  const d = Math.floor(s / 86400)
  const h = Math.floor((s % 86400) / 3600)
  const m = Math.floor((s % 3600) / 60)
  return d > 0 ? `${d}d ${h}h` : h > 0 ? `${h}h ${m}m` : `${m}m`
}

/** One window as a meter can draw it.
 *
 *  `left` IS ONLY SAID WHILE IT CAN BE TRUE. A window whose reset has passed
 *  since the provider reported it has refilled by some amount nobody
 *  measured, so it is `stale` and carries no figure -- never the old one. */
export interface CapacityMeter {
  name: string
  label: string
  /** the group the window belongs to, where the runtime has groups */
  group: string | null
  left: number | null
  stale: boolean
  resets: string | null
  /** plenty | low | nearly-out: a reading of `left`, for colour only */
  level: 'plenty' | 'low' | 'nearly-out' | null
}

export function capacityMeters(
  c: RuntimeCapacity | undefined,
  now = Date.now() / 1000,
): CapacityMeter[] {
  if (!c || !c.established) return []
  return c.windows
    .filter((w) => w.used_fraction !== null)
    .map((w) => {
      const stale = !!w.resets_at && w.resets_at <= now
      const left = stale ? null : Math.max(0, Math.min(1, 1 - (w.used_fraction as number)))
      return {
        name: windowName(w.label),
        label: w.label,
        group: w.group ?? null,
        left,
        stale,
        resets: stale ? null : resetsIn(w.resets_at, now),
        level: left === null ? null : left >= 0.5 ? 'plenty' : left >= 0.2 ? 'low' : 'nearly-out',
      }
    })
}

export function capacityWords(
  c: RuntimeCapacity | undefined, now = Date.now() / 1000,
): CapacityWords | null {
  if (!c || !c.established) return null
  const usable = c.windows.filter((w) => w.used_fraction !== null
    && Number.isFinite(w.used_fraction) && w.used_fraction >= 0 && w.used_fraction <= 1
    && (w.resets_at === null || w.resets_at > now))
  if (usable.length === 0) return c.plan ? { short: `plan ${c.plan}`, reported: null } : null
  const of = (w: CapacityWindow) => (w.group ? `${w.group} ` : '')
  return {
    short: usable
      .map((w) => `${of(w)}${Math.round((1 - (w.used_fraction as number)) * 100)}% ${windowName(w.label)} left`)
      .join(' · '),
    reported: usable
      .map((w) => `${Math.round((w.used_fraction as number) * 100)}% of ${of(w)}${w.label.replace(/_/g, ' ')} used`)
      .join(' · '),
  }
}


/** What is running now, asked repeatedly but not often.
 *
 *  SEPARATE AND CHEAP. `/api/execution` discovers runtimes and asks each for
 *  its catalogue -- measured at three and a half seconds -- so polling it to
 *  animate an indicator would be absurd. This route is a dictionary lookup
 *  and a pass over acts, measured under 10ms.
 *
 *  THE INTERVAL IS DELIBERATELY SLACK. A run takes seconds at least, so
 *  four-second resolution is enough to watch one begin and end; anything
 *  faster would be spending requests to make a dot feel livelier. It also
 *  stops entirely when the tab is hidden, because nobody is watching.
 */
export function useWorking(every = 4000, on = true) {
  // `on` false asks nothing at all: the Activity surface is closed.
  return usePolled<Working>(on ? '/api/working' : null, every)
}

/** HOW MANY RUNS ARE OPEN, AND NOTHING ELSE.
 *
 *  The closed Activity surface and the briefing's "N active runs" want a
 *  number, so they ask for a number: the same open runs `/api/working` lists,
 *  counted, with no row worded and no ended run read. */
export function useWorkingCount(every = 4000) {
  return usePolled<{ open: number | null; counted: boolean; why_not?: string }>(
    '/api/working?count=1',
    every,
  )
}

function usePolled<T>(path: string | null, every: number) {
  /* LIVE MOVEMENT REREADS THIS AT MOST ONCE PER POLL INTERVAL. It is already
     reread every `every` while visible, and that poll is a read like any
     other, so a live move between polls is answered by the next one at the
     latest; hearing every stream event as well only added requests. */
  const state = useApi<T>(path, { runs: true, runsSpacing: every })
  const { reload } = state
  const [tick, setTick] = useState(0)
  useEffect(() => {
    if (!path) return
    const id = window.setInterval(() => {
      if (document.visibilityState === 'visible') setTick((n) => n + 1)
    }, every)
    return () => window.clearInterval(id)
  }, [every, path])
  useEffect(() => {
    if (tick) reload()
  }, [tick, reload])
  return state
}
