/* EXPERIMENTAL: the reading half of checklist, chart and pad (drawn in ../types/basic.tsx). */
import type { TypeSpec } from './api'
import { csvTable } from '../util'

export type Items = { text: string; checked: boolean }[]

export const BAR_ONLY = ['stack', 'orient', 'max'] as const

/** The sum of declared cells, written to the most decimals any of them uses. Empty cells add nothing. */
export function sumText(raws: string[]) {
  const vals = raws.filter((s) => s !== '' && Number.isFinite(Number(s)))
  const dp = Math.max(0, ...vals.map((s) => (/e/i.test(s) ? 6 : (s.split('.')[1] ?? '').length)))
  return String(+vals.reduce((t, s) => t + Number(s), 0).toFixed(dp))
}

export interface ChartData {
  columns: string[]
  rows: string[][]
  x: { field: string; values: string[]; numbers: (number | null)[] | null }
  series: { field: string; values: (number | null)[] }[]
}

export const checklistSpec: TypeSpec<Items> = {
  type: 'checklist',
  summary: 'Items a person ticks. Ticks are state; the Markdown keeps what the author wrote.',
  attrs: { title: { req: 'optional', says: 'a heading' } },
  body: '`- [ ] text` or `- [x] text`, one per line',
  parse(body, _a, c) {
    const items: Items = []
    body.split('\n').forEach((line, n) => {
      if (!line.trim()) return
      const m = /^\s*[-*] \[( |x|X)\] (.*\S)\s*$/.exec(line)
      if (!m) c.err(`line ${n + 1}`, `“${line}” is not a checklist item. Items look like “- [ ] text” or “- [x] text”.`)
      else {
        /* Ticks are saved by item text (fill.ts), so two items with the same
           text could not be told apart: said, never refused. */
        const at = items.findIndex((x) => x.text === m[2])
        if (at >= 0)
          c.warn(`line ${n + 1}`, `“${m[2]}” is already an item above. Ticks are saved by the item's text, so what is ticked in this checklist will not be saved until every item's text is different.`,
            'Reword one of the items so no two are the same.')
        items.push({ text: m[2], checked: m[1] !== ' ' })
      }
    })
    if (!items.length) c.err('body', 'A checklist needs at least one item.')
    return items
  },
}

