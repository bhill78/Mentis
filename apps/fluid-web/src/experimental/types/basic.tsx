/* EXPERIMENTAL: checklist, chart and pad -- the three types the owner has
   already used, ported unchanged in behaviour into the TypeDef shape.

   A CHECKLIST OR PAD IN A POST WITH A UNIQUE name= IS KEPT BY MENTIS
   (../answers.ts, forms build P5b), as a form is: a tick is saved when it is
   made, keyed by the item's TEXT (so moving an item keeps its tick), and a
   pad's text when the box is left; each under the person's name, with
   conflicts, history, own words and the status line (./kept.tsx). Any other
   checklist or pad keeps what is changed in the tab, positionally, and a
   posted one says why it is not saved. */
import type React from 'react'
import { useEffect, useId, useState } from 'react'
import type { MenuGroup, RichProps, TypeDef } from '../api'
import type { Size } from '../spec/api'
import { PALETTE, q } from '../util'
import { useWidth } from './graph'
import { BAR_ONLY, chartSpec, checklistSpec, padSpec, sumText, type ChartData, type Items } from '../spec/basic'
import { repeatedItems } from '../spec/fill'
import type { Val } from '../spec/form'
import * as A from '../answers'
import { atField, doneWith, History, KeptFoot, KeptNotices, OwnWords, useKept, wordsLines } from './kept'

/* ---------------------------------------------------------------- checklist */

/** Tab state: index -> tick, where it differs from the source. Kept by
 *  Mentis instead: `values` by item text, as the readable text reads it. */
type CheckState = Record<number, boolean> & { values?: Record<string, Val>; durable?: A.Durable }

const checkNow = (items: Items, s: CheckState | undefined) =>
  s?.durable
    ? items.map((it) => (s.values && it.text in s.values ? s.values[it.text] === true : it.checked))
    : items.map((it, i) => (s && i in s ? s[i] : it.checked))

function ChecklistView({ data, attrs, state, set, help, menu }: RichProps<Items, CheckState>) {
  const key = help.key
  const repeated = repeatedItems(data)
  const { e, why } = useKept(help, attrs, 'checklist',
    repeated.length ? `items repeat (${repeated.map((t) => `“${t}”`).join(', ')}), and ticks are saved by item text` : null)
  const [history, setHistory] = useState(false)
  menu?.(e?.set ? [{ label: 'Answers', items: [{ label: 'History…', onSelect: () => setHistory(true) }] }] as MenuGroup[] : [])
  const now = e ? data.map((it) => A.shownValue(e, it.text, it.checked) === true) : checkNow(data, state)
  const off = !!e && (!e.read || !!e.set?.source_deleted)
  const tick = (i: number, on: boolean) => {
    const it = data[i]
    if (e) {
      A.draft(key, it.text, on)
      void A.finish(key, it.text, it.checked)
      return
    }
    const s: Record<number, boolean> = { ...(state ?? {}) }
    if (on === it.checked) delete s[i]
    else s[i] = on
    set(Object.keys(s).length ? s : undefined)
  }
  return (
    <div className="rb-kept" data-saved={e ? 'mentis' : 'tab'}>
      <KeptNotices e={e} why={why} blockKey={key} quiet what="checklist" />
      <ul className="rb-check">
        {data.map((it, i) => {
          const k = atField(e, key, it.text)
          return (
            <li key={i} className={!e && now[i] !== it.checked ? 'rb-changed' : ''} data-item={it.text} title={k.who ?? undefined}>
              <label>
                <input type="checkbox" checked={now[i]} disabled={off} onChange={(ev) => tick(i, ev.target.checked)} />{' '}
                {it.text}
              </label>
              {k.mark}
              {k.says}
            </li>
          )
        })}
      </ul>
      {e && <OwnWords e={e} blockKey={key} labelOf={(id) => id} />}
      {e && <KeptFoot e={e} blockKey={key} onDone={() => void doneWith(key, Object.fromEntries(data.map((it) => [it.text, it.checked])))} />}
      {history && e && <History blockKey={key} fields={data.map((it) => ({ id: it.text, label: it.text }))} onClose={() => setHistory(false)} />}
    </div>
  )
}

export const checklist: TypeDef<Items, CheckState> = {
  ...checklistSpec,
  Rich: (p) => <ChecklistView {...p} />,
  readable(data, a, s) {
    const now = checkNow(data, s)
    const d = s?.durable
    const out = a.title ? [`title: ${q(a.title)}`] : []
    if (d) out.push('ticks: kept by Mentis, each under the name of whoever made it')
    data.forEach((it, i) => {
      const by = d?.conflicts[it.text] ? `   (two answers disagree: ${d.conflicts[it.text].map((c) => `${c.value ? 'done' : 'open'} by ${c.by}`).join('; ')})`
        : d?.by[it.text] ? `   (ticked ${now[i] ? 'done' : 'open'} by ${d.by[it.text]})` : ''
      out.push(`- [${now[i] ? 'x' : ' '}] ${it.text}${now[i] !== it.checked ? `   (changed; source says ${it.checked ? 'done' : 'open'})` : ''}${by}`)
    })
    out.push(...wordsLines(d))
    if (d) out.push(`saved: ${d.status || 'nothing answered yet'}`)
    return out.join('\n')
  },
  handoff(data, _a, s) {
    return { checklist_now: data.map((it, i) => `- [${checkNow(data, s)[i] ? 'x' : ' '}] ${it.text}`).join('\n') }
  },
}

