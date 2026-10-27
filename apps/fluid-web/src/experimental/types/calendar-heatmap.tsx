import { useRef, useState, type KeyboardEvent } from 'react'
import type { TypeDef } from '../api'
import './calendar-heatmap.css'
import { DAY, calendarHeatmapSpec, isoDay, type CalendarData } from '../spec/calendar-heatmap'

export { dateDay, isoDay } from '../spec/calendar-heatmap'

export function calendarLevel(value: number, min: number, max: number): number {
  return max === min ? 0 : Math.min(4, Math.floor(5 * Math.max(0, (value - min) / (max - min))))
}
// Roving focus: day i sits in week column floor((i + offset) / 7) at weekday (i + offset) % 7.
export function calendarMove(key: string, i: number, count: number, offset: number): number {
  const weekday = (i + offset) % 7
  const next = key === 'ArrowUp' ? (weekday > 0 ? i - 1 : i) : key === 'ArrowDown' ? (weekday < 6 ? i + 1 : i)
    : key === 'ArrowLeft' ? i - 7 : key === 'ArrowRight' ? i + 7 : key === 'Home' ? 0 : key === 'End' ? count - 1 : i
  return next >= 0 && next < count ? next : i
}

export const calendarHeatmap: TypeDef<CalendarData, never> = {
  ...calendarHeatmapSpec,
  Rich({ data: d }) {
    const [focused, setFocused] = useState('Focus or tap a day to see its date and value.')
    const offset = new Date(d.start).getUTCDay()
    const days = Array.from({ length: Math.round((d.end - d.start) / DAY) + 1 }, (_, i) => d.start + i * DAY)
    const [chosen, setActive] = useState(() => Math.max(0, days.findIndex(t => d.values[isoDay(t)] !== undefined)))
    const active = Math.min(chosen, days.length - 1) // an edited, shorter range keeps one Tab stop
    const grid = useRef<HTMLDivElement>(null)
    const onKeyDown = (e: KeyboardEvent) => {
      if (!['ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(e.key)) return
      e.preventDefault()
      grid.current?.querySelector<HTMLElement>(`[data-day="${calendarMove(e.key, active, days.length, offset)}"]`)?.focus()
    }
    const months = new Map<number, string>()
    days.forEach((t, i) => {
      if (i === 0 || new Date(t).getUTCDate() === 1) months.set(Math.floor((i + offset) / 7) + 2, isoDay(t))
    })
    return <div className="rb-calendar">
      <div className="rb-calendar-range">{isoDay(d.start)} through {isoDay(d.end)} (inclusive)</div>
      <div className="rb-calendar-scroll">
        <div ref={grid} role="grid" aria-label="Daily activity calendar, weeks as columns. Arrow keys move between days; Home and End go to the first and last day." aria-readonly="true" onKeyDown={onKeyDown} className="rb-calendar-days" style={{ gridTemplateColumns: `32px repeat(${Math.ceil((days.length + offset) / 7)}, 22px)` }}>
          {[...months].map(([col, date]) => <span key={date} aria-hidden="true" title={date.slice(0, 7)} className="rb-calendar-month" style={{ gridColumn: col, gridRow: 1 }}>{['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'][Number(date.slice(5, 7)) - 1]}</span>)}
          {['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'].map((weekday, row) => <div role="row" className="rb-calendar-row" key={weekday}>
            <span role="rowheader" className="rb-calendar-weekday" style={{ gridColumn: 1, gridRow: row + 2 }}>{weekday}</span>
            {days.map((t, i) => {
              if ((i + offset) % 7 !== row) return null
              const date = isoDay(t), value = d.values[date], col = Math.floor((i + offset) / 7) + 2
              const label = `${date}: ${value === undefined ? 'missing (no value declared)' : value}`
              return <div role="gridcell" key={date} data-day={i} aria-colindex={col} tabIndex={i === active ? 0 : -1} onFocus={() => { setActive(i); setFocused(label) }} onClick={() => setFocused(label)} aria-label={label} title={label} className={`rb-calendar-cell ${value === undefined ? 'rb-calendar-empty' : `rb-calendar-level-${calendarLevel(value, d.min, d.max)}`}`} style={{ gridColumn: col, gridRow: row + 2 }}>{value === undefined ? '' : value === 0 ? '0' : '•'}</div>
            })}
          </div>)}
        </div>
      </div>
      <div className="rb-calendar-caption" aria-live="polite">{focused}</div>
      <div className="rb-calendar-legend" aria-label={Object.keys(d.values).length ? `Sequential scale from ${d.min} to ${d.max}` : 'No numeric values declared'}>
        <span className="rb-calendar-missing-key"><span className="rb-calendar-empty rb-calendar-key" aria-hidden="true" /> Missing</span><span>0 = declared zero; • = declared activity</span>
        {Object.keys(d.values).length > 0 && <span className="rb-calendar-scale"><span>{d.min}</span>{(d.min === d.max ? [0] : [0, 1, 2, 3, 4]).map(n => <span key={n} className={`rb-calendar-key rb-calendar-level-${n}`} aria-hidden="true" />)}<span>{d.max}</span></span>}
      </div>
    </div>
  },
  readable(d) { return `Range: ${isoDay(d.start)} through ${isoDay(d.end)} (inclusive). Missing days are unknown, not zero.\n${Object.keys(d.values).length ? `Sequential scale: ${d.min} to ${d.max}.` : 'No numeric values declared.'}\n` + Object.entries(d.values).sort().map(([date, value]) => `${date}: ${value}`).join('\n') },
}
