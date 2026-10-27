/* EXPERIMENTAL: the reading half of matrix-heatmap (drawn in ../types/matrix-heatmap.tsx). */
import type { TypeSpec } from './api'
import { csvTable } from '../util'

export interface MatrixData { rows: string[]; cols: string[]; cells: (number | null)[][]; min: number; max: number; midpoint?: number; labels: boolean; corner?: string }

export const matrixHeatmapSpec: TypeSpec<MatrixData> = {
  type: 'matrix-heatmap',
  summary: 'Numeric row × column data with a sequential or declared diverging scale.',
  attrs: {
    title: { req: 'optional', says: 'a heading' },
    scale: { req: 'optional', choices: ['sequential', 'diverging'], says: 'default sequential; diverging requires midpoint' },
    midpoint: { req: 'optional', says: 'any finite decimal midpoint; both sides share the maximum distance from it' },
    corner: { req: 'optional', says: 'declared corner header; blank by default' },
    labels: { req: 'optional', choices: ['yes', 'no'], says: 'show values in cells (default yes); labels remain accessible when no' },
  },
  body: 'CSV, one row per line: row,<column labels>, then <row label>,<numeric cells>. Empty cells mean missing, not zero. At most 100 rows × 100 columns.',
  parse(body, a, c) {
    const csvLine = /^(?:[^",\r\n]*|"(?:[^"]|"")*")(?:,(?:[^",\r\n]*|"(?:[^"]|"")*"))*$/
    body.trim().split(/\r?\n/).forEach((line, i) => {
      if (!csvLine.test(line)) c.err(`line ${i + 1}`, 'Malformed CSV quoting; use one row per line and double embedded quotes.')
    })
    const t = csvTable(body, c.err)
    const cols = t?.header.slice(1) ?? [], rows = t?.rows.map(r => r[0]?.trim() ?? '') ?? []
    if (t?.header[0] !== 'row' || !cols.length || cols.some(v => !v)) c.err('header', 'Use row followed by nonempty, unique column labels.')
    if (rows.some((v, i) => !v || rows.indexOf(v) !== i)) c.err('rows', 'Row labels must be nonempty and unique.')
    if (rows.length > 100 || cols.length > 100) {
      c.err('size', 'At most 100 rows and 100 columns are supported.')
      return { rows: [], cols: [], cells: [], min: 0, max: 0, labels: true }
    }
    const cells = (t?.rows ?? []).map((r, i) => r.slice(1).map(raw => {
      const v = raw.trim()
      if (!v) return null
      const n = Number(v)
      if (!/^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:e[+-]?\d+)?$/i.test(v) || !Number.isFinite(n) || Math.abs(n) > 1e12)
        c.err(`row ${i + 2}`, 'Cells must be finite decimal numbers with magnitude at most 1e12, or empty for missing.')
      return n
    }))
    const numbers = cells.flat().filter((v): v is number => v !== null)
    const min = numbers.length ? Math.min(...numbers) : 0, max = numbers.length ? Math.max(...numbers) : 0
    let midpoint: number | undefined
    if (a.scale === 'diverging') {
      midpoint = Number(a.midpoint)
      if (a.midpoint === undefined || !a.midpoint.trim() || !/^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:e[+-]?\d+)?$/i.test(a.midpoint) || !Number.isFinite(midpoint))
        c.err('midpoint', 'Diverging requires a finite numeric midpoint.')
    } else if (a.midpoint !== undefined) c.err('midpoint', 'Use scale=diverging with midpoint, or omit midpoint for sequential.')
    return { rows, cols, cells, min, max, midpoint, labels: a.labels !== 'no', corner: a.corner }
  },
}