/* -------------------------------------------------------------------- chart */

/** A bar that needs the stacked/horizontal/capped drawing; every other bar keeps the original one. */
const fancyBar = (a: Record<string, string>) => a.stack === 'true' || a.orient === 'horizontal' || 'max' in a

export const chart: TypeDef<ChartData | null, never> = {
  ...chartSpec,
  Rich: ChartRich,
  readable(data, a) {
    const d = data!
    const unit = (k: string) => (k in a ? `unit ${q(a[k])}` : 'unit (none stated)')
    const cell = (v: string) => v.replace(/\\/g, '\\\\').replace(/\|/g, '\\|')
    const out: string[] = []
    if ('title' in a) out.push(`title: ${q(a.title)}`)
    out.push(`form: ${a.form}`)
    if (a.form === 'venn') out.push(`sets: ${a.sets}; counts: ${a.counts ?? 'exclusive'}; schematic, not to scale`)
    out.push(`x axis: label ${q(a.x_label)}, column ${q(a.x)}, ${unit('x_unit')}`)
    out.push(`y axis: label ${q(a.y_label)}, ${unit('y_unit')}; series ${d.series.map((x) => q(x.field)).join(', ')}`)
    out.push('| ' + d.columns.map(cell).join(' | ') + ' |')
    out.push('|' + ' --- |'.repeat(d.columns.length))
    d.rows.forEach((r) => out.push('| ' + r.map(cell).join(' | ') + ' |'))
    if (a.form === 'bar' && fancyBar(a)) {
      const stack = a.stack === 'true'
      out.push(`bars: ${stack ? 'stacked (series end to end in one bar per row)' : 'grouped'}, ${a.orient === 'horizontal' ? 'horizontal (categories down the side, values along the bottom)' : 'vertical'}${'max' in a ? `; value axis fixed at 0..${a.max}, the rest of each bar left empty` : ''}`)
      if (stack) out.push('stacked totals (sum of the segments): ' + d.x.values.map((v, i) => `${v} ${sumText(d.series.map((s) => (d.rows[i][d.columns.indexOf(s.field)] ?? '').trim()))}`).join('; '))
    }
    if (a.form !== 'venn') {
      const unused: string[] = []
      if ('sets' in a) unused.push(`sets=${JSON.stringify(a.sets)}`)
      if ('counts' in a) unused.push(`counts=${JSON.stringify(a.counts)}`)
      if (a.form !== 'bar') for (const k of BAR_ONLY) if (k in a) unused.push(`${k}=${JSON.stringify(a[k])}`)
      if (unused.length) out.push('other attributes (not in the contract, kept, not used): ' + unused.join(' '))
    }
    return out.join('\n')
  },
  handoff(d, a) {
    return a.form === 'venn' ? { sets: a.sets.split(',').map((v) => v.trim()), counts: a.counts ?? 'exclusive', regions: d!.rows.map((r, i) => ({ members: d!.x.values[i].split('&').map((v) => v.trim()), value: r[d!.columns.indexOf(d!.series[0].field)] })) } : {}
  },
}

/* Presentation only: what is drawn comes from the declared attributes and the
   CSV, exactly as before. The look follows the post: muted theme colours,
   faint gridlines, round ticks, exact values on bars, and a drawing as wide
   as the column. It scrolls sideways only when the categories cannot fit
   at a readable size; it never shrinks text to make them. */

/* SIZED (L5). A workspace says what size a copy is drawn at: compact is a
   shorter plot, large a taller one, medium today's. The conversation says
   nothing, and the plot is exactly as it always was. The width is always the
   room the chart is given; only the height follows the size. */
const plotH = (W: number, size?: Size) =>
  size === 'compact' ? Math.round(Math.min(180, Math.max(120, W * 0.35)))
    : size === 'large' ? Math.round(Math.min(420, Math.max(240, W * 0.5)))
      : Math.round(Math.min(260, Math.max(170, W * 0.4)))
const sized = (size?: Size) => (size ? { 'data-size': size } : {})

/** Round ticks covering lo..hi: the tightest 1/2/2.5/5 step giving 2 to 5 intervals. */
function niceTicks(lo: number, hi: number): number[] {
  if (hi <= lo) hi = lo + 1
  let best: { a: number; b: number; s: number } | null = null
  const mag = Math.pow(10, Math.floor(Math.log10(hi - lo)) - 1)
  for (const m of [1, 10, 100]) for (const f of [1, 2, 2.5, 5]) {
    const s = f * m * mag, a = Math.floor(lo / s + 1e-9) * s, b = Math.ceil(hi / s - 1e-9) * s, n = Math.round((b - a) / s)
    if (n < 2 || n > 5) continue
    if (!best || b - a < best.b - best.a - 1e-9 || (Math.abs(b - a - (best.b - best.a)) < 1e-9 && s > best.s)) best = { a, b, s }
  }
  const { a, b, s } = best ?? { a: lo, b: hi, s: (hi - lo) / 4 }
  const out: number[] = []
  for (let v = a; v <= b + s / 2; v += s) out.push(+v.toPrecision(12))
  return out
}
const fmt = (v: number) => String(+v.toPrecision(6))
/** Width of a short run of chart text, estimated (tabular digits are about 0.6em). */
const textW = (s: string, size: number) => s.length * size * 0.6

