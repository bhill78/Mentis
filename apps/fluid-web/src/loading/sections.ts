/* WHICH SECTIONS OF THE PAGE ARE STILL LOADING (timer build, package B; plan
 * adm-4fc92741cf96, T5).
 *
 * Every read already says how it went -- `loading`, `error`, `data` on
 * useApi, a Fluid zone's waiting, failed and addresses -- but nothing said,
 * per section, which parts of the page were still being read and which had
 * finished. Each section now REPORTS what it already holds to this store
 * (`useSectionLoad`, ./index.tsx), and the loader strip and the section's
 * own header read it back. Nothing here fetches or decides anything about a
 * read: it only keeps what each section said, and when.
 *
 *   loading   no answer yet, and one is being read
 *   done      an answer is in hand; shown with a check that fades after
 *             FADE_MS, then no longer listed
 *   failed    the read failed; listed, with Retry, until it is read again
 *
 * A REREAD IS NOT A NEW LOAD. A section that has an answer and is reading
 * again stays as it was, so the strip does not flash on every reread; only a
 * section with nothing to show yet is "loading". A section with no read at
 * all (nothing asked of it) is not listed.
 *
 * Pure: no React, no DOM, and the clock is given, so a test drives it.
 * ------------------------------------------------------------------------ */

export type Phase = 'loading' | 'done' | 'failed'

/** What a section already holds about its read. */
export interface LoadState {
  loading?: boolean
  /** the read's failure: any truthy value, or its words */
  error?: unknown
  /** what was read; null or undefined while there is nothing */
  data?: unknown
  /** read it again */
  retry?: () => void
}

export interface Section {
  id: string
  label: string
  phase: Phase
  /** the failure, in words, when failed */
  error: string | null
  /** when it entered this phase (ms) */
  since: number
  retry?: () => void
}

/** How long a finished section's check stays in the strip. */
export const FADE_MS = 2000

const words = (e: unknown): string | null => {
  if (!e) return null
  if (typeof e === 'string') return e
  if (typeof e === 'object' && 'message' in (e as object)) return String((e as { message: unknown }).message)
  return String(e)
}

/** The phase a section's state reads as, given the phase it was in; null
 *  when there is nothing to list (no read asked of it). */
export function phaseOf(s: LoadState, was?: Phase | null): Phase | null {
  const have = s.data !== null && s.data !== undefined
  if (s.error) return 'failed'
  /* Reading again with an answer in hand: a finished section stays
     finished; one still loading, or retried after failing, is loading. */
  if (s.loading) return have && (was === 'done' || was === null || was === undefined) ? 'done' : 'loading'
  return have ? 'done' : null
}

export interface Sections {
  /** Say what a section holds now. Returns the phase it reads as. */
  report(id: string, label: string, state: LoadState): Phase | null
  /** The section is gone from the page. */
  drop(id: string): void
  phase(id: string): Phase | null
  /** What the strip lists now: every section loading or failed, and every
   *  one done less than FADE_MS ago (`fading`), in the order they first
   *  reported. Empty: the strip is not drawn. */
  shown(): (Section & { fading: boolean })[]
  /** ms until what `shown` lists changes by itself (a check fading out), or
   *  null when nothing will. */
  nextChange(): number | null
  subscribe(fn: () => void): () => void
  version(): number
}

export function createSections(now: () => number = () => Date.now()): Sections {
  const all = new Map<string, Section>()
  const listeners = new Set<() => void>()
  let v = 0
  const tell = () => { v++; listeners.forEach((f) => f()) }
  return {
    report(id, label, state) {
      const had = all.get(id)
      const phase = phaseOf(state, had?.phase ?? null)
      if (phase === null) {
        if (had) { all.delete(id); tell() }
        return null
      }
      const error = phase === 'failed' ? words(state.error) : null
      if (had && had.phase === phase && had.label === label && had.error === error) {
        had.retry = state.retry
        return phase
      }
      /* A section first seen already done (its answer was in hand) is not
         news: it is kept, and its check is never shown. */
      const since = had?.phase === phase ? had.since : !had && phase === 'done' ? -Infinity : now()
      all.set(id, { id, label, phase, error, since, retry: state.retry })
      tell()
      return phase
    },
    drop(id) {
      if (all.delete(id)) tell()
    },
    phase(id) {
      return all.get(id)?.phase ?? null
    },
    shown() {
      const t = now()
      return [...all.values()]
        .filter((s) => s.phase !== 'done' || t - s.since < FADE_MS)
        .map((s) => ({ ...s, fading: s.phase === 'done' }))
    },
    nextChange() {
      const t = now()
      const ends = [...all.values()].filter((s) => s.phase === 'done' && t - s.since < FADE_MS).map((s) => s.since + FADE_MS - t)
      return ends.length ? Math.max(0, Math.min(...ends)) : null
    },
    subscribe(fn) {
      listeners.add(fn)
      return () => { listeners.delete(fn) }
    },
    version: () => v,
  }
}

/** The page's one store. */
export const sections = createSections()
