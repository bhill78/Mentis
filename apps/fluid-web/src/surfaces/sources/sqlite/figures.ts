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
