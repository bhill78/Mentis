/* EXPERIMENTAL: table -- a data grid over a CSV body. The author declares
   which column identifies a row, whether rows may be chosen, and which
   columns the person may correct. Sorting, filtering, selection and edits
   are state; the Markdown keeps the rows as written. Numeric columns are
   detected mechanically (every non-empty cell is a number), never declared.

   AN EDITABLE TABLE IN A POST WITH A UNIQUE name= AND A key= IS KEPT BY
   MENTIS (../answers.ts, forms build P5b): each edited cell is saved when it
   is left, keyed by its row's key and its column, so sorting, filtering or
   reordering the rows keeps every edit on its row; under the person's name,
   with conflicts, history, own words and the status line (./kept.tsx).
   Sorting, filtering and selection stay in the tab: whether selection is
   saved is the owner's open choice (build plan C9). Any other table keeps its
   edits in the tab, and a posted editable one says why it is not saved. */
import { useState } from 'react'
import type { Help, MenuGroup, TypeDef } from '../api'
import type { Size } from '../spec/api'
import { q } from '../util'
import './data.css'
import { isNum, tableSpec, type TableData } from '../spec/table'
import { cellId } from '../spec/fill'
import type { Val } from '../spec/form'
import * as A from '../answers'
import { atField, doneWith, History, KeptFoot, KeptNotices, OwnWords, useKept, wordsLines } from './kept'

interface TableState {
  sort?: { col: string; dir: 'asc' | 'desc' }
  filter?: string
  /** Row ids, in source order. */
  selected?: string[]
  /** row id -> column -> the person's value (only where it differs from the source). */
  edits?: Record<string, Record<string, string>>
  /** Kept by Mentis instead of `edits`: cell values by `cellId(row, column)`. */
  values?: Record<string, Val>
  durable?: A.Durable
}

/** The person's value for a cell, where there is one: kept by Mentis, or held in the tab. */
const editOf = (s: TableState | undefined, id: string, col: string): string | undefined => {
  if (s?.durable) {
    const v = s.values?.[cellId(id, col)]
    return typeof v === 'string' ? v : undefined
  }
  return s?.edits?.[id]?.[col]
}

/** A cell as it is now: the person's edit if there is one, else the source. */
const cellNow = (d: TableData, s: TableState | undefined, r: number, c: number) =>
  editOf(s, d.ids[r], d.header[c]) ?? d.rows[r][c] ?? ''

/** Row indexes in view order: filtered by the text box, then sorted (stable). */
function viewOf(d: TableData, s: TableState | undefined): number[] {
  const f = (s?.filter ?? '').trim().toLowerCase()
  let idx = d.rows.map((_, i) => i)
  if (f) idx = idx.filter((r) => d.header.some((_, c) => cellNow(d, s, r, c).toLowerCase().includes(f)))
  const sc = s?.sort ? d.header.indexOf(s.sort.col) : -1
  if (sc >= 0) {
    const sign = s!.sort!.dir === 'asc' ? 1 : -1
    idx.sort((x, y) => {
      const a = cellNow(d, s, x, sc), b = cellNow(d, s, y, sc)
      // empty cells always last, whichever direction
      if (!a || !b) return (a ? 0 : 1) - (b ? 0 : 1) || x - y
      const cmp = d.numeric[sc] && isNum(a) && isNum(b) ? Number(a) - Number(b) : a.localeCompare(b, undefined, { numeric: true })
      return sign * cmp || x - y
    })
  }
  return idx
}

/** Every edit, in source row order, then column order. */
function editsOf(d: TableData, s: TableState | undefined) {
  const out: { row: string; r: number; column: string; source: string; now: string }[] = []
  d.rows.forEach((row, r) =>
    d.header.forEach((col, c) => {
      const v = editOf(s, d.ids[r], col)
      if (v !== undefined && v !== (row[c] ?? '')) out.push({ row: d.ids[r], r, column: col, source: row[c] ?? '', now: v })
    }),
  )
  return out
}

/** State left over for rows or columns the source no longer has (edited Markdown). */
function strays(d: TableData, s: TableState | undefined): string[] {
  const out: string[] = []
  for (const id of s?.selected ?? []) if (!d.ids.includes(id)) out.push(`selection of row ${q(id)}`)
  for (const [id, cols] of Object.entries(s?.durable ? {} : s?.edits ?? {}))
    for (const [col, v] of Object.entries(cols))
      if (!d.ids.includes(id) || !d.editable.includes(col)) out.push(`edit of row ${q(id)}, column ${q(col)} to ${q(v)}`)
  return out
}

/** Only a problem worth flagging: a non-number typed into a numeric column. */
const editProblem = (d: TableData, c: number, v: string) => (d.numeric[c] && v.trim() !== '' && !isNum(v.trim()) ? `“${v}” is not a number` : null)

