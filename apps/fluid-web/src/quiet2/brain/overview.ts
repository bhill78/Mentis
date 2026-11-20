/* ABOUT THIS BRAIN: what the server measured (`GET /api/brain/overview`), and
 * the words it is said in.
 *
 * Nothing here draws anything, so every sentence is checkable without a
 * browser (`tests/brain_overview_unit.ts`). Nothing here measures anything
 * either: a number shown is one the server read, and one it could not read
 * is said as "not measured", never as zero.
 *
 * TWO SORTS OF NUMBER, KEPT APART IN THE WORDS: how many things the Brain
 * holds (counts), and how much room they take on this computer (sizes). */
import { CLIENT_HEADERS } from '../../api'
import { statusWord } from './data'
import { kindWords } from './logic'

export interface KindCount { kind: string; count: number }
export interface RecordCounts { total: number; kinds: KindCount[]; standing: { status: string; count: number }[]; past: number }
export interface FileOrigin { group: 'attached' | 'returned' | 'source' | 'other'; origin: string; references: number; unique: number; bytes: number }
export interface SourceRow { collection: string; name: string | null; connector: string; connector_label: string; bound: boolean | null }
export interface FolderItem { name: string; files: number; bytes: number; portable: boolean }

export interface BrainOverviewData {
  brain: { id: string; corpus_name: string | null; corpus_role: string | null }
  read_at: number
  counts: {
    conversations: { total: number; archived: number; trash: number }
    posts: number
    knowledge: RecordCounts
    governing: RecordCounts
    files: { unique: number; references: number; purged_references: number; purged_files: number; recorded_bytes: number; unsized: number; origins: FileOrigin[] }
    sources: { total: number; bound: number; collections: SourceRow[] }
  }
  storage: {
    database: { bytes: number; files: { name: string; bytes: number }[]; copy_bytes: number | null }
    files: {
      measured_at: number; kept_for_s: number; on_disk: number; bytes: number
      missing: number; missing_bytes: number; unnamed: number; unnamed_bytes: number
      purged_present: number; purged_present_bytes: number; stray: number; stray_bytes: number
    }
    kept: FolderItem[]
    other: FolderItem[]
  }
  portable: {
    bytes: number | null; why_not: string | null; as: string
    parts: { part: 'database' | 'files' | 'kept'; bytes: number | null; count?: number; names?: string[] }[]
    left_out: {
      sources: number; purged_files: number; purged_bytes: number; missing_files: number
      stray_files: number; stray_bytes: number; other: FolderItem[]; other_bytes: number; sidecar_bytes: number
    }
  }
}

export async function fetchBrainOverview(measure = false, signal?: AbortSignal): Promise<BrainOverviewData> {
  const r = await fetch('/api/brain/overview' + (measure ? '?measure=1' : ''), { headers: { ...CLIENT_HEADERS }, signal })
  const body = (await r.json().catch(() => null)) as (BrainOverviewData & { error?: string }) | null
  if (!r.ok || !body || body.error) throw new Error(body?.error ?? r.statusText ?? 'the Brain did not answer')
  return body
}

/* -- numbers, said -------------------------------------------------------- */

/** 11218 -> "11,218": the same in every locale, so a count reads one way. */
export const num = (n: number) => Math.round(n).toString().replace(/\B(?=(\d{3})+(?!\d))/g, ',')

/** "1 post", "11,218 posts". */
export const things = (n: number, one: string, many = one + 's') => `${num(n)} ${n === 1 ? one : many}`

/** A size on disk in the units a file manager uses (1 KB = 1,024 bytes).
 *  Three significant figures at most; a size nobody measured says so. */
export function size(bytes: number | null | undefined): string {
  if (bytes == null || !Number.isFinite(bytes)) return 'not measured'
  if (bytes < 1024) return `${num(bytes)} ${bytes === 1 ? 'byte' : 'bytes'}`
  const units = ['KB', 'MB', 'GB', 'TB']
  let v = bytes / 1024, u = 0
  while (v >= 1024 && u < units.length - 1) { v /= 1024; u++ }
  const shown = v >= 100 ? Math.round(v).toString() : v >= 10 ? v.toFixed(1) : v.toFixed(2)
  return `${shown.replace(/\.0+$/, '').replace(/(\.\d*[1-9])0+$/, '$1')} ${units[u]}`
}