/** A bar with its data end lightly rounded and its baseline end square. */
function barPath(x: number, w: number, y0: number, y1: number) {
  const h = Math.abs(y1 - y0), r = Math.min(2, w / 2, h)
  if (h === 0) return ''
  const s = y1 < y0 ? 1 : -1 // upward bars round their top, downward ones their bottom
  return `M${x},${y0}V${y1 + s * r}Q${x},${y1} ${x + r},${y1}H${x + w - r}Q${x + w},${y1} ${x + w},${y1 + s * r}V${y0}Z`
}

function ChartPieRich(props: RichProps<ChartData | null, never>) {
  const { data, attrs: a } = props
  const d = data!
  const [wrap, avail] = useWidth<HTMLDivElement>()
  const capId = useId()
  const yUnit = a.y_unit ? ` ${a.y_unit}` : ''
  const colour = (k: number) => (k < 4 ? `var(--rb-chart-${k + 1})` : PALETTE[k % PALETTE.length])

  const series0 = d.series[0]
  const declaredRows = d.x.values.map((label, i) => {
    const val = series0?.values[i] ?? null
    const rawVal = (d.rows[i][d.columns.indexOf(series0?.field ?? '')] ?? '').trim()
    return { label, val, raw: rawVal, i }
  }).filter((x): x is { label: string; val: number; raw: string; i: number } => x.val !== null && x.val >= 0)

  const rows = declaredRows.filter((r) => r.val > 0)
  const total = rows.reduce((acc, r) => acc + r.val, 0)
  const fit = avail || 560
  const W = Math.max(280, fit)
  const H = Math.min(300, Math.max(200, Math.round(W * 0.45)))
  const R = Math.min(Math.round(H * 0.38), 105)
  const cx = W < 420 ? Math.round(W / 2) : Math.min(Math.round(W * 0.35), R + 30)
  const cy = Math.round(H / 2)
  const name = a.title ?? `${a.y_label} by ${a.x_label}`

  const slices: React.ReactNode[] = []
  let angle = -Math.PI / 2

  if (rows.length === 1) {
    const r = rows[0]
    slices.push(
      <circle
        key="p0"
        className="rb-chart-mark"
        cx={cx}
        cy={cy}
        r={R}
        fill={colour(r.i)}
        stroke="var(--line)"
        strokeWidth={1}
        role="img"
        aria-label={`${r.label}: ${r.raw}${yUnit} (100%)`}
        tabIndex={0}
      >
        <title>{`${r.label}: ${r.raw}${yUnit} (100%)`}</title>
      </circle>,
      <text
        key="pt0"
        className="rb-chart-value"
        x={cx}
        y={cy + 4}
        fontSize={12}
        textAnchor="middle"
        aria-hidden="true"
      >
        100%
      </text>,
    )
  } else if (total > 0) {
    rows.forEach((r, idx) => {
      const frac = r.val / total
      const delta = frac * 2 * Math.PI
      const endAngle = angle + delta
      const x1 = cx + R * Math.cos(angle)
      const y1 = cy + R * Math.sin(angle)
      const x2 = cx + R * Math.cos(endAngle)
      const y2 = cy + R * Math.sin(endAngle)
      const large = delta > Math.PI ? 1 : 0
      const dPath = `M ${cx} ${cy} L ${x1.toFixed(2)} ${y1.toFixed(2)} A ${R} ${R} 0 ${large} 1 ${x2.toFixed(2)} ${y2.toFixed(2)} Z`
      const c = colour(r.i)
      const pct = (frac * 100).toFixed(1)
      const midAngle = angle + delta / 2
      const lx = cx + (R * 0.65) * Math.cos(midAngle)
      const ly = cy + (R * 0.65) * Math.sin(midAngle)

      slices.push(
        <path
          key={`slice${idx}`}
          className="rb-chart-mark"
          d={dPath}
          fill={c}
          stroke="var(--surface-sunken, #fff)"
          strokeWidth={1.5}
          role="img"
          aria-label={`${r.label}: ${r.raw}${yUnit} (${pct}%)`}
          tabIndex={0}
        >
          <title>{`${r.label}: ${r.raw}${yUnit} (${pct}%)`}</title>
        </path>,
      )
      if (frac >= 0.08) {
        slices.push(
          <text
            key={`stxt${idx}`}
            className="rb-chart-value"
            x={lx.toFixed(2)}
            y={(ly + 4).toFixed(2)}
            fontSize={11}
            textAnchor="middle"
            aria-hidden="true"
          >
            {Math.round(frac * 100)}%
          </text>,
        )
      }
      angle = endAngle
    })
  }

  return (
    <figure className="rb-chart-fig" {...sized(props.size)}>
      <figcaption className="rb-chart-cap">
        <span id={capId}>{name}</span>
        <ul className="rb-chart-legend" aria-label="Slices">
          {declaredRows.map((r) => {
            const frac = total > 0 ? (r.val / total) * 100 : 0
            return (
              <li key={r.i}>
                <span className="rb-chart-swatch" style={{ background: colour(r.i) }} aria-hidden="true" />
                <span>{r.label}: {r.raw}{yUnit} ({frac.toFixed(1)}%)</span>
              </li>
            )
          })}
        </ul>
      </figcaption>
      <div ref={wrap} className="rb-chart-scroll">
        <svg className="rb-chart" width={W} height={H} viewBox={`0 0 ${W} ${H}`} role="group" aria-label={`${name}, pie chart`} aria-describedby={capId}>
          {total <= 0 ? (
            <text x={W / 2} y={H / 2} textAnchor="middle" className="rb-chart-cat">No positive data to display</text>
          ) : (
            slices
          )}
        </svg>
      </div>
    </figure>
  )
}

