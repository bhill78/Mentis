/* EXPERIMENTAL: the reading half of status-grid (drawn in ../types/status-grid.tsx). */
import type { TypeSpec } from './api'

export interface Cell { label: string; state: string }

export const tones = ['good', 'warn', 'bad', 'neutral', 'info'] as const

export interface GridData { rows: string[]; columns: string[]; states: string[]; cells: Cell[][]; tones?: (string | undefined)[]; corner?: string }

export const statusGridSpec: TypeSpec<GridData> = {
  type: 'status-grid',
  summary: 'A static labelled categorical matrix, using only declared states and cells.',
  attrs: { title: { req: 'optional', says: 'a heading' }, corner: { req: 'optional', says: 'declared corner header; blank by default' } },
  body: 'JSON object: rows and columns (unique labels), states (1–8 strings or {label,tone} entries; tone is good/warn/bad/neutral/info), and cells (row-major arrays of {label,state}). At most 100 × 100 cells.',
  parse(body, a, c) {
    const empty: GridData = { rows: [], columns: [], states: [], cells: [] }
    let raw: unknown
    try { raw = JSON.parse(body) } catch { c.err('body', 'Use valid JSON with rows, columns, states and cells.'); return empty }
    if (!raw || typeof raw !== 'object' || Array.isArray(raw)) { c.err('body', 'The JSON must be an object.'); return empty }
    const o = raw as Record<string, unknown>
    if (Object.keys(o).some(k => !['rows', 'columns', 'states', 'cells'].includes(k))) c.err('body', 'Only rows, columns, states and cells are supported.')
    const declaredTones: (string | undefined)[] = []
    const stateLabels = Array.isArray(o.states) ? o.states.map((entry, i) => {
      if (typeof entry === 'string') return entry
      if (!entry || typeof entry !== 'object' || Array.isArray(entry) || Object.keys(entry).some(k => !['label', 'tone'].includes(k)) ||
        typeof entry.label !== 'string' || (entry.tone !== undefined && !tones.includes(entry.tone))) {
        c.err(`state ${i + 1}`, 'Use a string or {label,tone}, with tone good, warn, bad, neutral or info.'); return ''
      }
      declaredTones[i] = entry.tone
      return entry.label
    }) : o.states
    const labels = (key: string, max: number): string[] => {
      const v = key === 'states' ? stateLabels : o[key]
      if (!Array.isArray(v) || !v.length || v.length > max || v.some((x, i) => typeof x !== 'string' || !x.trim() || v.indexOf(x) !== i)) {
        c.err(key, `Declare 1–${max} unique, nonempty string labels.`); return []
      }
      return v as string[]
    }
    const rows = labels('rows', 100), columns = labels('columns', 100), states = labels('states', 8)
    if (!Array.isArray(o.cells) || o.cells.length !== rows.length) { c.err('cells', 'cells must have exactly one array per declared row.'); return { ...empty, rows, columns, states } }
    const cells: Cell[][] = []
    o.cells.forEach((row, ri) => {
      if (!Array.isArray(row) || row.length !== columns.length) { c.err(`row ${ri + 1}`, 'Declare exactly one cell per column.'); return }
      cells.push(row.map((v, ci) => {
        if (!v || typeof v !== 'object' || Array.isArray(v) || Object.keys(v).some(k => !['label', 'state'].includes(k)) || typeof v.label !== 'string' || !v.label.trim() || typeof v.state !== 'string' || !states.includes(v.state)) {
          c.err(`cell ${ri + 1},${ci + 1}`, 'Each cell needs a nonempty label and a state from the declared states key.'); return { label: '', state: '' }
        }
        return { label: v.label, state: v.state }
      }))
    })
    return { rows, columns, states, cells, tones: declaredTones, corner: a.corner }
  },
}