/** The time something was read, for "measured at". */
export function clock(at: number): string {
  const d = new Date(at * 1000)
  const p = (n: number) => String(n).padStart(2, '0')
  return `${p(d.getHours())}:${p(d.getMinutes())}`
}

const list = (parts: string[]) => (parts.length <= 1 ? parts.join('') : parts.slice(0, -1).join(', ') + ' and ' + parts[parts.length - 1])

/* -- the overview: a few lines -------------------------------------------- */

/** What the Brain is called, in one line. */
export function brainName(o: BrainOverviewData): string {
  const name = o.brain.corpus_name?.trim()
  const role = o.brain.corpus_role?.trim()
  if (!name) return 'This Brain has no name recorded'
  return role ? `${name} · ${role}` : name
}

const standingCount = (r: RecordCounts, status: string) => r.standing.find((s) => s.status === status)?.count ?? 0

/** HOW MANY THINGS: the lines of the first section. */
export function holdsLines(o: BrainOverviewData): string[] {
  const c = o.counts
  const aside = [c.conversations.archived ? `${num(c.conversations.archived)} archived` : '', c.conversations.trash ? `${num(c.conversations.trash)} in Trash` : ''].filter(Boolean)
  const g = c.governing
  return [
    `${things(c.conversations.total, 'conversation')}${aside.length ? ` (${aside.join(', ')})` : ''} · ${things(c.posts, 'post')}`,
    `${things(c.knowledge.total, 'knowledge record')} · ${things(g.total, 'governing record')}${g.total ? `, ${num(standingCount(g, 'adopted'))} in effect` : ''}`,
    `${things(c.files.unique, 'file')}${c.files.references !== c.files.unique ? `, referred to ${things(c.files.references, 'time')}` : ''} · ${things(c.sources.total, 'connected source')}`,
  ]
}

/** HOW MUCH ROOM: the line of the second section. */
export function diskLine(o: BrainOverviewData): string {
  return `Database ${size(o.storage.database.bytes)} · Files ${size(o.storage.files.bytes)}`
}

/** What a portable backup would take, and exactly what that includes and
 *  leaves out. Every clause is said only where it is true of this Brain. */
export function portableWords(o: BrainOverviewData): { total: string; includes: string; excludes: string } {
  const p = o.portable
  const files = p.parts.find((x) => x.part === 'files')
  const kept = p.parts.find((x) => x.part === 'kept')
  const total = p.bytes == null ? `Not measured: ${p.why_not ?? 'a part could not be read'}.` : `About ${size(p.bytes)} as a portable backup.`
  const inc = ['the database', files?.count ? (files.count === 1 ? 'the 1 stored file' : `all ${num(files.count)} stored files, each once`) : 'no stored files (there are none)']
  if (kept?.names?.length) inc.push('the pictures, layouts and settings kept in the Brain’s folder')
  const out: string[] = []
  const l = p.left_out
  if (l.sources) out.push(`the ${l.sources === 1 ? 'connected source itself' : `${num(l.sources)} connected sources themselves`} (their folders, repositories and databases stay where they are; only the copies already taken are included)`)
  if (l.purged_files) out.push(`${things(l.purged_files, 'file')} you removed (${size(l.purged_bytes)})`)
  if (l.missing_files) out.push(`${things(l.missing_files, 'file')} the Brain refers to but no longer has on disk`)
  if (l.stray_files) out.push(`${things(l.stray_files, 'unfinished or misplaced file')} (${size(l.stray_bytes)})`)
  if (l.other.length) out.push(`${size(l.other_bytes)} that is rebuilt or belongs to this computer`)
  return {
    total,
    includes: `Includes ${list(inc)}.`,
    excludes: out.length ? `Leaves out ${list(out)}.` : 'Leaves nothing of this Brain out.',
  }
}

/* -- detail, on demand ---------------------------------------------------- */

export interface Row { label: string; value: string; note?: string }

export const kindRows = (r: RecordCounts): Row[] => r.kinds.map((k) => ({ label: kindWords(k.kind), value: num(k.count) }))

