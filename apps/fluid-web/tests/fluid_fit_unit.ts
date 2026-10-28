/* Fit to content (Fluid Focus, DESIGN.md 4; workspace/tree.ts `place`,
   `fitSizes`), held in Node against the tree itself (no server, no browser):

     * a fitted zone in a column takes its natural height, held between its
       minimum and FIT_MAX of the column; its neighbours absorb the rest in
       proportion to their shares;
     * a natural size too big for the neighbours' minimums gives way to them;
     * every kid fitted: the one with the largest share flexes;
     * in a row a fitted zone is measured across, at the row's height;
     * nothing fitted (or nothing measured): `place` lays every tree out
       exactly as the function did before fit (`placeBefore`, its body as it
       was, kept here);
     * `valid` accepts `fit` only as a boolean; `setFit`, `fitAxes` and
       `asDrawn` do what they say.

   Run by tests/run.mjs. */
import assert from 'node:assert/strict'
import {
  asDrawn, fitAxes, FIT_MAX, foldedHeight, GUTTER, MIN_H, MIN_W, minSize, place, setFit, valid,
  type Folded, type Natural, type Node, type Rect, type Split, type Zone,
} from '../src/fluid/workspace/tree'

let checks = 0
const eq = (a: unknown, b: unknown, what: string) => { assert.deepEqual(a, b, what); checks++ }
const near = (a: number | undefined, b: number, what: string) => { assert.ok(a !== undefined && Math.abs(a - b) < 1e-6, `${what}: ${a} is not ${b}`); checks++ }

const z = (id: string, fit?: boolean): Zone => ({ type: 'zone', id, show: 'objects', name: id, ...(fit === undefined ? {} : { fit }) })
const split = (dir: 'row' | 'col', kids: Node[], sizes?: number[]): Split => ({ type: 'split', dir, kids, sizes: sizes ?? kids.map(() => 1 / kids.length) })
const box = (w: number, h: number): Rect => ({ x: 0, y: 0, w, h })
/** a natural size per zone id, along whatever axis is asked */
const nat = (m: Record<string, number>, seen?: { id: string; axis: string; cross: number }[]): Natural =>
  (zz, axis, cross) => { seen?.push({ id: zz.id, axis, cross }); return m[zz.id] ?? null }

/* -- the function before fit, its body as it was ------------------------------ */

