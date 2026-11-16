/* MANAGE SOURCES IN QUIET CHAT: WHAT IS SAID, decided apart from what draws
 * it, so each rule is checkable without a browser (`tests/quiet_sources_unit.ts`).
 *
 * Everything here is read from what the source system already answers
 * (`/api/sources`, `mentis/web/sources.py`): the collection, this machine's
 * binding, and the one run it keeps for the collection. Nothing is invented:
 * no health, no percentage, no schedule.
 *
 * THE BACKEND'S `state` IGNORES A RUN (it says "not refreshing" while one
 * runs), so the standing here is read from the run FIRST. A run that ended
 * failed or refused is the only "problem" the system knows, and it is kept
 * only while the server keeps running; that is said where it is shown. */
import type { CollectionView, Descriptor, RunView } from '../../surfaces/sources/route'

export type SourceTab = 'all' | 'here' | 'away' | 'attention'
export type SourceOrder = 'recent' | 'name' | 'size'
export type Tone = 'ok' | 'run' | 'bad' | 'off' | 'none'

export const TABS: { id: SourceTab; label: string }[] = [
  { id: 'all', label: 'All' },
  { id: 'here', label: 'Connected here' },
  { id: 'away', label: 'Not connected' },
  { id: 'attention', label: 'Needs attention' },
]

export const count = (n: number | null | undefined) => (n ?? 0).toLocaleString('en-US')

