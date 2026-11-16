/* PLAIN WORDS FOR A RECORD'S STANDING, checked without a browser
 * (`tests/brain_record_unit.ts`): DESIGN-r2.md "The record, at rest", the
 * Ladder→plain-words table (`data.ts`'s `plainStandingLabel`) extended here
 * with the one case that table cannot say alone -- a hypothesis that is
 * merely `recorded` is "Not settled", not "reaches agents as experience" --
 * and the subline ("who adopted it and when, and its scope"), the standing
 * dot's four appearances, a history act's words, and the fold-toggle a
 * section's disclosure button uses. Pure; `BrainRecord.tsx` only renders
 * what these return. */
import { plainStandingLabel } from './data'

/** The alias a reader sees: dropped leading '@', the same as Mark 2's own
 *  bylines and `Surface.tsx`'s `who` -- an identity Mentis already names,
 *  said once in its plain form. */
export function stripAt(alias: string | null | undefined, fallback = ''): string {
  const a = (alias ?? '').trim()
  return a ? a.replace(/^@/, '') : fallback
}

/** A moment as the reading column gives a date with no time: "Nov 12". */
export function dateOnly(ts: number | null | undefined): string {
  if (!ts) return ''
  return new Date(ts * 1000).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}

/** The standing dot beside the plain-language line: solid (in effect),
 *  `ask` (waiting on the owner), `gone` (was in effect, no longer, dashed),
 *  or `off` (recorded but never asked for, hollow). */
export type StandingDot = '' | 'ask' | 'off' | 'gone'
export function standingDot(status: string): StandingDot {
  switch (status) {
    case 'adopted': return ''
    case 'adoption_requested': return 'ask'
    case 'declined':
    case 'superseded':
    case 'ended':
    case 'retired':
      return 'gone'
    default: return 'off'
  }
}

/** The standing sentence, Kind-aware: a `hypothesis` merely `recorded` is
 *  "Not settled" (DESIGN-r2.md's table, the one row `plainStandingLabel`
 *  cannot say without knowing the Kind). Every other Kind and status is
 *  `plainStandingLabel`'s own 2-argument mapping, unchanged. */
export function standingSentence(kind: string, status: string, governs: boolean): string {
  if (kind === 'hypothesis' && status === 'recorded') return 'Not settled.'
  return plainStandingLabel(status, governs)
}

/** The standing line for a record asking the owner a decision: the one
 *  sentence `plainStandingLabel` leaves generic because it does not know
 *  who asked. */
export function proposedSentence(byAlias: string | null | undefined, by: string | null | undefined): string {
  return `Not in effect — proposed by ${stripAt(byAlias ?? by, 'somebody')}, waiting for your decision.`
}

/** "Under that, one small line: who adopted it and when, and its scope
 *  where it has one" (DESIGN-r2.md) -- and the parallel line for every
 *  other standing a record can be read in. */
export function sublineWords(args: {
  status: string
  governs: boolean
  adoptedBy?: string | null
  adoptedAt?: number | null
  scopeLabel?: string | null
  recordedBy?: string | null
  recordedAt?: number | null
}): string {
  const { status, governs, adoptedBy, adoptedAt, scopeLabel, recordedBy, recordedAt } = args
  if (status === 'adopted') {
    const who = stripAt(adoptedBy, 'somebody')
    const when = dateOnly(adoptedAt)
    const base = `Adopted by ${who}${when ? `, ${when}` : ''}`
    return scopeLabel ? `${base} · ${scopeLabel}` : base
  }
  if (status === 'adoption_requested') {
    return governs
      ? 'If adopted, agents are given it as a rule they must follow.'
      : "If adopted, agents are told it when relevant; it doesn't bind them."
  }
  if (status === 'declined') {
    const who = recordedBy ? ` by ${stripAt(recordedBy)}` : ''
    const when = dateOnly(recordedAt)
    return `Declined${who}${when ? `, ${when}` : ''}.`
  }
  if (status === 'superseded') {
    const when = dateOnly(recordedAt)
    return `Replaced${when ? `, ${when}` : ''}.`
  }
  if (status === 'ended' || status === 'retired') {
    const when = dateOnly(recordedAt)
    return `Ended${when ? `, ${when}` : ''}.`
  }
  const who = stripAt(recordedBy, 'somebody')
  const when = dateOnly(recordedAt)
  return `Recorded by ${who}${when ? `, ${when}` : ''}`
}

/** A history act's code (`material-recorded`, `adoption-requested`, …) as
 *  words, for the History section's list. An act this does not know is said
 *  plainly rather than dropped: its own words, decoded, capitalised once. */
export function actWords(act: string): string {
  switch (act) {
    case 'material-recorded': return 'Recorded'
    case 'material-adopted': return 'Adopted'
    case 'adoption-requested': return 'Adoption requested'
    case 'material-declined': return 'Declined'
    case 'material-challenged': return 'Challenged'
    case 'material-set-aside': return 'Challenge set aside'
    case 'material-withdrawn': return 'Challenge withdrawn'
    case 'material-superseded': return 'Superseded'
    case 'material-placed': return 'Placed'
    case 'material-unplaced': return 'Unplaced'
    default: {
      const words = act.replace(/^material-/, '').replace(/[-_]/g, ' ')
      return words ? words[0].toUpperCase() + words.slice(1) : act
    }
  }
}

/** A count, said as none/one/many: "none", "1 source", "3 outcomes". */
export function countWords(n: number, singular: string, plural = singular + 's'): string {
  if (n === 0) return 'none'
  return `${n} ${n === 1 ? singular : plural}`
}

/** A section's open/closed set, toggled: a `Set` so several sections can be
 *  open together, exactly as the mockups' "details opened" state shows. */
export function toggleFold<T>(open: ReadonlySet<T>, key: T): Set<T> {
  const next = new Set(open)
  if (next.has(key)) next.delete(key)
  else next.add(key)
  return next
}

/** "challenged: a separate quiet flag, never a status" (DESIGN-r2.md) --
 *  the words for that flag, open challenges only (the same count the
 *  per-post popover already shows, `epistemic/Records.tsx`'s `q2e-challenged`:
 *  "1 open challenge" / "3 open challenges"). `null` when there is nothing
 *  to flag, so a caller can decide not to render it at all. */
export function challengedFlagWords(n: number): string | null {
  if (n <= 0) return null
  return `${n} open ${n === 1 ? 'challenge' : 'challenges'}`
}

/** An outcome's evidence link, in words: the Turn's own number where it is
 *  known ("#5"), else a short form of its id -- never the bare, unshortened
 *  id a reader cannot use at a glance. `null` when there is no evidence to
 *  point at. */
export function evidenceLabel(number: number | null | undefined, id: string | null | undefined): string | null {
  if (number) return `#${number}`
  if (id && id.trim()) return id.length <= 10 ? id : id.slice(0, 10) + '…'
  return null
}