function placeBefore(n: Node, r: Rect, out = new Map<Node, Rect>(), folded?: Folded, wrap = false, setW?: Map<string, number>): Map<Node, Rect> {
  out.set(n, r)
  if (n.type === 'zone') return out
  const set = (k: Node) => (n.dir === 'row' && k.type === 'zone' ? setW?.get(k.id) ?? null : null)
  if (wrap && n.dir === 'row') {
    const mins = n.kids.map((k) => set(k) ?? minSize(k, 'w', true))
    if (mins.reduce((a, b) => a + b, 0) + GUTTER * (n.kids.length - 1) > r.w && n.kids.length > 1) {
      const lines: number[][] = [[]]
      let used = 0
      mins.forEach((m, i) => {
        const line = lines[lines.length - 1]
        if (line.length && used + GUTTER + m > r.w) { lines.push([i]); used = m } else { line.push(i); used += (line.length > 1 ? GUTTER : 0) + m }
      })
      const lh = Math.max(0, (r.h - GUTTER * (lines.length - 1)) / lines.length)
      lines.forEach((line, j) => {
        const share = line.reduce((a, i) => a + n.sizes[i], 0) || 1
        const row: Split = { type: 'split', dir: 'row', kids: line.map((i) => n.kids[i]), sizes: line.map((i) => n.sizes[i] / share) }
        const lr = { x: r.x, y: r.y + j * (lh + GUTTER), w: r.w, h: lh }
        placeBefore(row, lr, out, folded, wrap, setW)
      })
      out.set(n, r)
      return out
    }
  }
  const along = n.dir === 'row' ? r.w : r.h
  const avail = Math.max(0, along - GUTTER * (n.kids.length - 1))
  const fixed = n.dir === 'col' ? n.kids.map((k) => foldedHeight(k, folded, r.w)) : n.kids.map(() => null)
  if (fixed.some((h) => h !== null)) {
    const taken = fixed.reduce<number>((a, h) => a + (h ?? 0), 0)
    const share = n.sizes.reduce((a, s, i) => a + (fixed[i] === null ? s : 0), 0) || 1
    const left = Math.max(0, avail - taken)
    let off = 0
    n.kids.forEach((k, i) => {
      const s = fixed[i] ?? (left * n.sizes[i]) / share
      placeBefore(k, { x: r.x, y: r.y + off, w: r.w, h: s }, out, folded, wrap, setW)
      off += s + GUTTER
    })
    return out
  }
  const sets = n.kids.map(set)
  const mins = n.kids.map((k, i) => sets[i] ?? minSize(k, n.dir === 'row' ? 'w' : 'h', wrap))
  const taken = sets.reduce<number>((a, w) => a + (w ?? 0), 0)
  const shared = n.sizes.reduce((a, s, i) => a + (sets[i] === null ? s : 0), 0) || 1
  let sizes = n.kids.map((_, i) => sets[i] ?? (taken ? ((avail - taken) * n.sizes[i]) / shared : avail * n.sizes[i]))
  if (mins.reduce((a, b) => a + b, 0) <= avail)
    for (let pass = 0; pass < 4; pass++) {
      const short = sizes.reduce((d, s, i) => d + Math.max(0, mins[i] - s), 0)
      if (short < 0.5) break
      const spare = sizes.reduce((d, s, i) => d + Math.max(0, s - mins[i]), 0)
      sizes = sizes.map((s, i) => (s <= mins[i] ? mins[i] : s - ((s - mins[i]) / spare) * short))
    }
  let off = 0
  n.kids.forEach((k, i) => {
    const s = sizes[i]
    placeBefore(k, n.dir === 'row' ? { x: r.x + off, y: r.y, w: s, h: r.h } : { x: r.x, y: r.y + off, w: r.w, h: s }, out, folded, wrap, setW)
    off += s + GUTTER
  })
  return out
}

/** Rects by zone id (and split by its first zone), for comparing two layouts. */
const byId = (m: Map<Node, Rect>) => [...m].map(([n, r]) => [n.type === 'zone' ? n.id : 'split:' + (n.kids[0].type === 'zone' ? n.kids[0].id : '…'), r])
const rectOf = (m: Map<Node, Rect>, id: string) => [...m].find(([n]) => n.type === 'zone' && n.id === id)?.[1]

/* -- a fitted zone in a column --------------------------------------------- */

{
  const t = split('col', [z('A', true), z('B'), z('C')], [0.5, 0.25, 0.25])
  const avail = 1000 - 2 * GUTTER
  const at = (v: number) => place(t, box(800, 1000), undefined, undefined, false, undefined, nat({ A: v }))
  let m = at(200)
  near(rectOf(m, 'A')?.h, 200, 'a fitted zone takes its natural height')
  near(rectOf(m, 'B')?.h, (avail - 200) / 2, 'its neighbours absorb the rest')
  near(rectOf(m, 'C')?.h, (avail - 200) / 2, 'in proportion to their shares')
  near(rectOf(m, 'C')!.y + rectOf(m, 'C')!.h, 1000, 'and the column is filled')
  m = at(2000)
  near(rectOf(m, 'A')?.h, avail * FIT_MAX, 'never more than FIT_MAX of the column')
  near(rectOf(m, 'B')?.h, (avail * (1 - FIT_MAX)) / 2, 'the rest still shared')
  m = at(40)
  near(rectOf(m, 'A')?.h, MIN_H, 'never less than its minimum')
  /* unequal shares: the rest in proportion */
  const u = split('col', [z('A', true), z('B'), z('C')], [0.2, 0.6, 0.2])
  m = place(u, box(800, 1000), undefined, undefined, false, undefined, nat({ A: 300 }))
  near(rectOf(m, 'B')!.h / rectOf(m, 'C')!.h, 3, 'neighbours keep the proportion of their shares')
}

