/* THE ORBIT: A MAGNET'S RING, READ (owner Turns #1226, #1592; plan §3.10
 * "ring").
 *
 * Around the disc, one arc per kind of thing it holds, sized by its share
 * (model.ts orbitArcs) and coloured by its kind, over a halo in the canvas's
 * own colour so it reads on any background or theme. Its state shows in the
 * ring itself: new items since it was last opened are satellites going round
 * it; reading is the empty ring turning; paused is a dashed, muted ring; an
 * error a red one. The `ring` renderer draws the same ring heavier. With
 * reduced motion nothing turns: satellites rest at their places and reading
 * is a still dashed ring. Decorative: the disc's label says all of it. */

import { orbitArcs, type Holding, type MagnetState } from './model'

const SIZE = 84
const C = SIZE / 2

const at = (frac: number, r: number) => {
  const a = frac * 2 * Math.PI - Math.PI / 2
  return `${(C + r * Math.cos(a)).toFixed(2)} ${(C + r * Math.sin(a)).toFixed(2)}`
}
/** An arc from `from` to `to` (fractions of the circle, from the top, clockwise). */
export const arcPath = (from: number, to: number, r: number): string =>
  to - from >= 0.999
    ? `M ${at(0, r)} A ${r} ${r} 0 1 1 ${at(0.5, r)} A ${r} ${r} 0 1 1 ${at(0, r)}`
    : `M ${at(from, r)} A ${r} ${r} 0 ${to - from > 0.5 ? 1 : 0} 1 ${at(to, r)}`

export function Orbit({ holding, state, unread, renderer }: { holding: Holding; state: MagnetState; unread: number; renderer: string }) {
  const ring = renderer === 'ring'
  const r = ring ? 35 : 34
  const w = ring ? 5 : 3.5
  const arcs = orbitArcs(holding)
  const sats = Math.min(3, unread)
  return <svg className="mg-orbit" data-state={state} data-renderer={renderer} width={SIZE} height={SIZE} viewBox={`0 0 ${SIZE} ${SIZE}`} aria-hidden="true" focusable="false">
    <circle className="mg-orbit-halo" cx={C} cy={C} r={r} strokeWidth={w + 4} />
    {arcs.length && state !== 'reading'
      ? <g className="mg-orbit-arcs">{arcs.map((a) => <path key={a.type} className="mg-arc" data-type={a.type} d={arcPath(a.from, a.to, r)} strokeWidth={w} />)}</g>
      : <circle className="mg-orbit-empty" cx={C} cy={C} r={r} strokeWidth={w} />}
    {sats > 0 && <g className="mg-sats">
      {Array.from({ length: sats }, (_, i) => <circle key={i} className="mg-sat" cx={C} cy={C - r} r={ring ? 5 : 4.5}
        transform={`rotate(${i * (360 / sats)} ${C} ${C})`} />)}
    </g>}
  </svg>
}
