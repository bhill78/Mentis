import type { TypeDef } from '../api'
import './status-grid.css'
import { statusGridSpec, type GridData } from '../spec/status-grid'

export function statusClass(d: GridData, index: number): string {
  return `rb-status-${d.tones?.some(Boolean) ? d.tones[index] ?? 'neutral' : index}`
}
export const statusGrid: TypeDef<GridData, never> = {
  ...statusGridSpec,
  Rich({ data: d }) {
    return <div className="rb-status-grid">
      <div className="rb-status-scroll" tabIndex={0} aria-label="Status grid; scroll horizontally for more columns">
        <table className="rb-status-table"><thead><tr><th scope="col">{d.corner}</th>{d.columns.map(col => <th scope="col" key={col}>{col}</th>)}</tr></thead>
          <tbody>{d.rows.map((row, ri) => <tr key={row}><th scope="row">{row}</th>{d.columns.map((col, ci) => {
            const cell = d.cells[ri][ci], label = `${row} / ${col}: ${cell.label}; ${cell.state}`
            return <td key={col} aria-label={label} title={label} className={statusClass(d, d.states.indexOf(cell.state))}><span>{cell.label}</span><strong>{cell.state}</strong></td>
          })}</tr>)}</tbody>
        </table>
      </div>
      <div className="rb-status-legend" aria-label="Declared category key">{d.states.map((state, i) => <span className={statusClass(d, i)} key={state}>{state}</span>)}</div>
    </div>
  },
  readable(d) { return `Declared states: ${JSON.stringify(d.states.map((label, i) => d.tones?.[i] ? { label, tone: d.tones[i] } : label))}\n` + d.rows.flatMap((row, ri) => d.columns.map((col, ci) => `${JSON.stringify(row)} / ${JSON.stringify(col)}: ${JSON.stringify(d.cells[ri][ci])}`)).join('\n') },
}