function ChartVennRich({ data, attrs: a, size }: RichProps<ChartData | null, never>) {
  const d = data!
  const capId = useId()
  const sets = a.sets.split(',').map((v) => v.trim())
  const three = sets.length === 3
  const colour = (i: number) => `var(--rb-chart-${i + 1})`
  const centers = three ? [[150, 88], [108, 158], [192, 158]] : [[112, 130], [188, 130]]
  const positions: Record<string, number[]> = three
    ? { '0': [150, 47], '1': [72, 176], '2': [228, 176], '0,1': [109, 102], '0,2': [191, 102], '1,2': [150, 188], '0,1,2': [150, 133] }
    : { '0': [72, 130], '1': [228, 130], '0,1': [150, 130] }
  const vh = size === 'compact' ? 200 : size === 'large' ? 340 : 260
  return <figure className="rb-chart-fig rb-venn" {...sized(size)}>
    <figcaption id={capId}>{a.title ?? 'Venn diagram'} — schematic, not to scale. Counts: {a.counts === 'total' ? 'total (inclusive)' : 'per-region (exclusive)'}.</figcaption>
    <ul className="rb-chart-legend" aria-label="Declared sets">{sets.map((s, i) => <li key={i} title={s}><span className="rb-chart-swatch" style={{ background: colour(i) }} />{s}</li>)}</ul>
    <svg className="rb-chart" width="100%" height={vh} viewBox="0 0 300 260" role="group" aria-label="Schematic Venn regions" aria-describedby={capId}>
      {centers.map(([x, y], i) => <circle className="rb-chart-mark" key={i} cx={x} cy={y} r={76} fill={colour(i)} fillOpacity={0.18} stroke={colour(i)} strokeWidth={2}><title>{sets[i]}</title></circle>)}
      {d.rows.map((r, i) => {
        const members = d.x.values[i].split('&').map((v) => v.trim())
        const key = sets.map((s, k) => members.includes(s) ? k : -1).filter((k) => k >= 0).join(',')
        const [x, y] = positions[key]
        const raw = r[d.columns.indexOf(d.series[0].field)].trim()
        return <text key={i} className="rb-chart-value" x={x} y={y} textAnchor="middle" dominantBaseline="middle" tabIndex={0} role="img" aria-label={`${members.join(' & ')}: ${raw}`} fontSize={12}><title>{members.join(' & ')}: {raw}</title>{raw}</text>
      })}
    </svg>
    <ul className="rb-venn-regions" aria-label="Declared regions">{d.rows.map((r, i) => <li key={i}>{d.x.values[i]}: {r[d.columns.indexOf(d.series[0].field)]}{a.y_unit ? ` ${a.y_unit}` : ''}</li>)}</ul>
  </figure>
}

function ChartRich(props: RichProps<ChartData | null, never>) {
  const f = props.attrs.form
  return f === 'pie' ? <ChartPieRich {...props} /> : f === 'venn' ? <ChartVennRich {...props} />
    : f === 'bar' && fancyBar(props.attrs) ? <ChartBarRich {...props} /> : <ChartCartesianRich {...props} />
}

/** Ticks for an axis fixed at 0..max: round ticks up to max, and max itself as the last. */
function capTicks(max: number): number[] {
  const t = niceTicks(0, max).filter((v) => v <= max + 1e-9)
  if (t[t.length - 1] < max - 1e-9) {
    if (t.length > 2 && max - t[t.length - 1] < (t[1] - t[0]) * 0.4) t.pop() // too close to max to read
    t.push(max)
  }
  return t
}

/** A horizontal bar with its data end (x1) lightly rounded and its baseline end square. */
function hbarPath(y: number, h: number, x0: number, x1: number) {
  const w = Math.abs(x1 - x0), r = Math.min(2, h / 2, w)
  if (w === 0) return ''
  const s = x1 > x0 ? 1 : -1
  return `M${x0},${y}H${x1 - s * r}Q${x1},${y} ${x1},${y + r}V${y + h - r}Q${x1},${y + h} ${x1 - s * r},${y + h}H${x0}Z`
}
const rectPath = (x: number, y: number, w: number, h: number) => `M${x},${y}h${w}v${h}h${-w}Z`

/* form=bar with stack=true, orient=horizontal or max=N. Same marks, palette and
   value labels as the original bar; what is new is only where they go. A
   stacked bar puts its series end to end and labels the sum at the end of the
   fill; max fixes the value axis and leaves the rest of each bar as an empty
   track. Validation has already refused anything that would need clipping. */
