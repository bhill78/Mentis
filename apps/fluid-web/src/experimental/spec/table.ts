/* EXPERIMENTAL: the reading half of table (drawn in ../types/table.tsx). */
import type { TypeSpec } from './api'
import { csvTable, listOf } from '../util'

export interface TableData {
  header: string[]
  /** Cells, trimmed, in source order. */
  rows: string[][]
  /** Row identity: the key cell, or "#n" (source position) with no key. */
  ids: string[]
  numeric: boolean[]
  keyed: boolean
  editable: string[]
  select: 'none' | 'one' | 'many'
}

export const isNum = (s: string) => s !== '' && Number.isFinite(Number(s))

export const tableSpec: TypeSpec<TableData> = {
  type: 'table',
  summary: 'A data grid: sort, filter, choose rows, correct declared columns. All of that is state; the Markdown keeps the rows.',
  attrs: {
    title: { req: 'optional', says: 'a heading' },
    key: { req: 'optional', says: 'the column that names each row (unique, never empty); needed for selection/edits to follow a row' },
    select: { req: 'optional', choices: ['none', 'one', 'many'], says: 'whether the person may choose rows: none, one or many' },
    editable: { req: 'optional', says: 'comma list of columns the person may correct' },
  },
  body: 'CSV: a header row, then one row per line',
  parse(body, a, c) {
    const t = csvTable(body, c.err, 'rows')
    const header = t?.header ?? []
    const rows = (t?.rows ?? []).map((r) => r.map((x) => x.trim()))
    const select = (a.select ?? 'none') as TableData['select']
    const editable = listOf(a.editable).filter((x) => x !== '')
    for (const col of editable)
      if (!header.includes(col)) c.err('editable', `editable names the column “${col}”, but the columns are: ${header.join(', ')}.`)
    let ids = rows.map((_, i) => `#${i + 1}`)
    const keyed = a.key !== undefined
    if (keyed) {
      const k = header.indexOf(a.key)
      if (k < 0) c.err('key', `key names the column “${a.key}”, but the columns are: ${header.join(', ')}.`)
      else {
        ids = rows.map((r) => r[k] ?? '')
        ids.forEach((id, i) => {
          if (!id) c.err(`data line ${i + 2}`, `The key column “${a.key}” is empty in this row; every row needs its own key.`)
          else if (ids.indexOf(id) !== i) c.err(`data line ${i + 2}`, `The key “${id}” is already used on data line ${ids.indexOf(id) + 2}; keys must be unique.`)
        })
        if (editable.includes(a.key)) c.err('editable', `The key column “${a.key}” can't be editable: it is what keeps a row's selection and edits attached to it.`)
      }
    } else if (select !== 'none' || editable.length)
      c.warn('key', 'No key= column, so rows are known only by position. If the rows in the Markdown are reordered, added or removed, the selection and edits will land on the wrong rows, so what is entered in this table will not be saved. Add key=<a column whose values are unique>.')
    const numeric = header.map((_, i) => {
      const vals = rows.map((r) => r[i] ?? '').filter((v) => v !== '')
      return vals.length > 0 && vals.every(isNum)
    })
    return { header, rows, ids, numeric, keyed, editable, select }
  },
}