/* -- too big gives way to the neighbours' minimums -------------------------- */

{
  const t = split('col', [z('A', true), z('B'), z('C')])
  const avail = 600 - 2 * GUTTER
  const m = place(t, box(800, 600), undefined, undefined, false, undefined, nat({ A: 500 }))
  near(rectOf(m, 'B')?.h, MIN_H, 'the neighbour keeps its minimum')
  near(rectOf(m, 'C')?.h, MIN_H, 'and so does the other')
  near(rectOf(m, 'A')?.h, avail - 2 * MIN_H, 'the fitted zone gives way')
  /* two fitted give way in proportion to what each has above its minimum */
  const two = split('col', [z('A', true), z('B', true), z('C')])
  const m2 = place(two, box(800, 700), undefined, undefined, false, undefined, nat({ A: 340, B: 240 }))
  const av2 = 700 - 2 * GUTTER
  near(rectOf(m2, 'C')?.h, MIN_H, 'the sharing zone keeps its minimum')
  const over = 340 + 240 + MIN_H - av2
  near(rectOf(m2, 'A')?.h, 340 - over * (200 / 300), 'the one with more above its minimum gives more')
  near(rectOf(m2, 'B')?.h, 240 - over * (100 / 300), 'the other less')
}

/* -- every kid fitted ------------------------------------------------------- */

{
  const t = split('col', [z('A', true), z('B', true)], [0.6, 0.4])
  const m = place(t, box(800, 900), undefined, undefined, false, undefined, nat({ A: 200, B: 200 }))
  near(rectOf(m, 'B')?.h, 200, 'the smaller share keeps its natural height')
  near(rectOf(m, 'A')?.h, 900 - GUTTER - 200, 'the largest share flexes')
}

/* -- in a row: measured across, at the row's height --------------------------- */

{
  const seen: { id: string; axis: string; cross: number }[] = []
  const t = split('row', [z('A'), z('B', true)])
  const m = place(t, box(1200, 700), undefined, undefined, false, undefined, nat({ B: 300 }, seen))
  eq(seen.map((s) => [s.id, s.axis, s.cross]), [['B', 'w', 700]], 'only the fitted zone is measured, across, at the row\'s height')
  near(rectOf(m, 'B')?.w, 300, 'it takes its natural width')
  near(rectOf(m, 'A')?.w, 1200 - GUTTER - 300, 'the other the rest')
  near(rectOf(m, 'B')?.x, 1200 - 300, 'drawn where it is in the row')
  const narrow = place(t, box(1200, 700), undefined, undefined, false, undefined, nat({ B: 100 }))
  near(rectOf(narrow, 'B')?.w, MIN_W, 'not narrower than a zone is')
}

/* -- nested: a fitted zone in a column inside a row -------------------------- */

{
  const t = split('row', [z('L'), split('col', [z('A', true), z('B')])], [0.5, 0.5])
  const m = place(t, box(1012, 800), undefined, undefined, false, undefined, nat({ A: 250 }))
  near(rectOf(m, 'A')?.h, 250, 'fitted in its own column')
  near(rectOf(m, 'B')?.h, 800 - GUTTER - 250, 'its neighbour the rest')
  near(rectOf(m, 'L')?.w, 500, 'the row is as it was')
}

/* -- nothing fitted: exactly as before --------------------------------------- */

