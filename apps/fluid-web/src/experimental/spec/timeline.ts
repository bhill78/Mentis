/* EXPERIMENTAL: the reading half of timeline (drawn in ../types/timeline.tsx). */
import type { TypeSpec } from './api'
import { csvTable } from '../util'

export type Prec = 'year' | 'month' | 'day' | 'minute'

export interface Ev {
  /** Written date + label: stable when rows are reordered or added. */
  id: string
  row: number
  start: number
  /** Exclusive end of a span, or null for a single moment. */
  end: number | null
  from: string
  until: string
  label: string
  lane: string
  detail: string
  parents?: string[]
  extra: [string, string][]
  prec: Prec
}

export interface TL { events: Ev[]; lanes: string[]; cols: Record<string, string>; min: number; max: number }

export const DATE = /^(\d{4})(?:-(\d{2})(?:-(\d{2})(?:[T ](\d{2}):(\d{2}))?)?)?$/

/** A written date, as its first instant and the first instant after it. */
export function readDate(s: string): { t: number; next: number; prec: Prec } | string {
  const m = DATE.exec(s.trim())
  if (!m) return `“${s}” is not a date I can read. Write YYYY-MM-DD (e.g. 2026-03-05), YYYY-MM, YYYY or YYYY-MM-DDTHH:MM.`
  const y = +m[1], mo = m[2] ? +m[2] : 1, d = m[3] ? +m[3] : 1, h = m[4] ? +m[4] : 0, mi = m[5] ? +m[5] : 0
  if (mo < 1 || mo > 12) return `“${s}”: there is no month ${m[2]}.`
  if (h > 23 || mi > 59) return `“${s}”: ${m[4]}:${m[5]} is not a time of day.`
  const t = Date.UTC(y, mo - 1, d, h, mi)
  if (new Date(t).getUTCDate() !== d) return `“${s}”: ${m[1]}-${m[2]} has no day ${m[3]}.`
  const prec: Prec = m[4] ? 'minute' : m[3] ? 'day' : m[2] ? 'month' : 'year'
  const next = prec === 'year' ? Date.UTC(y + 1, 0, 1) : prec === 'month' ? Date.UTC(y, mo, 1) : prec === 'day' ? Date.UTC(y, mo - 1, d + 1) : t
  return { t, next, prec }
}