/** A standing in the browser's own words, with what it means for effect. */
export function standingRows(r: RecordCounts): Row[] {
  const note: Record<string, string> = { adopted: 'in effect', adoption_requested: 'waiting for a decision', recorded: 'not in effect', declined: 'not in effect' }
  const rows = r.standing.filter((s) => s.count > 0 || s.status === 'adopted').map((s) => ({ label: statusWord(s.status), value: num(s.count), note: note[s.status] }))
  if (r.past) rows.push({ label: 'Replaced or ended', value: num(r.past), note: 'kept, not counted above' })
  return rows
}

const ORIGIN: Record<FileOrigin['group'], string> = { attached: 'Attached by people', returned: 'Returned by agents', source: 'Taken from a source', other: 'Other' }

/** Where the files came from. A source's connector is named; the rest are
 *  said by how they arrived. */
export function originRows(o: BrainOverviewData): Row[] {
  const label = (x: FileOrigin) => {
    if (x.group === 'source') {
      const connector = o.counts.sources.collections.find((c) => c.connector === x.origin)?.connector_label
      return `${ORIGIN.source} (${connector ?? x.origin})`
    }
    return x.group === 'other' ? `${ORIGIN.other} (${x.origin || 'unnamed'})` : ORIGIN[x.group]
  }
  return o.counts.files.origins.map((x) => ({ label: label(x), value: size(x.bytes), note: things(x.unique, 'file') }))
}

/** The bytes on disk, part by part. */
export function diskRows(o: BrainOverviewData): Row[] {
  const s = o.storage
  const rows: Row[] = s.database.files.map((f) => ({
    label: f.name === 'corpus.db' ? 'Database' : f.name.endsWith('-wal') ? 'Database, changes not yet folded in' : f.name.endsWith('-shm') ? 'Database, working index' : f.name,
    value: size(f.bytes), note: f.name,
  }))
  rows.push({ label: 'Stored files', value: size(s.files.bytes), note: `${things(s.files.on_disk, 'file')}, each kept once` })
  for (const k of [...s.kept, ...s.other]) rows.push({ label: folderWords(k.name), value: size(k.bytes), note: k.portable ? k.name : `${k.name} · not in a portable backup` })
  return rows
}

const FOLDER: Record<string, string> = {
  presentation: 'Pictures, layouts and summaries', instances: 'Runtime and capacity notes', 'mentis-corpus.json': 'The Brain’s name and identity',
  derived: 'Search and status indexes (rebuilt)', 'mcp-policy.json': 'This computer’s agent access policy',
}
export const folderWords = (name: string) => FOLDER[name] ?? name

/** What is outside a portable backup, item by item. Empty where nothing is. */
export function leftOutRows(o: BrainOverviewData): Row[] {
  const l = o.portable.left_out
  const rows: Row[] = o.counts.sources.collections.map((c) => ({
    label: c.name || 'A source with no name', value: c.connector_label,
    note: c.bound === false ? 'not connected on this computer' : c.bound ? 'stays where it is; where that is, is not part of the Brain' : 'stays where it is',
  }))
  if (l.purged_files) rows.push({ label: 'Files you removed', value: size(l.purged_bytes), note: things(l.purged_files, 'file') })
  if (o.counts.files.purged_references && !l.purged_files) rows.push({ label: 'Files you removed', value: 'gone', note: `${things(o.counts.files.purged_references, 'reference')} kept` })
  if (l.missing_files) rows.push({ label: 'Files referred to but not on disk', value: num(l.missing_files), note: 'they would be missing after a move too' })
  if (l.stray_files) rows.push({ label: 'Unfinished or misplaced files', value: size(l.stray_bytes), note: things(l.stray_files, 'file') })
  for (const k of l.other) rows.push({ label: folderWords(k.name), value: size(k.bytes), note: k.name })
  if (l.sidecar_bytes) rows.push({ label: 'Database working files', value: size(l.sidecar_bytes), note: 'their contents are in the database’s copy' })
  return rows
}

/** What the disk measurement adds that the record does not say. */
export function measuredWords(o: BrainOverviewData): string {
  const f = o.storage.files
  const extra = f.unnamed ? ` ${things(f.unnamed, 'stored file')} (${size(f.unnamed_bytes)}) ${f.unnamed === 1 ? 'is' : 'are'} referred to by nothing; a portable backup carries ${f.unnamed === 1 ? 'it' : 'them'} too.` : ''
  return `Counts read at ${clock(o.read_at)}. Files on disk measured at ${clock(f.measured_at)}, by size only: no file was opened or checked.${extra}`
}