export const chartSpec: TypeSpec<ChartData | null> = {
  type: 'chart',
  summary: 'A chart drawn mechanically from declared form, fields, labels and units. Nothing is inferred from prose.',
  attrs: {
    form: { req: 'required', choices: ['bar', 'line', 'scatter', 'pie', 'venn'], says: 'bar, line, scatter, pie or venn' },
    x: { req: 'required', says: 'the column along the x axis' },
    y: { req: 'required', says: 'comma list of columns drawn as series' },
    x_label: { req: 'required', says: 'x axis text' },
    y_label: { req: 'required', says: 'y axis text' },
    x_unit: { req: 'optional', says: 'x unit, e.g. wk' },
    y_unit: { req: 'optional', says: 'y unit, e.g. mm' },
    title: { req: 'optional', says: 'a heading' },
    sets: { req: 'optional', says: 'Venn: exactly 2 or 3 distinct comma-separated names; region keys join member names with &' },
    counts: { req: 'optional', says: 'Venn counts: exclusive per-region (default), or total inclusive' },
    stack: { req: 'optional', choices: ['true', 'false'], says: 'bar: true draws the y series end to end in one bar per row, labelled with their sum; no negatives' },
    orient: { req: 'optional', choices: ['vertical', 'horizontal'], says: 'bar: vertical (default) or horizontal, categories down the side' },
    max: { req: 'optional', says: 'bar: a positive number fixing the value axis at 0..max, the rest of each bar an empty track; a value or stacked total above it is an error' },
  },
  body: 'CSV: a header row, then data rows',
  parse(body, a, c) {
    if (a.form === 'venn' && a.counts !== undefined && a.counts !== 'exclusive' && a.counts !== 'total')
      c.err('counts', `counts must be one of: exclusive, total — not “${a.counts}”.`)
    const t = csvTable(body, c.err)
    if (!t) return null
    const { header, rows } = t
    const x = a.x, ys = a.y.split(',')
    let bad = false
    if (!header.includes(x)) { c.err('x', `x names the column “${x}”, but the columns are: ${header.join(', ')}.`); bad = true }
    for (const y of ys)
      if (!header.includes(y)) { c.err('y', `y names the column “${y}”, but the columns are: ${header.join(', ')}.`); bad = true }
    if (bad) return null
    const num = (s: string | undefined, where: string, what: string) => {
      if (s === undefined || s.trim() === '') return null
      const v = Number(s.trim())
      if (!Number.isFinite(v)) { c.err(where, `${what} “${s}” is not a number.`); return null }
      return v
    }
    const xi = header.indexOf(x)
    if (a.form !== 'venn') {
      if ('sets' in a) c.warn('sets', 'chart has no attribute “sets”. It is kept, shown here, and ignored.')
      if ('counts' in a) c.warn('counts', 'chart has no attribute “counts”. It is kept, shown here, and ignored.')
    }
    const bar = a.form === 'bar'
    if (!bar) for (const k of BAR_ONLY) if (k in a) c.warn(k, `${k} applies only to form=bar. It is kept, shown here, and ignored.`)
    const max = bar && 'max' in a ? Number(a.max.trim() || NaN) : null
    if (max !== null && !(Number.isFinite(max) && max > 0)) c.err('max', `max must be a positive number — not “${a.max}”.`)
    if (a.form === 'pie' || a.form === 'venn') {
      if (ys.length !== 1) c.err('y', 'Pie and Venn require exactly one series.')
      const vals = rows.map((r, n) => {
        const v = num(r[header.indexOf(ys[0])], `data line ${n + 2}`, 'Count')
        if (v === null || v < 0) c.err(`data line ${n + 2}`, 'Counts must be present and non-negative.')
        return v
      })
      if (a.form === 'pie' && !vals.some((v) => v !== null && v > 0)) c.err('body', 'Pie requires a positive total.')
      if (a.form === 'venn') {
        const sets = (a.sets ?? '').split(',').map((v) => v.trim())
        if (sets.length < 2 || sets.length > 3 || sets.some((v) => !v || v.includes('&')) || new Set(sets).size !== sets.length)
          c.err('sets', 'Declare exactly 2 or 3 distinct non-empty sets; names cannot contain & or commas.')
        const regions = new Map<string, number | null>()
        rows.forEach((r, n) => {
          const members = (r[xi] ?? '').trim().split('&').map((v) => v.trim())
          if (members.some((v) => !sets.includes(v)) || new Set(members).size !== members.length)
            c.err(`data line ${n + 2}`, 'Region must name distinct declared sets joined by &.')
          const key = sets.filter((v) => members.includes(v)).join('&')
          if (regions.has(key)) c.err(`data line ${n + 2}`, 'Duplicate region membership.')
          regions.set(key, vals[n])
        })
        if (a.counts === 'total') rows.forEach((r, n) => {
          const members = (r[xi] ?? '').trim().split('&').map((v) => v.trim())
          if (members.length > 1) members.forEach((m) => {
            const total = regions.get(m)
            if (total === undefined) c.err(`data line ${n + 2}`, `counts=total requires the member set total for ${m}.`)
            else if (total !== null && vals[n] !== null && vals[n]! > total) c.err(`data line ${n + 2}`, `Intersection exceeds member set ${m}.`)
          })
        })
      }
    }
    const xd = {
      field: x,
      values: rows.map((r) => r[xi] ?? ''),
      numbers: a.form === 'scatter' ? rows.map((r, n) => num(r[xi], `data line ${n + 2}`, 'The x value (scatter needs numbers)')) : null,
    }
    const series = ys.map((y) => ({ field: y, values: rows.map((r, n) => num(r[header.indexOf(y)], `data line ${n + 2}`, `The ${y} value`)) }))
    // Stacked and capped bars are checked, never clipped: what cannot be drawn truthfully is an error.
    if (bar) rows.forEach((r, n) => {
      const where = `data line ${n + 2}`, cat = xd.values[n]
      const cells = series.map((s) => ({ field: s.field, v: s.values[n], raw: (r[header.indexOf(s.field)] ?? '').trim() })).filter((e) => e.v !== null)
      if (a.stack === 'true') {
        for (const e of cells) if (e.v! < 0) c.err(where, `${e.field} for “${cat}” is ${e.raw}. A stacked bar cannot hold a negative value; its segments run end to end from 0.`)
        const total = sumText(cells.map((e) => e.raw))
        if (max !== null && Number.isFinite(max) && Number(total) > max) c.err(where, `The stacked total for “${cat}” is ${total}, above max=${a.max}. Bars are never clipped: raise max or correct the values.`)
      } else if (max !== null && Number.isFinite(max)) for (const e of cells) {
        if (e.v! > max) c.err(where, `${e.field} for “${cat}” is ${e.raw}, above max=${a.max}. Bars are never clipped: raise max or correct the value.`)
        if (e.v! < 0) c.err(where, `${e.field} for “${cat}” is ${e.raw}, below 0. With max the value axis is 0..${a.max}.`)
      }
    })
    return { columns: header, rows, x: xd, series }
  },
}

export const padSpec: TypeSpec<string> = {
  type: 'pad',
  summary: 'An editable text surface. What you type is state; the Markdown keeps the starting text.',
  attrs: {
    title: { req: 'optional', says: 'a heading' },
    source: { req: 'optional', choices: ['none', 'conversation', 'refs'], says: 'material it may draw on (shown, never resolved)' },
    refs: { req: 'optional', says: 'items, when source=refs' },
  },
  body: 'the starting text (may be empty)',
  parse(body, a, c) {
    if (a.source === 'refs' && !a.refs) c.err('refs', 'source=refs needs refs=… listing the items it may use.')
    if (a.refs && a.source !== 'refs') c.err('refs', `refs is only allowed with source=refs (this block says source=${a.source ?? '(not given)'}).`)
    return body
  },
}