{
  const trees: [string, Node, Rect, Folded | undefined, boolean, Map<string, number> | undefined][] = [
    ['one zone', z('A'), box(900, 600), undefined, false, undefined],
    ['a row', split('row', [z('A'), z('B'), z('C')], [0.5, 0.3, 0.2]), box(1400, 800), undefined, false, undefined],
    ['a row below its minimums', split('row', [z('A'), z('B'), z('C')], [0.8, 0.1, 0.1]), box(900, 600), undefined, false, undefined],
    ['nested', split('row', [z('A'), split('col', [z('B'), z('C'), z('D')], [0.2, 0.5, 0.3])], [0.4, 0.6]), box(1300, 900), undefined, false, undefined],
    ['wrapped (Home)', split('row', [z('A'), z('B'), z('C'), z('D')]), box(700, 900), undefined, true, undefined],
    ['folded (Home)', split('col', [z('A'), z('B'), z('C')]), box(800, 900), (zz) => (zz.id === 'B' ? 44 : null), false, undefined],
    ['a set width (rail)', split('row', [z('A'), z('B'), z('C')], [0.2, 0.4, 0.4]), box(1400, 800), undefined, false, new Map([['A', 56]])],
  ]
  for (const [what, t, r, folded, wrap, setW] of trees) {
    const before = byId(placeBefore(t, r, undefined, folded, wrap, setW))
    eq(byId(place(t, r, undefined, folded, wrap, setW)), before, `${what}: as before, without natural`)
    eq(byId(place(t, r, undefined, folded, wrap, setW, nat({ A: 300, B: 300, C: 300 }))), before, `${what}: as before, nothing fitted`)
    const allFit = (n: Node): Node => (n.type === 'zone' ? { ...n, fit: true } : { ...n, kids: n.kids.map(allFit) })
    const unmeasured = place(allFit(t), r, undefined, folded, wrap, setW, () => null)
    eq(byId(unmeasured).map(([, x]) => x), before.map(([, x]) => x), `${what}: as before, fitted but not yet measured`)
  }
}

/* -- reading one back, and the edits -------------------------------------------- */

{
  ok(valid(split('col', [z('A', true), z('B', false)])), 'fit, true or false, is a well-formed tree')
  ok(!valid(split('col', [{ ...z('A'), fit: 'yes' } as unknown as Zone, z('B')])), 'fit as anything else is not')
  const t = split('row', [z('A'), split('col', [z('B', true), z('C')])])
  eq([...fitAxes(t)], [['B', 'h']], 'a fitted zone in a column is measured down')
  eq([...fitAxes(split('row', [z('A', true), z('B')]))], [['A', 'w']], 'in a row, across')
  eq([...fitAxes(z('A', true))], [], 'the whole tree fills')
  eq([...fitAxes(z('A', true), true)], [['A', 'h']], 'stacked, it is measured down')
  const on = setFit(t, ['C'], true)
  eq(fitAxes(on).has('C'), true, 'setFit turns it on')
  const off = setFit(on, ['B', 'C'], false)
  eq(fitAxes(off).size, 0, 'and off')
  eq(JSON.stringify(off).includes('"fit"'), false, 'off, nothing of it is kept')
  const s = split('col', [z('A', true), z('B'), z('C')], [0.5, 0.25, 0.25])
  const rects = place(s, box(800, 1000), undefined, undefined, false, undefined, nat({ A: 200 }))
  const d = asDrawn(s, s, rects)
  const ds = (d.split as Split).sizes
  near(ds.reduce((a, b) => a + b, 0), 1, 'asDrawn: shares that add up to one')
  near(ds[0] * (1000 - 2 * GUTTER), 200, 'each kid\'s share what it is drawn at')
  const again = place(setFit(d.tree, ['A'], false), box(800, 1000))
  near(rectOf(again, 'A')?.h, 200, 'so turned off there, it stays where it was')
}

function ok(v: unknown, what: string) { assert.ok(v, what); checks++ }

console.log(`fluid fit: ${checks} checks passed`)
