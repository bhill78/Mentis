import { useRef, useState, type KeyboardEvent } from 'react'
import type { TypeDef } from '../api'
import './matrix-heatmap.css'
import { matrixHeatmapSpec, type MatrixData } from '../spec/matrix-heatmap'

export function matrixPosition(value: number, min: number, max: number, midpoint?: number): number {
  if (midpoint !== undefined) {
    const extent = Math.max(Math.abs(min - midpoint), Math.abs(max - midpoint))
    return extent === 0 ? 0.5 : 0.5 + 0.5 * ((value - midpoint) / extent)
  }
  return min === max ? 0 : (value - min) / (max - min)
}
export function matrixLevel(value: number, min: number, max: number, midpoint?: number): number {
  const position = matrixPosition(value, min, max, midpoint)
  const level = midpoint === undefined ? Math.floor(position * 5)
    : 2 + Math.sign(value - midpoint) * Math.round(Math.abs(position - 0.5) * 4)
  return Math.max(0, Math.min(4, level))
}
// Roving focus: arrows move by row/column; Home/End within the row, Ctrl+Home/End to the corners.
export function matrixMove(key: string, ctrl: boolean, r: number, c: number, rows: number, cols: number): [number, number] {
  const [nr, nc] = key === 'ArrowUp' ? [r - 1, c] : key === 'ArrowDown' ? [r + 1, c] : key === 'ArrowLeft' ? [r, c - 1] : key === 'ArrowRight' ? [r, c + 1]
    : key === 'Home' ? [ctrl ? 0 : r, 0] : key === 'End' ? [ctrl ? rows - 1 : r, cols - 1] : [r, c]
  return nr >= 0 && nr < rows && nc >= 0 && nc < cols ? [nr, nc] : [r, c]
}
export const matrixHeatmap: TypeDef<MatrixData, never> = {
  ...matrixHeatmapSpec,
  Rich({ data: d }) {
    const [focused, setFocused] = useState('Focus or tap a cell to see its value.')
    const hasNumbers = d.cells.some(row => row.some(value => value !== null))
    const [chosen, setActive] = useState(() => {
      const r = d.cells.findIndex(row => row.some(value => value !== null))
      return r < 0 ? [0, 0] : [r, d.cells[r].findIndex(value => value !== null)]
    })
    // an edited, smaller matrix keeps one Tab stop
    const active = chosen[0] < d.rows.length && chosen[1] < d.cols.length ? chosen : [0, 0]
    const table = useRef<HTMLTableElement>(null)
    const onKeyDown = (e: KeyboardEvent) => {
      if (!['ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(e.key)) return
      e.preventDefault()
      const [r, c] = matrixMove(e.key, e.ctrlKey || e.metaKey, active[0], active[1], d.rows.length, d.cols.length)
      table.current?.querySelector<HTMLElement>(`[data-cell="${r},${c}"]`)?.focus()
    }
    const extent = d.midpoint === undefined ? 0 : Math.max(Math.abs(d.min - d.midpoint), Math.abs(d.max - d.midpoint))
    return <div className="rb-matrix">
      <div className="rb-matrix-scroll">
        <table ref={table} role="grid" aria-label="Matrix heat map. Arrow keys move between cells; Home and End go to the first and last cell in the row." aria-readonly="true" onKeyDown={onKeyDown} className="rb-matrix-table"><thead><tr><th scope="col">{d.corner}</th>{d.cols.map(col => <th key={col} scope="col">{col}</th>)}</tr></thead>
          <tbody>{d.rows.map((row, r) => <tr key={row}><th scope="row">{row}</th>{d.cols.map((col, ci) => {
            const value = d.cells[r][ci], missing = value === null
            const level = missing ? '' : matrixLevel(value, d.min, d.max, d.midpoint)
            const label = `${row} / ${col}: ${missing ? 'missing (no value declared)' : value}`
            return <td key={col} role="gridcell" data-cell={`${r},${ci}`} tabIndex={r === active[0] && ci === active[1] ? 0 : -1} onFocus={() => { setActive([r, ci]); setFocused(label) }} onClick={() => setFocused(label)} title={label} aria-label={label} className={missing ? 'rb-matrix-missing' : `rb-matrix-${d.midpoint === undefined ? 'seq' : 'div'}-${level}`}>{missing ? '–' : d.labels ? value : '•'}</td>
          })}</tr>)}</tbody>
        </table>
      </div>
      <div className="rb-matrix-caption" aria-live="polite">{focused}</div>
      <div className="rb-matrix-legend"><span>– Missing</span>{hasNumbers ? <><span>{d.midpoint === undefined ? 'Sequential' : 'Diverging distance'}:</span><span className="rb-matrix-scale"><span>{d.midpoint === undefined ? d.min : -extent}</span>
        {(d.min === d.max ? [matrixLevel(d.min, d.min, d.max, d.midpoint)] : [0, 1, 2, 3, 4]).map(level => <span aria-hidden="true" key={level} className={`rb-matrix-swatch rb-matrix-${d.midpoint === undefined ? 'seq' : 'div'}-${level}`} />)}
        <span>{d.midpoint === undefined ? d.max : extent}</span></span>{d.midpoint !== undefined && <span>Midpoint {d.midpoint}; declared {d.min} to {d.max}</span>}</> : <span>No numeric values declared.</span>}
        {!d.labels && <span>• Declared value (focus or tap for value)</span>}
      </div>
    </div>
  },
  readable(d) { return (d.cells.some(row => row.some(v => v !== null)) ? `${d.midpoint === undefined ? 'Sequential' : 'Diverging'} scale: ${d.min} to ${d.max}${d.midpoint === undefined ? '' : `, midpoint ${d.midpoint}`}.\n` : 'No numeric values declared.\n') + d.rows.flatMap((r, ri) => d.cols.map((col, ci) => `${JSON.stringify(r)} / ${JSON.stringify(col)}: ${d.cells[ri][ci] === null ? 'missing' : d.cells[ri][ci]}`)).join('\n') },
}