export function size(n: number | null | undefined): string {
  if (n === null || n === undefined) return '—'
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(n < 10 * 1024 ? 1 : 0)} KB`
  if (n < 1024 * 1024 * 1024) return `${(n / (1024 * 1024)).toFixed(1)} MB`
  return `${(n / (1024 * 1024 * 1024)).toFixed(1)} GB`
}

/** What one held thing is called. A folder holds files; a database holds
 *  records; a repository holds files AND the change records beside them, so
 *  it and anything else is counted in items, never miscalled files. */
export const itemWord = (connector: string, n: number) =>
  connector === 'filesystem' ? (n === 1 ? 'file' : 'files')
    : connector === 'sqlite' ? (n === 1 ? 'record' : 'records')
      : n === 1 ? 'item' : 'items'

/** A day, as a list row says it: "Nov 14". */
export function day(ts: number | null | undefined): string {
  if (!ts) return ''
  return new Date(ts * 1000).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
}

/** A moment: "Nov 14, 3:12 PM". */
export function moment(ts: number | null | undefined): string {
  if (!ts) return ''
  return new Date(ts * 1000).toLocaleString('en-US', { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })
}

/** An address shown to a person never carries what could be a credential.
 *  The server already refuses such an address; this is the second guard, for
 *  text that reaches the page from an error. */
export const redact = (text: string): string => text.replace(/([a-z][a-z0-9+.-]*:\/\/)[^/\s@]+@/gi, '$1…@')

export const running = (c: Pick<CollectionView, 'run'>): RunView | null => (c.run && c.run.state === 'running' ? c.run : null)

/** The run that ended badly, if the collection's last run did. A cancelled
 *  run is not a problem: the owner stopped it. */
export const failed = (c: Pick<CollectionView, 'run'>): RunView | null =>
  c.run && (c.run.state === 'failed' || c.run.state === 'refused') ? c.run : null

/** Refreshing takes; a plan or preview only looks. */
export const runWords = (r: Pick<RunView, 'kind'>) => (r.kind === 'sweep' ? 'Refreshing now' : 'Looking at the source')
export const failedWords = (r: Pick<RunView, 'kind'>) => (r.kind === 'sweep' ? 'Last refresh failed' : 'Last preview failed')

export interface Failure { title: string | null; advice: string | null; said: string }

const KNOWN: { find: RegExp; title: string; advice: string }[] = [
  { find: /authentication required/i, title: 'sign-in was refused',
    advice: 'Mentis holds no password for it. Sign in to that server with Git on this machine (its credential helper, or an SSH key), then try again.' },
  { find: /unknown host key/i, title: 'this machine does not know the server’s key',
    advice: 'Connect to the server once with ssh on this machine and accept its key, then try again.' },
  { find: /not found, or no access/i, title: 'it was not found, or this machine has no access to it',
    advice: 'Check the address, and that the account Git uses on this machine can read it.' },
  { find: /unreachable/i, title: 'the server could not be reached',
    advice: 'Check the network and the address, then try again.' },
]

/** Why a run failed, in the system's own words, with what to do where the
 *  system's words are ones it is known to say. Anything else is shown as it
 *  was said, with nothing guessed about it. */
export function failureWords(text: string | null | undefined): Failure {
  const said = redact((text ?? '').trim()) || 'No reason was given.'
  const k = KNOWN.find((x) => x.find.test(said))
  return { title: k?.title ?? null, advice: k?.advice ?? null, said }
}

/** The few words a list row shows for a failure. */
export function failureShort(text: string | null | undefined): string {
  const f = failureWords(text)
  if (f.title) return f.title
  const first = f.said.split(/[\n.]/)[0].trim()
  return first.length > 60 ? first.slice(0, 57) + '…' : first
}

export interface Standing { tone: Tone; label: string; words: string; attention: boolean }

/** How a source stands, for a row and for its page. The run is read first. */
export function standing(c: CollectionView): Standing {
  const n = c.counts?.present ?? 0
  const held = `${count(n)} ${itemWord(c.connector, n)}`
  const run = running(c)
  if (run) {
    return { tone: 'run', label: runWords(run), attention: false,
      words: `${count(run.progress.files)} ${run.progress.files === 1 ? 'file' : 'files'}, ${size(run.progress.bytes)} so far` }
  }
  const bad = failed(c)
  if (bad) return { tone: 'bad', label: failedWords(bad), words: failureShort(bad.failure), attention: true }
  const taken = c.last_sweep ? day(c.last_sweep.at) : ''
  if (!c.binding?.bound) {
    if (!c.last_sweep) return { tone: 'none', label: 'Declared', words: 'nothing taken yet', attention: false }
    return { tone: 'off', label: 'Not connected on this machine', words: `${held} held · taken ${taken}`, attention: false }
  }
  if (!c.last_sweep) return { tone: 'ok', label: 'Connected here', words: 'nothing taken yet', attention: false }
  return { tone: 'ok', label: 'Connected here', words: `${held} · refreshed ${taken}`, attention: false }
}

export interface Narrow { q: string; tab: SourceTab; kind: string; order: SourceOrder }

/** The rows a browser shows: narrowed, then ordered. `label` names a kind. */
export function listed(all: CollectionView[], by: Narrow, label: (connector: string) => string): CollectionView[] {
  const q = by.q.trim().toLowerCase()
  const rows = all.filter((c) =>
    (!q || (c.name + ' ' + label(c.connector)).toLowerCase().includes(q)) &&
    (!by.kind || c.connector === by.kind) &&
    (by.tab === 'all' || (by.tab === 'here' && !!c.binding?.bound) || (by.tab === 'away' && !c.binding?.bound) ||
      (by.tab === 'attention' && standing(c).attention)))
  const at = (c: CollectionView) => c.last_sweep?.at ?? 0
  if (by.order === 'name') return rows.sort((a, b) => a.name.localeCompare(b.name))
  if (by.order === 'size') return rows.sort((a, b) => (b.counts?.held_bytes ?? 0) - (a.counts?.held_bytes ?? 0) || a.name.localeCompare(b.name))
  return rows.sort((a, b) => at(b) - at(a) || a.name.localeCompare(b.name))
}

export const attentionCount = (all: CollectionView[]) => all.filter((c) => standing(c).attention).length

/** "3 of 7 sources · 4 connected on this machine · 569 MB held". */
export function footWords(shown: number, all: CollectionView[]): string {
  const total = all.length
  const of = shown < total ? `${shown} of ${total}` : String(total)
  const here = all.filter((c) => c.binding?.bound).length
  const held = all.reduce((a, c) => a + (c.counts?.held_bytes ?? 0), 0)
  return `${of} ${total === 1 ? 'source' : 'sources'} · ${here} connected on this machine · ${size(held)} held`
}

/** What a sweep did, in one line: only what is not zero. */
export function sweepWords(counts: Record<string, number> | null | undefined): string {
  const c = counts ?? {}
  const parts: string[] = []
  const say = (n: number | undefined, word: string) => { if (n) parts.push(`${count(n)} ${word}`) }
  say(c.new, 'new'); say((c.changed ?? 0) + (c.reappeared ?? 0), 'changed'); say(c.absent, 'gone from the source')
  say(c.withheld, 'withheld'); say(c.not_examined, 'not examined')
  if (!parts.length) return c.unchanged ? `nothing changed (${count(c.unchanged)} unchanged)` : 'nothing changed'
  return parts.join(', ')
}

/** The one-line summary of what a preview would do. */
export function previewWords(counts: Record<string, number>): string {
  const moved = (counts.new ?? 0) + (counts.changed ?? 0) + (counts.reappeared ?? 0) + (counts.absent ?? 0)
  return moved ? sweepWords(counts) : 'Nothing has changed since the last refresh.'
}

/** Patterns, as a person reads them: "everything" for the catch-alls. */
export function patternWords(list: string[] | null | undefined): string {
  const l = (list ?? []).filter(Boolean)
  if (!l.length) return 'nothing'
  if (l.length === 1 && (l[0] === '*' || l[0] === '**' || l[0] === '**/*')) return 'everything'
  return l.join('  ')
}

/** What changing the selection would do: what it brings in, and what would
 *  leave it (kept as held, no longer examined; never recorded as gone). */
export function reviseWords(counts: Record<string, number>): string {
  const moved = (counts.new ?? 0) + (counts.changed ?? 0) + (counts.reappeared ?? 0) + (counts.absent ?? 0)
  const leaving = counts.not_examined ?? 0
  const out = leaving ? `${count(leaving)} would leave the selection: kept as held, no longer refreshed.` : ''
  const c = { ...counts, not_examined: 0 }
  if (!moved) return out || 'This change takes nothing new and leaves nothing out that is held.'
  return `${sweepWords(c)}.${out ? ' ' + out : ''}`
}

/** Past this many available kinds, Add a source's cards get a search line. */
export const SEARCH_FROM = 7

/** The kinds a person can choose now, narrowed by what they typed: only what
 *  the source system says is available, matched on its name and its own words. */
export function kindsShown(descriptors: Descriptor[], q: string): Descriptor[] {
  const words = q.trim().toLowerCase()
  return descriptors.filter((d) => d.available && (!words || (d.label + ' ' + (d.summary ?? '')).toLowerCase().includes(words)))
}