function ChartBarRich(props: RichProps<ChartData | null, never>) {
  const { data, attrs: a } = props
  const d = data!
  const [wrap, avail] = useWidth<HTMLDivElement>()
  const capId = useId()
  const S = d.series.length, n = d.x.values.length
  const horiz = a.orient === 'horizontal', stack = a.stack === 'true'
  const max = 'max' in a ? Number(a.max) : null
  const unit = (k: string) => (a[k] ? ` (${a[k]})` : '')
  const yUnit = a.y_unit ? ` ${a.y_unit}` : ''
  const colour = (k: number) => (S === 1 ? 'var(--rb-chart-one)' : k < 4 ? `var(--rb-chart-${k + 1})` : PALETTE[k % PALETTE.length])
  const raw = (k: number, i: number) => (d.rows[i][d.columns.indexOf(d.series[k].field)] ?? '').trim()
  const totals = d.x.values.map((_, i) => sumText(d.series.map((_, k) => raw(k, i))))

  const all = stack ? totals.map(Number) : d.series.flatMap((x) => x.values).filter((v): v is number => v !== null)
  const vt = max !== null ? capTicks(max) : niceTicks(Math.min(0, ...all), Math.max(0, ...all))
  const lo = vt[0], hi = vt[vt.length - 1]

  // Room the words need, so the drawing can be sized to them and never they to it.
  const VS = S === 1 || stack ? 13 : 11, IS = 11, CS = 13, TS = 12
  const ends = stack ? totals : d.series.flatMap((_, k) => d.x.values.map((_, i) => raw(k, i)))
  const labelW = Math.max(0, ...ends.map((v) => textW(v, VS)))
  const catW = Math.max(0, ...d.x.values.map((v) => textW(v, CS)))
  const bars = stack ? 1 : S // bars per category
  const fit = avail || 560

  let W: number, H: number, L: number, T: number, pw: number, ph: number, band: number, thick: number
  if (horiz) {
    thick = stack || S === 1 ? 24 : 16
    band = bars * thick + (bars - 1) * 2 + 18
    L = catW + 12 + (lo < 0 ? labelW + 6 : 0)
    const R = labelW + 12
    T = 6
    W = Math.ceil(Math.max(fit, L + R + 160))
    pw = W - L - R
    ph = n * band
    H = T + ph + 26
  } else {
    L = Math.max(24, ...vt.map((v) => textW(fmt(v), TS))) + 10
    T = VS + 12
    const minBar = bars === 1 ? 12 : Math.max(10, labelW)
    const minGroup = bars * minBar + (bars - 1) * 2
    const minBand = Math.max(catW + 10, bars === 1 ? labelW + 12 : minGroup / 0.9, 20)
    W = Math.ceil(Math.max(fit, L + 8 + n * minBand))
    pw = W - L - 8
    ph = plotH(W, props.size)
    H = T + ph + 28 + (lo < 0 ? VS + 6 : 0)
    band = pw / Math.max(n, 1)
    const groupW = bars === 1 ? Math.min(band * 0.5, 140) : Math.max(Math.min(band * 0.8, bars * 72), Math.min(minGroup, band * 0.9))
    thick = (groupW - (bars - 1) * 2) / bars
  }
  const scrolls = W > fit + 1
  /** Pixel along the value axis. */
  const vp = (v: number) => (horiz ? L + ((v - lo) / (hi - lo)) * pw : T + ph - ((v - lo) / (hi - lo)) * ph)
  /** Start of bar j (0..bars-1) of category i across the band axis. */
  const bp = (i: number, j: number) => {
    const group = bars * thick + (bars - 1) * 2
    return (horiz ? T : L) + (i + 0.5) * band - group / 2 + j * (thick + 2)
  }
  /** One run of a bar from value v0 to v1; `round` rounds its data end. */
  const run = (b: number, v0: number, v1: number, round: boolean) => {
    const p0 = vp(v0), p1 = vp(v1)
    if (round) return (horiz ? hbarPath(b, thick, p0, p1) : barPath(b, thick, p0, p1)) || (horiz ? `M${p0},${b}V${b + thick}` : `M${b},${p0}H${b + thick}`)
    return horiz ? rectPath(Math.min(p0, p1), b, Math.abs(p1 - p0), thick) : rectPath(b, Math.min(p0, p1), thick, Math.abs(p1 - p0))
  }
  /** A value label just past the data end of a bar. */
  const endLabel = (key: string, b: number, v: number, text: string) => {
    const p = vp(v), neg = v < 0
    return horiz
      ? <text key={key} className="rb-chart-value" x={neg ? p - 5 : p + 5} y={b + thick / 2} dominantBaseline="central" fontSize={VS} textAnchor={neg ? 'end' : 'start'} aria-hidden="true">{text}</text>
      : <text key={key} className="rb-chart-value" x={b + thick / 2} y={neg ? p + VS + 3 : p - 5} fontSize={VS} textAnchor="middle" aria-hidden="true">{text}</text>
  }
  const many = S * n > 60 // past this, marks are left out of the Tab order; the readable text lists every value

  const out: React.ReactNode[] = []
  vt.forEach((v, k) => {
    const p = vp(v), cls = v === 0 ? 'rb-chart-base' : 'rb-chart-grid'
    out.push(horiz
      ? <line key={`g${k}`} className={cls} x1={p} x2={p} y1={T} y2={T + ph} />
      : <line key={`g${k}`} className={cls} x1={L} x2={L + pw} y1={p} y2={p} />)
    out.push(horiz
      ? <text key={`gt${k}`} className="rb-chart-tick" x={p} y={T + ph + 18} fontSize={TS} textAnchor={k === vt.length - 1 ? 'end' : k === 0 ? 'start' : 'middle'} aria-hidden="true">{fmt(v)}</text>
      : <text key={`gt${k}`} className="rb-chart-tick" x={L - 8} y={p + 4} fontSize={TS} textAnchor="end" aria-hidden="true">{fmt(v)}</text>)
  })
  if (!vt.includes(0)) out.push(horiz
    ? <line key="g0" className="rb-chart-base" x1={vp(0)} x2={vp(0)} y1={T} y2={T + ph} />
    : <line key="g0" className="rb-chart-base" x1={L} x2={L + pw} y1={vp(0)} y2={vp(0)} />)
  d.x.values.forEach((v, i) => out.push(horiz
    ? <text key={`xl${i}`} className="rb-chart-cat" x={catW + 4} y={T + (i + 0.5) * band} dominantBaseline="central" fontSize={CS} textAnchor="end" aria-hidden="true">{v}</text>
    : <text key={`xl${i}`} className="rb-chart-cat" x={L + (i + 0.5) * band} y={T + ph + 20} fontSize={CS} textAnchor="middle" aria-hidden="true">{v}</text>))

  // The empty track up to max, behind each bar.
  if (max !== null) d.x.values.forEach((_, i) => {
    for (let j = 0; j < bars; j++) out.push(<path key={`t${j}-${i}`} className="rb-chart-track" d={run(bp(i, j), 0, max, false)} aria-hidden="true" />)
  })

  const name = (k: number, i: number) => `${d.x.values[i]}, ${d.series[k].field}: ${raw(k, i)}${yUnit}`
  if (stack) d.x.values.forEach((cat, i) => {
    const b = bp(i, 0)
    const segs = d.series.map((s, k) => ({ k, v: s.values[i] })).filter((e): e is { k: number; v: number } => e.v !== null && e.v > 0)
    let at = 0
    segs.forEach(({ k, v }, m) => {
      const p0 = vp(at), p1 = vp(at + v)
      out.push(
        <path key={`b${k}-${i}`} className="rb-chart-mark" d={run(b, at, at + v, m === segs.length - 1)} style={{ fill: colour(k) }}
          role="img" aria-label={`${name(k, i)} (stacked total ${totals[i]}${yUnit})`} tabIndex={many ? undefined : 0}>
          <title>{`${d.series[k].field} @ ${cat}: ${raw(k, i)}`}</title>
        </path>,
      )
      // A segment's own value goes inside it, only when it fits whole.
      if (Math.abs(p1 - p0) >= textW(raw(k, i), IS) + 8 && thick >= IS + 4) out.push(
        <text key={`sv${k}-${i}`} className="rb-chart-inval" x={horiz ? (p0 + p1) / 2 : b + thick / 2} y={horiz ? b + thick / 2 : (p0 + p1) / 2}
          dominantBaseline="central" fontSize={IS} textAnchor="middle" aria-hidden="true">{raw(k, i)}</text>,
      )
      at += v
    })
    out.push(endLabel(`v${i}`, b, Number(totals[i]), totals[i]))
  })
  else d.series.forEach((ser, k) => ser.values.forEach((v, i) => {
    if (v === null) return
    const b = bp(i, k), c = colour(k)
    out.push(
      <path key={`b${k}-${i}`} className="rb-chart-mark" d={run(b, 0, v, true)} style={{ fill: c }} stroke={v === 0 ? c : undefined} strokeWidth={v === 0 ? 2 : undefined}
        role="img" aria-label={name(k, i)} tabIndex={many ? undefined : 0}>
        <title>{`${ser.field} @ ${d.x.values[i]}: ${raw(k, i)}`}</title>
      </path>,
      endLabel(`v${k}-${i}`, b, v, raw(k, i)),
    )
  }))

  const title = a.title ?? `${a.y_label} by ${a.x_label}`
  const kind = `${stack ? 'stacked ' : ''}${horiz ? 'horizontal ' : ''}bar chart${max !== null ? `, 0 to ${a.max}` : ''}`
  return (
    <figure className="rb-chart-fig" {...sized(props.size)}>
      <figcaption className="rb-chart-cap">
        <span id={capId}>{a.y_label}{unit('y_unit')} by {a.x_label}{unit('x_unit')}</span>
        {S > 1 && (
          <ul className="rb-chart-legend" aria-label="Series">
            {d.series.map((s, k) => (
              <li key={s.field}><span className="rb-chart-swatch" style={{ background: colour(k) }} aria-hidden="true" />{s.field}</li>
            ))}
          </ul>
        )}
      </figcaption>
      <div
        ref={wrap}
        className={'rb-chart-scroll' + (scrolls ? ' rb-chart-scrolls' : '')}
        {...(scrolls ? { tabIndex: 0, role: 'region', 'aria-label': `${title}: scroll sideways to see every value` } : {})}
      >
        <svg className="rb-chart" width={W} height={H} viewBox={`0 0 ${W} ${H}`} role="group" aria-label={`${title}, ${kind}`} aria-describedby={capId}>
          {out}
        </svg>
      </div>
    </figure>
  )
}