/** Drop empty parts; no state at all means "as the source says". */
function tidy(s: TableState): TableState | undefined {
  const t: TableState = {}
  if (s.values) t.values = s.values
  if (s.durable) t.durable = s.durable
  if (s.sort) t.sort = s.sort
  if (s.filter) t.filter = s.filter
  if (s.selected?.length) t.selected = s.selected
  const edits = Object.fromEntries(Object.entries(s.edits ?? {}).filter(([, v]) => Object.keys(v).length))
  if (Object.keys(edits).length) t.edits = edits
  return Object.keys(t).length ? t : undefined
}

/* SIZED (L5). A workspace says what size a copy is drawn at; the
   conversation says nothing, and then the table is drawn exactly as it
   always was. compact: denser rows, the counts shortened, the grid scrolls
   within a bounded height. medium: today's table. large: roomier rows and a
   header that stays in view. Every row and control is there at every size. */
function TableView({ data: d, attrs, state: tab, set, mode, size, help, menu }: {
  data: TableData; attrs: Record<string, string>; state: TableState | undefined; set: (s: TableState | undefined) => void; mode: 'inline' | 'pin'; size?: Size
  help: Help; menu?: (g: MenuGroup[]) => void
}) {
  const key = help.key
  /* Only edited cells are saved; a table whose rows can only be chosen keeps to the tab, as selection does. */
  const fills = d.editable.length > 0
  const kept = useKept(help, attrs, 'table', !fills ? 'only its selection can change, and selection is kept in the tab'
    : attrs.key === undefined ? 'it has no key= column, which is what keeps an edit on its row' : null)
  const e = fills ? kept.e : null
  const why = fills ? kept.why : null
  const [history, setHistory] = useState(false)
  menu?.(e?.set ? [{ label: 'Answers', items: [{ label: 'History…', onSelect: () => setHistory(true) }] }] : [])
  /* What is drawn reads the kept cells; what is held in the tab is only the view. */
  const s: TableState | undefined = e
    ? { ...(tab ?? {}), durable: {} as A.Durable, values: Object.fromEntries(d.ids.flatMap((id, r) => d.editable.map((col) => {
        const c = d.header.indexOf(col)
        return [cellId(id, col), A.shownValue(e, cellId(id, col), d.rows[r][c] ?? '')]
      }))) }
    : tab
  const put = (patch: Partial<TableState>) => {
    const { values: _v, durable: _d, ...view } = { ...(tab ?? {}), ...patch }
    set(tidy(view))
  }
  const view = viewOf(d, s)
  const selected = new Set((s?.selected ?? []).filter((id) => d.ids.includes(id)))
  const choose = (id: string, on: boolean) => {
    if (d.select === 'one') return put({ selected: on ? [id] : [] })
    // keep source order so the state (and readable) read the same however it was clicked
    put({ selected: d.ids.filter((x) => (x === id ? on : selected.has(x))) })
  }
  const edit = (r: number, col: string, v: string) => {
    const id = d.ids[r]
    if (e) { A.draft(key, cellId(id, col), v); return }
    const row = { ...(s?.edits?.[id] ?? {}) }
    if (v === d.rows[r][d.header.indexOf(col)]) delete row[col]
    else row[col] = v
    put({ edits: { ...(s?.edits ?? {}), [id]: row } })
  }
  const cycleSort = (col: string) => {
    const now = s?.sort?.col === col ? s.sort.dir : null
    put({ sort: now === null ? { col, dir: 'asc' } : now === 'asc' ? { col, dir: 'desc' } : undefined })
  }
  const shownIds = view.map((r) => d.ids[r])
  const allShownChosen = shownIds.length > 0 && shownIds.every((id) => selected.has(id))
  const counts = [
    `${d.rows.length} row${d.rows.length === 1 ? '' : 's'}`,
    `${view.length} shown`,
    d.select !== 'none' && `${selected.size} selected`,
  ].filter(Boolean).join(', ')
  const shortCounts = `${view.length} of ${d.rows.length}`

  return (
    <div className={'rb-table' + (mode === 'pin' ? ' rb-table-pin' : '') + (size ? ` rb-table-${size}` : '')} {...(size ? { 'data-size': size } : {})}>
      <div className="rb-row rb-table-bar">
        <input
          className="rb-table-filter"
          type="search"
          placeholder="Filter rows…"
          aria-label="Filter rows"
          value={s?.filter ?? ''}
          onChange={(e) => put({ filter: e.target.value })}
        />
        <span className="rb-muted" title={size === 'compact' ? counts : undefined}>{size === 'compact' ? shortCounts : counts}</span>
        <span className="rb-grow" />
        {s?.sort && <button className="btn quiet" onClick={() => put({ sort: undefined })}>Source order</button>}
        {selected.size > 0 && <button className="btn quiet" onClick={() => put({ selected: [] })}>Clear selection</button>}
      </div>
      <KeptNotices e={e} why={why} blockKey={key} quiet what="table" />
      <div className="rb-table-scroll">
        <table className="rb-table-grid">
          <thead>
            <tr>
              {d.select !== 'none' && (
                <th className="rb-table-sel">
                  {d.select === 'many' && (
                    <input
                      type="checkbox"
                      aria-label="Select every shown row"
                      title="Select every shown row"
                      checked={allShownChosen}
                      onChange={(e) => {
                        const on = e.target.checked
                        put({ selected: d.ids.filter((x) => (shownIds.includes(x) ? on : selected.has(x))) })
                      }}
                    />
                  )}
                </th>
              )}
              {d.header.map((h, c) => {
                const dir = s?.sort?.col === h ? s.sort.dir : null
                return (
                  <th
                    key={h}
                    className={d.numeric[c] ? 'rb-table-n' : ''}
                    aria-sort={dir === 'asc' ? 'ascending' : dir === 'desc' ? 'descending' : 'none'}
                  >
                    <button className="rb-table-sort" onClick={() => cycleSort(h)} title="Sort: ascending, descending, source order">
                      {h}
                      {d.editable.includes(h) && <span className="rb-table-ed-mark" title="you may edit this column"> ✎</span>}
                      <span className="rb-table-arrow">{dir === 'asc' ? ' ▲' : dir === 'desc' ? ' ▼' : ''}</span>
                    </button>
                  </th>
                )
              })}
            </tr>
          </thead>
          <tbody>
            {view.map((r) => {
              const id = d.ids[r]
              const on = selected.has(id)
              return (
                <tr key={id} className={on ? 'rb-table-chosen' : ''}>
                  {d.select !== 'none' && (
                    <td className="rb-table-sel">
                      <input
                        type={d.select === 'one' ? 'radio' : 'checkbox'}
                        aria-label={`Select row ${id}`}
                        checked={on}
                        onChange={(e) => choose(id, d.select === 'one' ? true : e.target.checked)}
                        onClick={() => { if (d.select === 'one' && on) choose(id, false) }}
                      />
                    </td>
                  )}
                  {d.header.map((h, c) => {
                    const v = cellNow(d, s, r, c)
                    const src = d.rows[r][c] ?? ''
                    const changed = v !== src
                    const cls = [d.numeric[c] ? 'rb-table-n' : '', changed ? 'rb-table-edited' : ''].filter(Boolean).join(' ')
                    if (!d.editable.includes(h)) return <td key={h} className={cls}>{v}</td>
                    const p = editProblem(d, c, v)
                    const k = atField(e, key, cellId(id, h))
                    const said = changed ? `edited; source: ${src || '(empty)'}${p ? ` — ${p}` : ''}${k.who ? ` — ${k.who}` : ''}` : 'editable'
                    return (
                      <td key={h} className={cls + ' rb-table-editable' + (p ? ' rb-table-badcell' : '')} title={said} data-cell={cellId(id, h)}>
                        <input
                          className="rb-table-cell"
                          aria-label={`${h} for row ${id}`}
                          value={v}
                          disabled={!!e && (!e.read || !!e.set?.source_deleted)}
                          onChange={(ev) => edit(r, h, ev.target.value)}
                          onBlur={() => { if (e) void A.finish(key, cellId(id, h), src) }}
                          onKeyDown={(ev) => { if (e && ev.key === 'Enter') void A.finish(key, cellId(id, h), src) }}
                        />
                        {k.mark}
                        {k.says.length > 0 && <div className="rb-table-cellnote">{k.says}</div>}
                      </td>
                    )
                  })}
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
      {view.length === 0 && <p className="rb-muted">No row matches the filter.</p>}
      {e && <OwnWords e={e} blockKey={key} labelOf={(f) => {
        try { const [row, col] = JSON.parse(f) as [string, string]; return `${col} for row ${row}` } catch { return f }
      }} />}
      {e && <KeptFoot e={e} blockKey={key} onDone={() => void doneWith(key, Object.fromEntries(d.ids.flatMap((id, r) =>
        d.editable.map((col) => [cellId(id, col), d.rows[r][d.header.indexOf(col)] ?? ''])))) } />}
      {history && e && <History blockKey={key} answeredOnly onClose={() => setHistory(false)}
        fields={d.ids.flatMap((id) => d.editable.map((col) => ({ id: cellId(id, col), label: `${col} for row ${id}` })))} />}
    </div>
  )
}

const md = (v: string) => v.replace(/\\/g, '\\\\').replace(/\|/g, '\\|').replace(/\n/g, ' ')

export const table: TypeDef<TableData, TableState> = {
  ...tableSpec,
  Rich: (p) => <TableView {...p} />,
  readable(d, a, s) {
    const out: string[] = []
    if (a.title) out.push(`title: ${q(a.title)}`)
    out.push(d.keyed ? `rows are identified by the key column ${q(a.key)}` : 'no key column: rows are identified by position (#1 is the first data row)')
    out.push(`selection: ${d.select}${d.select === 'none' ? ' (rows cannot be chosen)' : ' (x in the “selected” column marks a chosen row)'}`)
    out.push(`editable columns: ${d.editable.length ? d.editable.map((x) => q(x)).join(', ') : '(none)'}`)
    const nums = d.header.filter((_, i) => d.numeric[i])
    if (nums.length) out.push(`numeric columns (detected): ${nums.map((x) => q(x)).join(', ')}`)
    const view = viewOf(d, s)
    const vparts = [s?.sort ? `sorted by ${q(s.sort.col)} ${s.sort.dir === 'asc' ? 'ascending' : 'descending'}` : 'source order']
    if (s?.filter) vparts.push(`filter ${q(s.filter)} (${view.length} of ${d.rows.length} rows match)`)
    out.push(`the person's view: ${vparts.join('; ')}. The table below is in source order, with every row.`)
    const selected = new Set(s?.selected ?? [])
    const cols = [...(d.select !== 'none' ? ['selected'] : []), ...(d.keyed ? [] : ['row']), ...d.header]
    out.push('| ' + cols.map(md).join(' | ') + ' |')
    out.push('|' + ' --- |'.repeat(cols.length))
    d.rows.forEach((row, r) => {
      const cells = d.header.map((_, c) => {
        const now = cellNow(d, s, r, c), src = row[c] ?? ''
        return now === src ? md(now) : `${md(now)} (edited; source ${md(q(src))})`
      })
      const lead = [...(d.select !== 'none' ? [selected.has(d.ids[r]) ? 'x' : ''] : []), ...(d.keyed ? [] : [d.ids[r]])]
      out.push('| ' + [...lead, ...cells].join(' | ') + ' |')
    })
    if (d.select !== 'none') {
      const chosen = d.ids.filter((id) => selected.has(id))
      out.push(`selected (${chosen.length}): ${chosen.length ? chosen.map((x) => q(x)).join(', ') : '(none)'}`)
    }
    const edits = editsOf(d, s)
    const dur = s?.durable
    if (d.editable.length) {
      if (dur) out.push('edits: kept by Mentis, each under the name of whoever made it')
      out.push(`edits (${edits.length}):${edits.length ? '' : ' (none)'}`)
      for (const e of edits) {
        const p = editProblem(d, d.header.indexOf(e.column), e.now)
        const by = dur?.by[cellId(e.row, e.column)]
        out.push(`- row ${q(e.row)}, column ${q(e.column)}: ${q(e.source)} -> ${q(e.now)}${p ? ` (${p})` : ''}${by ? ` (by ${by})` : ''}`)
      }
      for (const [f, cs] of Object.entries(dur?.conflicts ?? {})) {
        const [row, col] = JSON.parse(f) as [string, string]
        out.push(`- row ${q(row)}, column ${q(col)}: two answers disagree: ${cs.map((c) => `${q(String(c.value))} by ${c.by}`).join('; ')}`)
      }
    }
    const st = strays(d, s)
    if (st.length) out.push(`state held for rows/columns no longer in the source (ignored): ${st.join('; ')}`)
    out.push(...wordsLines(dur))
    if (dur) out.push(`saved: ${dur.status || 'nothing answered yet'}`)
    return out.join('\n')
  },
  handoff(d, _a, s) {
    const obj = (r: number) => Object.fromEntries(d.header.map((h, c) => [h, cellNow(d, s, r, c)]))
    const selected = new Set(s?.selected ?? [])
    const edits = editsOf(d, s)
    const out: Record<string, unknown> = {
      table_view: { sort: s?.sort ?? null, filter: s?.filter ?? '', rows_total: d.rows.length, rows_shown: viewOf(d, s).length },
    }
    if (d.select !== 'none')
      out.table_selected_rows = d.rows.map((_, r) => r).filter((r) => selected.has(d.ids[r])).map((r) => ({ row: d.ids[r], ...obj(r) }))
    if (d.editable.length) {
      out.table_edits = edits.map((e) => ({ row: e.row, column: e.column, source: e.source, now: e.now }))
      const bad = edits.flatMap((e) => {
        const p = editProblem(d, d.header.indexOf(e.column), e.now)
        return p ? [`row ${e.row}, ${e.column}: ${p}`] : []
      })
      if (bad.length) out.table_edit_problems = bad
    }
    const st = strays(d, s)
    if (st.length) out.table_orphaned_state = st
    return out
  },
}