export const timelineSpec: TypeSpec<TL | null> = {
  type: 'timeline',
  summary: 'Dated events on a time axis, in lanes. Select an event for its detail; zoom and pan; notes are state.',
  attrs: {
    title: { req: 'optional', says: 'a heading' },
    when: { req: 'optional', says: 'the column holding the date (default: date)' },
    what: { req: 'optional', says: 'the column holding the event text (default: event)' },
    until: { req: 'optional', says: 'a column holding an end date, for spans (empty cell = a single moment)' },
    group: { req: 'optional', says: 'a column naming the lane each event goes in' },
    id: { req: 'optional', says: 'column holding unique event ids; required with parents=' },
    parents: { req: 'optional', says: 'explicit column of prerequisite ids, separated by semicolons or commas; resolves only against id=' },
    detail: { req: 'optional', says: 'a column with longer text shown when an event is selected' },
  },
  body: 'CSV: a header row, then one event per row; dates as YYYY-MM-DD, YYYY-MM, YYYY or YYYY-MM-DDTHH:MM',
  parse(body, a, c) {
    const t = csvTable(body, c.err, 'events')
    if (!t) return null
    const { header, rows } = t
    const cols: Record<string, string> = {}
    let bad = false
    const col = (k: string, dflt?: string) => {
      const name = a[k] ?? dflt
      if (name === undefined) return -1
      cols[k] = name
      const i = header.indexOf(name)
      if (i >= 0) return i
      bad = true
      c.err(k, a[k] === undefined
        ? `There is no “${name}” column. Call that column “${name}”, or name it with ${k}=<column>. The columns are: ${header.join(', ')}.`
        : `${k} names the column “${name}”, but the columns are: ${header.join(', ')}.`)
      return -1
    }
    const wi = col('when', 'date'), li = col('what', 'event'), ui = col('until'), gi = col('group'), di = col('detail'), pi = col('parents'), ii = col('id')
    if (a.parents && !a.id) c.err('id', 'parents= requires id= naming the unique dependency key column.')
    if (bad) return null
    const used = [wi, li, ui, gi, di, pi, ii]
    const events: Ev[] = [], lanes: string[] = [], seen: Record<string, number> = {}
    rows.forEach((r, n) => {
      const where = `data line ${n + 2}`
      const cell = (i: number) => (i >= 0 ? (r[i] ?? '').trim() : '')
      const from = cell(wi), label = cell(li), until = cell(ui)
      if (!from) { c.err(where, `The date (column “${cols.when}”) is empty.`); return }
      const s = readDate(from)
      if (typeof s === 'string') { c.err(where, s); return }
      if (!label) c.err(where, `The event text (column “${cols.what}”) is empty.`)
      let end: number | null = null
      if (until) {
        const u = readDate(until)
        if (typeof u === 'string') { c.err(where, `until: ${u}`); return }
        if (u.t < s.t) { c.err(where, `This event ends (${until}) before it starts (${from}).`); return }
        end = Math.max(u.next, s.t)
      }
      const lane = gi >= 0 ? cell(gi) || '(no group)' : ''
      if (!lanes.includes(lane)) lanes.push(lane)
      const base = `${from}|${label}`
      seen[base] = (seen[base] ?? 0) + 1
      const pcell = cell(pi)
      const parentList = pcell ? pcell.split(/[,;]/).map((p) => p.trim()).filter(Boolean) : undefined
      events.push({
        id: ii >= 0 ? cell(ii) : seen[base] > 1 ? `${base} #${seen[base]}` : base,
        row: n, start: s.t, end: end !== null && end > s.t ? end : null, from, until, label, lane,
        detail: cell(di), prec: s.prec, parents: parentList,
        extra: header.map((h, i) => [h, (r[i] ?? '').trim()] as [string, string]).filter(([, v], i) => !used.includes(i) && v !== ''),
      })
    })
    if (ii >= 0) {
      const ids = new Set<string>()
      events.forEach((e) => {
        if (!e.id || ids.has(e.id)) c.err(`data line ${e.row + 2}`, 'Event ids must be non-empty and unique (duplicate/ambiguous id).')
        ids.add(e.id)
      })
      events.forEach((e) => e.parents?.forEach((p) => {
        if (p === e.id) c.err(`data line ${e.row + 2}`, 'An event cannot be its own parent.')
        else if (!ids.has(p)) c.err(`data line ${e.row + 2}`, `Unresolved parent id: ${p}.`)
      }))
      const parentMap = new Map<string, string[]>()
      events.forEach((e) => {
        if (e.id && e.parents) parentMap.set(e.id, e.parents)
      })
      const active = new Set<string>(), done = new Set<string>()
      const hasCycle = (id: string): boolean => {
        if (active.has(id)) return true
        if (done.has(id)) return false
        active.add(id)
        const ps = parentMap.get(id) ?? []
        for (const p of ps) {
          if (ids.has(p) && hasCycle(p)) return true
        }
        active.delete(id)
        done.add(id)
        return false
      }
      for (const e of events) {
        if (e.id && hasCycle(e.id)) {
          c.err(`data line ${e.row + 2}`, 'Timeline dependencies cannot contain a cycle.')
          break
        }
      }
    }
    if (!events.length) return null
    events.sort((x, y) => x.start - y.start || x.row - y.row)
    return {
      events, lanes, cols,
      min: Math.min(...events.map((e) => e.start)),
      max: Math.max(...events.map((e) => e.end ?? e.start)),
    }
  },
}
