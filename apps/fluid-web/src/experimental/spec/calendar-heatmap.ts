/* EXPERIMENTAL: the reading half of calendar-heatmap (drawn in ../types/calendar-heatmap.tsx). */
import type { TypeSpec } from './api'
import { csvRows } from '../util'

export const DAY = 86400000

export const isoDay = (t: number) => new Date(t).toISOString().slice(0, 10)

export function dateDay(s: string): number | null {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(s)) return null
  const t = Date.parse(s + 'T00:00:00Z')
  return Number.isFinite(t) && isoDay(t) === s ? t : null
}

export interface CalendarData { start: number; end: number; values: Record<string, number>; min: number; max: number }

export const calendarHeatmapSpec: TypeSpec<CalendarData> = {
  type: 'calendar-heatmap',
  summary: 'Declared daily activity, with missing days kept separate from zero.',
  attrs: {
    title: { req: 'optional', says: 'a heading' },
    start: { req: 'optional', says: 'inclusive YYYY-MM-DD range start; otherwise earliest entry' },
    end: { req: 'optional', says: 'inclusive YYYY-MM-DD range end; otherwise latest entry' },
  },
  body: 'CSV, one row per line, with exactly date,value columns. Unique YYYY-MM-DD dates and nonnegative numbers; header alone requires start and end.',
  parse(body, a, c) {
    const csvLine = /^(?:[^",\r\n]*|"(?:[^"]|"")*")(?:,(?:[^",\r\n]*|"(?:[^"]|"")*"))*$/
    body.trim().split(/\r?\n/).forEach((line, i) => {
      if (!csvLine.test(line)) c.err(`line ${i + 1}`, 'Malformed CSV quoting; use one row per line and double embedded quotes.')
    })
    const csv = csvRows(body.trim())
    const header = csv[0]?.map(v => v.trim()) ?? []
    const rows = csv.slice(1)
    const values: Record<string, number> = Object.create(null)
    const dates: number[] = []
    if (header.length !== 2 || header[0] !== 'date' || header[1] !== 'value') c.err('header', 'Use exactly date,value as the CSV header.')
    if (rows.length > 3660) c.err('body', 'At most 3660 entries are supported.')
    for (const [i, row] of rows.slice(0, 3660).entries()) {
      if (row.length !== 2) c.err(`row ${i + 2}`, 'Each row needs exactly a date and value.')
      const date = row[0]?.trim() ?? '', raw = row[1]?.trim() ?? ''
      const day = dateDay(date), value = Number(raw)
      if (day === null) c.err(`row ${i + 2}`, 'Use a real date in YYYY-MM-DD form.')
      if (!raw || !/^(?:\d+(?:\.\d*)?|\.\d+)(?:e[+-]?\d+)?$/i.test(raw) || !Number.isFinite(value) || value < 0 || value > 1e12)
        c.err(`row ${i + 2}`, 'Activity must be a nonnegative finite decimal number, at most 1e12; omit missing days.')
      if (date in values) c.err(`row ${i + 2}`, `Duplicate date ${date}; declare each date once.`)
      values[date] = value
      if (day !== null) dates.push(day)
    }
    const start = a.start === undefined ? (dates.length ? Math.min(...dates) : null) : dateDay(a.start)
    const end = a.end === undefined ? (dates.length ? Math.max(...dates) : null) : dateDay(a.end)
    if ((a.start !== undefined && dateDay(a.start) === null) || (a.end !== undefined && dateDay(a.end) === null))
      c.err('range', 'Use real YYYY-MM-DD dates for start and end.')
    else if (rows.length === 0 && (start === null || end === null)) c.err('range', 'Declare valid start and end dates when there are no entries.')
    if (start !== null && end !== null) {
      if (end < start || (end - start) / DAY >= 3660) c.err('range', 'Range must be ordered and at most 3660 days inclusive.')
      if (dates.some(d => d < start || d > end)) c.err('range', 'Every entry must be inside the declared range.')
    }
    const nums = Object.values(values)
    return { start: start ?? 0, end: end ?? 0, values, min: nums.length ? Math.min(...nums) : 0, max: nums.length ? Math.max(...nums) : 0 }
  },
}