function ChartCartesianRich(props: RichProps<ChartData | null, never>) {
  const { data, attrs: a } = props
  const d = data!
  const [wrap, avail] = useWidth<HTMLDivElement>()
  const capId = useId()
  const S = d.series.length, n = d.x.values.length
  const unit = (k: string) => (a[k] ? ` (${a[k]})` : '')
  const yUnit = a.y_unit ? ` ${a.y_unit}` : ''
  const colour = (k: number) => (S === 1 ? 'var(--rb-chart-one)' : k < 4 ? `var(--rb-chart-${k + 1})` : PALETTE[k % PALETTE.length])
  const raw = (k: number, i: number) => (d.rows[i][d.columns.indexOf(d.series[k].field)] ?? '').trim()

  const all = d.series.flatMap((x) => x.values).filter((v): v is number => v !== null)
  const yt = niceTicks(Math.min(0, ...all), Math.max(0, ...all))
  const lo = yt[0], hi = yt[yt.length - 1]
  const bar = a.form === 'bar', scatter = a.form === 'scatter'

  // Room the words need, so the drawing can be sized to them and never they to it.
  const VS = S === 1 ? 13 : 11, CS = 13, TS = 12
  const labelW = bar ? Math.max(...d.series.flatMap((_, k) => d.x.values.map((_, i) => textW(raw(k, i), VS)))) : 0
  const catW = scatter ? 0 : Math.max(...d.x.values.map((v) => textW(v, CS)))
  const L = Math.max(24, ...yt.map((v) => textW(fmt(v), TS))) + 10, R = 8
  const T = bar ? VS + 12 : 12, B = 28 + (bar && lo < 0 ? VS + 6 : 0)
  const minBar = S === 1 ? 12 : Math.max(10, labelW)
  const minGroup = S * minBar + (S - 1) * 2 // several series: each bar as wide as its value
  const minBand = scatter ? 0 : Math.max(catW + 10, bar ? (S === 1 ? labelW + 12 : minGroup / 0.9) : 0, 20)
  const fit = avail || 560
  const W = Math.ceil(Math.max(fit, L + R + n * minBand, scatter ? 200 : 0))
  const scrolls = W > fit + 1
  const pw = W - L - R, ph = plotH(W, props.size)
  const H = T + ph + B
  const yv = (v: number) => T + ph - ((v - lo) / (hi - lo)) * ph
  const many = S * n > 60 // past this, marks are left out of the Tab order; the readable text lists every value

  const out: React.ReactNode[] = []
  yt.forEach((v, k) => {
    const y = yv(v)
    out.push(<line key={`g${k}`} className={v === 0 ? 'rb-chart-base' : 'rb-chart-grid'} x1={L} x2={L + pw} y1={y} y2={y} />)
    out.push(<text key={`gt${k}`} className="rb-chart-tick" x={L - 8} y={y + 4} fontSize={TS} textAnchor="end" aria-hidden="true">{fmt(v)}</text>)
  })
  if (!yt.includes(0)) out.push(<line key="g0" className="rb-chart-base" x1={L} x2={L + pw} y1={yv(0)} y2={yv(0)} />)
  let xs: (number | null)[]
  const band = pw / Math.max(n, 1)
  if (scatter) {
    const xn = d.x.numbers!.filter((v): v is number => v !== null)
    const xt = niceTicks(Math.min(...xn), Math.max(...xn))
    const xl = xt[0], xh = xt[xt.length - 1]
    xs = d.x.numbers!.map((v) => (v === null ? null : L + ((v - xl) / (xh - xl)) * pw))
    xt.forEach((v, k) => out.push(
      <text key={`xt${k}`} className="rb-chart-tick" x={L + ((v - xl) / (xh - xl)) * pw} y={T + ph + 20} fontSize={TS}
        textAnchor={k === 0 ? 'start' : k === xt.length - 1 ? 'end' : 'middle'} aria-hidden="true">{fmt(v)}</text>,
    ))
  } else {
    xs = d.x.values.map((_, i) => L + (i + 0.5) * band)
    d.x.values.forEach((v, i) => out.push(
      <text key={`xl${i}`} className="rb-chart-cat" x={xs[i]!} y={T + ph + 20} fontSize={CS} textAnchor="middle" aria-hidden="true">{v}</text>,
    ))
  }
  const groupW = S === 1 ? Math.min(band * 0.5, 140) : Math.max(Math.min(band * 0.8, S * 72), Math.min(minGroup, band * 0.9))
  const bw = (groupW - (S - 1) * 2) / S
  d.series.forEach((ser, k) => {
    const c = colour(k)
    const name = (i: number) => `${d.x.values[i]}, ${ser.field}: ${bar ? raw(k, i) : ser.values[i]}${yUnit}`
    if (bar) {
      ser.values.forEach((v, i) => {
        if (v === null) return
        const x = xs[i]! - groupW / 2 + k * (bw + 2), y = yv(v), y0 = yv(0)
        out.push(
          <path key={`b${k}-${i}`} className="rb-chart-mark" d={barPath(x, bw, y0, y) || `M${x},${y0}H${x + bw}`} style={{ fill: c }} stroke={v === 0 ? c : undefined} strokeWidth={v === 0 ? 2 : undefined}
            role="img" aria-label={name(i)} tabIndex={many ? undefined : 0}>
            <title>{`${ser.field} @ ${d.x.values[i]}: ${raw(k, i)}`}</title>
          </path>,
          <text key={`v${k}-${i}`} className="rb-chart-value" x={x + bw / 2} y={v < 0 ? y + VS + 3 : y - 5} fontSize={VS} textAnchor="middle" aria-hidden="true">
            {raw(k, i)}
          </text>,
        )
      })
      return
    }
    if (a.form === 'line') {
      let seg: string[] = [], m = 0
      const flush = () => {
        if (seg.length) out.push(<polyline key={`l${k}-${m++}`} className="rb-chart-line" fill="none" style={{ stroke: c }} strokeWidth={2} points={seg.join(' ')} />)
        seg = []
      }
      ser.values.forEach((v, i) => { if (v === null) flush(); else seg.push(`${xs[i]},${yv(v)}`) })
      flush()
    }
    ser.values.forEach((v, i) => {
      if (v === null || xs[i] === null) return
      out.push(
        <circle key={`p${k}-${i}`} className="rb-chart-mark" cx={xs[i]!} cy={yv(v)} r={a.form === 'line' ? 3.5 : 4} style={{ fill: c }}
          role="img" aria-label={a.form === 'line' ? name(i) : `${ser.field}: ${d.x.values[i]}, ${v}${yUnit}`} tabIndex={many ? undefined : 0}>
          <title>{a.form === 'line' ? `${ser.field} @ ${d.x.values[i]}: ${v}` : `${d.x.values[i]}, ${v}`}</title>
        </circle>,
      )
    })
  })
  const name = a.title ?? `${a.y_label} by ${a.x_label}`
  return (
    <figure className="rb-chart-fig" {...sized(props.size)}>
      <figcaption className="rb-chart-cap">
        <span id={capId}>{a.y_label}{unit('y_unit')} by {a.x_label}{unit('x_unit')}</span>
        {S > 1 && (
          <ul className="rb-chart-legend" aria-label="Series">
            {d.series.map((s, k) => (
              <li key={s.field}><span className="rb-chart-swatch" style={{ background: colour(k) }} aria-hidden="true" />{s.field}</li>
            ))}
          </ul>
        )}
      </figcaption>
      <div
        ref={wrap}
        className={'rb-chart-scroll' + (scrolls ? ' rb-chart-scrolls' : '')}
        {...(scrolls ? { tabIndex: 0, role: 'region', 'aria-label': `${name}: scroll sideways to see every value` } : {})}
      >
        <svg className="rb-chart" width={W} height={H} viewBox={`0 0 ${W} ${H}`} role="group" aria-label={`${name}, ${a.form} chart`} aria-describedby={capId}>
          {out}
        </svg>
      </div>
    </figure>
  )
}

