import { complete, config, isTaken, type Cfg, type Samples, type Table } from './types'
export const weight = (type: string) => /INT|REAL|FLOA|DOUB|NUM|DEC|BOOL|DATE|TIME/i.test(type) ? 1 : /CHAR|CLOB|TEXT/i.test(type) ? 3 : 8
export function figure(t: Table, cfg: Cfg, samples: Samples) {
  const c = config(cfg, t.name), sample = samples[t.name], base = sample?.total ?? t.rows
  const narrowed = c.rows.some(complete)
  const rows = narrowed ? sample?.matching ?? null : base
  const totalWeight = t.columns.reduce((s, col) => s + weight(col.type), 0)
  const takenWeight = t.columns.filter(col => col.pk || isTaken(col, c)).reduce((s, col) => s + weight(col.type), 0)
  const amount = t.bytes == null || rows == null || base == null ? null : t.bytes * rows / Math.max(1, base) * takenWeight / Math.max(1, totalWeight)
  return { rows, bytes: amount, narrowed: narrowed || c.omit.length > 0, source: sample ? 'snapshot' : 'file', base }
}
export function totals(tables: Table[], sel: string[], cfg: Cfg, samples: Samples) {
  const fs = tables.filter(t => sel.includes(t.name)).map(t => figure(t, cfg, samples))
  return { tables: fs.length, rows: fs.some(f => f.rows == null) ? null : fs.reduce((s, f) => s + f.rows!, 0),
    bytes: fs.some(f => f.bytes == null) ? null : fs.reduce((s, f) => s + f.bytes!, 0) }
}

/* WHAT ONE ACQUISITION IS COUNTED IN (defect D-11). A database is recorded as
 * one object per ROW, one SCHEMA object per table beside them, and -- for a
 * table with no key -- one SNAPSHOT object holding the table whole. So "rows"
 * and "records" (Admissions) are different numbers for the same thing, and
 * the screens said them side by side with nothing between: "Acquire 5 rows",
 * "7 Admissions recorded", "5 rows are now in Mentis", "a copy of 7 records".
 * Every sentence here says WHICH it counts, so the numbers add up on screen.
 *
 * `kinds` is the server's own count of what is held, by what it is
 * (`counts.kinds` of the collection, mentis/sources/reading.py). */
export type Kinds = Record<string, number>
const n = (v: number) => v.toLocaleString('en-US')
const some = (v: number, one: string, many: string) => `${n(v)} ${v === 1 ? one : many}`
const listed = (parts: string[]) => parts.length < 2 ? parts.join('') : `${parts.slice(0, -1).join(', ')} and ${parts[parts.length - 1]}`

/** "5 rows and 2 table schemas"; '' where the source names no kinds. */
export function kindsWords(kinds: Kinds | null | undefined): string {
  const k = kinds ?? {}
  if (!('row' in k) && !('schema' in k) && !('snapshot' in k)) return ''
  return listed([
    k.row || !k.snapshot ? some(k.row ?? 0, 'row', 'rows') : '',
    k.snapshot ? some(k.snapshot, 'table held whole', 'tables held whole') : '',
    k.schema ? some(k.schema, 'table schema', 'table schemas') : '',
  ].filter(Boolean))
}

/** What a plan would record, by what it is, read from the object names the
 *  plan lists (`<table>/@schema`, `<table>/snapshot`, otherwise a row). */
export function kindsOf(admit: { path: string }[]): Kinds {
  const k: Kinds = {}
  for (const a of admit) {
    const kind = a.path.endsWith('/@schema') ? 'schema' : a.path.endsWith('/snapshot') ? 'snapshot' : 'row'
    k[kind] = (k[kind] ?? 0) + 1
  }
  return k
}

/** The confirmation's count: "7 Admissions recorded (5 rows and 2 table schemas)". */
export function admittedWords(admit: { path: string }[]): string {
  const kinds = kindsWords(kindsOf(admit))
  return `${some(admit.length, 'Admission', 'Admissions')} recorded${admit.length && kinds ? ` (${kinds})` : ''}`
}

/** The result line, after an acquisition or a revise: what Mentis HOLDS now.
 *  `held` is the collection's own count once it has been read; a revise that
 *  takes no new row still holds its rows, so the plan's `new` (0 then) is
 *  never what "are now in Mentis" is read from. Before the count is known:
 *  a first acquisition holds exactly the rows it took (`newRows`); a revise
 *  claims no number it does not have. */
export function heldLine(tables: number, held: Kinds | null | undefined, newRows: number | null): string {
  const t = some(tables, 'table', 'tables')
  if (held && kindsWords(held)) {
    const total = Object.values(held).reduce((a, b) => a + b, 0)
    const data = listed([
      held.row || !held.snapshot ? some(held.row ?? 0, 'row', 'rows') : '',
      held.snapshot ? some(held.snapshot, 'table held whole', 'tables held whole') : '',
    ].filter(Boolean))
    return `${t} · ${data} are now in Mentis, held as ${some(total, 'record', 'records')} (${kindsWords(held)}).`
  }
  if (newRows !== null) return `${t} · ${some(newRows, 'row', 'rows')} are now in Mentis.`
  return `${t} are now in Mentis.`
}