/* ---------------------------------------------------------------------- pad */

/** Tab state: the edited text. Kept by Mentis instead: its one field, `text`. */
type PadState = string | { values?: Record<string, Val>; durable?: A.Durable }
const padNow = (data: string, s: PadState | undefined) =>
  s === undefined ? data : typeof s === 'string' ? s : typeof s.values?.text === 'string' ? s.values.text : data

function PadView({ data, attrs, state, set, help, menu }: RichProps<string, PadState>) {
  const key = help.key
  const { found, e, why } = useKept(help, attrs, 'pad')
  const [history, setHistory] = useState(false)
  menu?.(e?.set ? [{ label: 'Answers', items: [{ label: 'History…', onSelect: () => setHistory(true) }] }] as MenuGroup[] : [])
  /* Refused by the server after something was typed: keep it, in the tab. */
  useEffect(() => {
    if (found?.cannot && 'text' in found.drafts) {
      set(String(found.drafts.text))
      found.drafts = {}
    }
  }, [found, found?.cannot, set])
  if (!e)
    return (
      <div className="rb-kept" data-saved="tab">
        <KeptNotices e={null} why={why} blockKey={key} quiet what="pad" />
        <textarea className="rb-pad" value={typeof state === 'string' ? state : data}
          onChange={(ev) => set(ev.target.value === data ? undefined : ev.target.value)} />
      </div>
    )
  const k = atField(e, key, 'text')
  return (
    <div className="rb-kept" data-saved="mentis" data-field="text" title={k.who ?? undefined}>
      <KeptNotices e={e} why={null} blockKey={key} what="pad" />
      <textarea className="rb-pad" aria-label={attrs.title ?? 'Pad'} disabled={!e.read || !!e.set?.source_deleted}
        value={String(A.shownValue(e, 'text', data))}
        onChange={(ev) => A.draft(key, 'text', ev.target.value)} onBlur={() => void A.finish(key, 'text', data)} />
      <div className="rb-pad-notes">{k.mark}{k.says}{k.who && <div className="rb-form-who rb-pad-who">{k.who}</div>}</div>
      <OwnWords e={e} blockKey={key} labelOf={() => 'the text'} />
      <KeptFoot e={e} blockKey={key} onDone={() => void doneWith(key, { text: data })} />
      {history && <History blockKey={key} fields={[{ id: 'text', label: attrs.title ?? 'Text' }]} onClose={() => setHistory(false)} />}
    </div>
  )
}

export const pad: TypeDef<string, PadState> = {
  ...padSpec,
  Rich: (p) => <PadView {...p} />,
  readable(data, a, s) {
    const d = typeof s === 'object' ? s.durable : undefined
    const now = padNow(data, s)
    const out = a.title ? [`title: ${q(a.title)}`] : []
    if (a.source) out.push(`source (declared, not resolved): ${a.source}${a.refs ? ' ' + a.refs : ''}`)
    if (d?.conflicts.text) out.push(`text: two answers disagree: ${d.conflicts.text.map((c) => `${q(String(c.value))} by ${c.by}`).join('; ')}`)
    out.push(now === data ? 'text (as in the source):' : `text (edited; the source text differs${d?.by.text ? `; by ${d.by.text}` : ''}${d?.unsaved.includes('text') ? '; typed here, not saved yet' : ''}):`)
    out.push(...now.split('\n').map((l) => '> ' + l))
    out.push(...wordsLines(d))
    if (d) out.push(`saved: ${d.status || 'nothing answered yet'}`)
    return out.join('\n')
  },
  handoff(data, _a, s) {
    return { pad_text_now: padNow(data, s) }
  },
}
