/* THE WORKSPACE YOU SHAPE: a place's zones as a split tree (Fluid
 * completion, stream A; the Lab's zones.ts, ui/src/lab/zones.ts, in the
 * shape Fluid keeps in the Brain, mentis/fluid/arrangements.py).
 *
 * A page is a tree: a ZONE, or a SPLIT laying its children side by side
 * (`row`) or stacked (`col`), each with its share of what is left once the
 * gutters are paid for. The gutter is the only border. Every edit returns a
 * NEW tree, so React sees it and Undo keeps the old one.
 *
 * A conversation's zone carries a SLOT: whether it follows what is read
 * (with its Show filter) and which objects are kept in it, by live address,
 * shown before what it follows -- so keeping in place is "this zone holds it
 * now" whatever is read next. `present` and `appearance` are kept for the
 * zone body (present/index.ts) and the zone sheet (stream D); this file only
 * carries them. A Home zone says which collection it shows (`show`) and keeps
 * its own choices in `options`. */

export const GUTTER = 12
export const MIN_W = 240
export const MIN_H = 140

/** What a following zone shows of what is read (the zone sheet's Show). */
/** `needs-you` (#576): what on the post read, or its thread, needs the owner.
 *  `forms`, `fillable`: its forms; everything in it that can be filled in. */
export type Show = 'objects' | 'everything' | 'sections' | 'media' | 'files' | 'forms' | 'fillable' | 'kinds' | 'needs-you'
export type PresentMode = 'cards' | 'gallery' | 'slides' | 'list' | 'focus' | 'previews' | 'across'
export type Background = 'transparent' | 'tinted' | 'solid'
export interface Appearance { panel?: Background; content?: Background; opacity?: number }

export interface Slot {
  follow: boolean
  /** a following zone held on one post (its root id) and its replies,
   *  whatever is read; absent, it follows what is read. A post, so a named
   *  layout never carries it. Null, as the server takes it, is no pin. */
  pin?: string | null
  show: Show
  kinds?: string[]
  /** what is kept here, by live address, in order */
  items: string[]
  present: PresentMode
  appearance?: Appearance
}

export interface Zone {
  type: 'zone'
  id: string
  /** a conversation zone: `objects`; a Home zone: the collection it shows */
  show: string
  name?: string
  options?: Record<string, unknown>
  slot?: Slot
}
export interface Split { type: 'split'; dir: 'row' | 'col'; sizes: number[]; kids: Node[] }
export type Node = Zone | Split
export interface Rect { x: number; y: number; w: number; h: number }

let seq = 0
export const freshId = (p: string) => `${p}${Date.now().toString(36)}${(seq += 1)}`

const NAMES = ['Stage', 'Side', 'Shelf', 'Desk', 'Notes', 'Wing', 'Corner', 'Strip', 'Bench', 'Margin']

export const zones = (n: Node): Zone[] => (n.type === 'zone' ? [n] : n.kids.flatMap(zones))

/** The zone that carries the read post's words on a rail: the first that
 *  follows what is read. A zone held on a post (P10b) shows another post, so
 *  it carries them only where every following zone is held -- and then it
 *  draws the read post's words, not its own post's (Zones.tsx). */
export function wordsZone(n: Node): string | undefined {
  const following = zones(n).filter((z) => z.slot?.follow)
  return (following.find((z) => !z.slot?.pin) ?? following[0])?.id
}

/** A name nobody in this tree is using yet. */
export function freshName(tree: Node | null): string {
  const used = new Set(tree ? zones(tree).map((z) => z.name) : [])
  for (const n of NAMES) if (!used.has(n)) return n
  let i = NAMES.length + 1
  while (used.has(`Zone ${i}`)) i++
  return `Zone ${i}`
}

export const followSlot = (show: Show = 'objects'): Slot => ({ follow: true, show, items: [], present: 'cards' })
export const keepSlot = (items: string[] = [], present: PresentMode = 'cards'): Slot => ({ follow: false, show: 'objects', items, present })

/** A conversation zone. */
export const zone = (tree: Node | null, slot: Slot = followSlot()): Zone =>
  ({ type: 'zone', id: freshId('z'), show: 'objects', name: freshName(tree), slot })

/* -- geometry ---------------------------------------------------------------- */

/** The smallest a node can be along one axis and still give each zone its
 *  minimum. `wrap`: a row too full for its width wraps onto more lines
 *  (`place`), so across it needs only its widest zone. */
export function minSize(n: Node, axis: 'w' | 'h', wrap = false): number {
  if (n.type === 'zone') return axis === 'w' ? MIN_W : MIN_H
  const along = (n.dir === 'row') === (axis === 'w')
  const m = n.kids.map((k) => minSize(k, axis, wrap))
  if (wrap && n.dir === 'row' && axis === 'w') return Math.max(...m)
  return along ? m.reduce((a, b) => a + b, 0) + GUTTER * (n.kids.length - 1) : Math.max(...m)
}

/** A row wrapped onto more than one line (`place` with `wrap`): it has no
 *  boundary to drag between its zones. */
export const wrapped = (n: Split, rects: Map<Node, Rect>) =>
  n.dir === 'row' && new Set(n.kids.map((k) => Math.round(rects.get(k)?.y ?? 0))).size > 1

/** The least height a line of a wrapped row is usable at: a zone's caption
 *  and a couple of lines of what it shows. */
export const WRAP_H = 96

/** Did every wrapped row keep its lines usable? When one did not, the space
 *  is too small for the tree at all (a phone), and it is shown stacked. */
export function wrapFits(n: Node, rects: Map<Node, Rect>): boolean {
  if (n.type === 'zone') return true
  if (wrapped(n, rects) && n.kids.some((k) => (rects.get(k)?.h ?? 0) < WRAP_H)) return false
  return n.kids.every((k) => wrapFits(k, rects))
}

/** A zone's height when it needs only so much -- folded to its caption, or
 *  (Home) a zone still asking what to show -- at width `w`; null when it
 *  takes its share (#568 5.2). */
export type Folded = (z: Zone, w: number) => number | null

/** The height a node needs when everything in it needs only so much, or
 *  null when something in it takes a share: zones above one another add up,
 *  zones side by side are as tall as the tallest. */
export function foldedHeight(n: Node, folded: Folded | undefined, w: number): number | null {
  if (!folded) return null
  if (n.type === 'zone') return folded(n, w)
  const avail = Math.max(0, w - (n.dir === 'row' ? GUTTER * (n.kids.length - 1) : 0))
  const hs = n.kids.map((k, i) => foldedHeight(k, folded, n.dir === 'row' ? avail * n.sizes[i] : w))
  if (hs.some((h) => h === null)) return null
  const all = hs as number[]
  return n.dir === 'col' ? all.reduce((a, b) => a + b, 0) + GUTTER * (all.length - 1) : Math.max(...all)
}

/** Where every node sits, for a tree drawn into `r`. A zone folded to its
 *  caption gives the rest of its height back to the zones above and below
 *  it (`folded`); what it was given is kept for when it opens again.
 *
 *  `wrap` (Home, opr-996398d467d1): A ROW TOO FULL FOR ITS WIDTH WRAPS ONTO
 *  MORE LINES in its own space, as many zones on each as fit at their
 *  minimum, and the rest of the tree keeps its shape -- rather than the
 *  whole tree falling back to one stacked column. Its shares are kept for
 *  when there is room again.
 *
 *  `setW`: zones drawn at a set width across their row, whatever their
 *  share (a zone docked as a rail, `docked`); the rest of the row shares
 *  what is left. */
export function place(n: Node, r: Rect, out = new Map<Node, Rect>(), folded?: Folded, wrap = false, setW?: Map<string, number>): Map<Node, Rect> {
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
        place(row, lr, out, folded, wrap, setW)
      })
      out.set(n, r)
      return out
    }
  }
  const along = n.dir === 'row' ? r.w : r.h
  const avail = Math.max(0, along - GUTTER * (n.kids.length - 1))
  const fixed = n.dir === 'col' ? n.kids.map((k) => foldedHeight(k, folded, r.w)) : n.kids.map(() => null)
  if (fixed.some((h) => h !== null)) {
    /* The folded take their captions; the rest share what is left, in
       proportion to their own shares. */
    const taken = fixed.reduce<number>((a, h) => a + (h ?? 0), 0)
    const share = n.sizes.reduce((a, s, i) => a + (fixed[i] === null ? s : 0), 0) || 1
    const left = Math.max(0, avail - taken)
    let off = 0
    n.kids.forEach((k, i) => {
      const s = fixed[i] ?? (left * n.sizes[i]) / share
      place(k, { x: r.x, y: r.y + off, w: r.w, h: s }, out, folded, wrap, setW)
      off += s + GUTTER
    })
    return out
  }
  /* Shares set at one width are kept at another, but never at a zone's
     expense: while there is room for every minimum, a zone below its own is
     lifted to it and the room taken from the others in proportion.  A zone
     at a set width (`setW`) is that wide; the others share the rest. */
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
    place(k, n.dir === 'row' ? { x: r.x + off, y: r.y, w: s, h: r.h } : { x: r.x, y: r.y + off, w: r.w, h: s }, out, folded, wrap, setW)
    off += s + GUTTER
  })
  return out
}

/* -- a zone minimized to a rail, docked at the edge of its row --------------
 *
 * HOME'S CONVERSATION, TOO NARROW TO READ, GIVES ITS ROOM BACK (the owner,
 * adm-d0a5e868ba3d: the rail drawn down the middle of a 300 px zone). A zone
 * that wants it is drawn at the rail's width at the nearer end of the row
 * that holds it, and the zones beside it share the rest in proportion to
 * their own shares. Only the drawing: the tree is not rewritten -- its order
 * and shares are what is kept and saved, and the zone is back where it was,
 * as wide as it was, once it is wide enough to read.
 *
 * A ZONE IN A COLUMN IS TAKEN OUT OF IT (the owner, adm-0eeed9d27bb8: never
 * centred in leftover space): drawn, the column is without it -- the zones
 * that shared it take its whole height, at its whole width -- and it is the
 * rail at the nearer end of the nearest row holding that column, the rest of
 * the row in its order and proportions. Squeezing the column itself to the
 * rail would take the others down with it. Kept, it is still in the column,
 * with its share. A zone in a row wrapped onto more lines (a phone), or with
 * no row above it (as wide as the page), is not docked. */

export interface Dock {
  /** the zone drawn as the rail */
  id: string
  /** its width, drawn */
  w: number
  /** the row it is drawn at the end of, in the tree as kept */
  split: Split
  /** the end of the row it is drawn at */
  at: 'start' | 'end'
  /** drawn away from its place in the row (it was not at that end) */
  moved: boolean
  /** the column it is kept in and drawn out of, when it is in one */
  from?: Split
}

/** The zones of `tree`, laid out in `rects`, that `want` a rail's width:
 *  one a row. A zone held directly by a row docks at that row's end; one in
 *  a column, at the end of the nearest row above it. No row that has
 *  wrapped docks one. */
export function docks(tree: Node, rects: Map<Node, Rect>, want: (z: Zone, r: Rect) => number | null): Dock[] {
  const out: Dock[] = []
  const used = new Set<Split>()
  const walk = (n: Node, up: Split[]) => {
    if (n.type === 'split') { n.kids.forEach((k) => walk(k, [...up, n])); return }
    const kr = rects.get(n)
    const w = kr ? want(n, kr) : null
    const parent = up[up.length - 1]
    if (!kr || w === null || w >= kr.w || !parent) return
    const row = [...up].reverse().find((s) => s.dir === 'row')
    const r = row && rects.get(row)
    if (!row || !r || used.has(row) || wrapped(row, rects)) return
    const at = kr.x + kr.w / 2 <= r.x + r.w / 2 ? 'start' : 'end'
    const from = parent === row ? undefined : parent
    const i = row.kids.indexOf(n)
    used.add(row)
    out.push({ id: n.id, w, split: row, at, moved: !!from || (at === 'start' ? i !== 0 : i !== row.kids.length - 1), ...(from ? { from } : {}) })
  }
  walk(tree, [])
  return out
}

/** The tree as it is drawn with `ds` docked: each docked row with its rail
 *  at its end, the rail's share its width, the others' the rest in their
 *  own proportion -- so a boundary between two of them moves as it is
 *  dragged; a rail kept in a column drawn out of it, the column's others
 *  sharing it in their own proportion (one left is the column). Drawn with
 *  `place(..., fixedOf(ds))`. */
export function docked(tree: Node, ds: Dock[], rects: Map<Node, Rect>): Node {
  const rows = new Map(ds.map((d) => [d.split, d]))
  const lifts = new Map(ds.filter((d) => d.from).map((d) => [d.from!, d]))
  const rebuild = (n: Node): Node => {
    if (n.type === 'zone') return n
    let kids = n.kids.map(rebuild)
    let sizes = n.sizes
    const lift = lifts.get(n)
    if (lift) {
      const stay = n.kids.map((_, j) => j).filter((j) => { const k = n.kids[j]; return k.type !== 'zone' || k.id !== lift.id })
      if (stay.length === 1) return kids[stay[0]]
      const rest = stay.reduce((a, j) => a + n.sizes[j], 0) || 1
      kids = stay.map((j) => kids[j])
      sizes = stay.map((j) => n.sizes[j] / rest)
    }
    const d = rows.get(n)
    const r = rects.get(n)
    if (d && r && d.from) {
      const rail = d.from.kids.find((k) => k.type === 'zone' && k.id === d.id)
      if (rail) {
        const along = r.w - GUTTER * kids.length
        const others = sizes.map((s) => s * ((along - d.w) / along))
        kids = d.at === 'start' ? [rail, ...kids] : [...kids, rail]
        sizes = d.at === 'start' ? [d.w / along, ...others] : [...others, d.w / along]
      }
    } else if (d && r) {
      const i = n.kids.findIndex((k) => k.type === 'zone' && k.id === d.id)
      if (i >= 0) {
        const along = r.w - GUTTER * (n.kids.length - 1)
        const rest = 1 - n.sizes[i] || 1
        const others = n.kids.map((_, j) => j).filter((j) => j !== i)
        const order = d.at === 'start' ? [i, ...others] : [...others, i]
        const size = (j: number) => (j === i ? d.w / along : (n.sizes[j] / rest) * ((along - d.w) / along))
        kids = order.map((j) => kids[j])
        sizes = order.map(size)
      }
    }
    return kids.length === n.kids.length && kids.every((k, j) => k === n.kids[j]) && sizes === n.sizes ? n : { ...n, kids, sizes }
  }
  return rebuild(tree)
}

export const fixedOf = (ds: Dock[]) => new Map(ds.map((d) => [d.id, d.w]))

/** A drawn tree's edit (a boundary moved, evened) read back into the tree as
 *  kept: its order, and each rail's own share, as they were -- a rail drawn
 *  out of its column back in it -- and the others' shares in the proportion
 *  the edit gave them. */
export function undocked(kept: Node, drawn: Node, ds: Dock[]): Node {
  const rails = new Set(ds.map((d) => d.id))
  const isRail = (k: Node) => k.type === 'zone' && rails.has(k.id)
  /* what a node is, but for the rails drawn elsewhere */
  const key = (n: Node) => zones(n).map((z) => z.id).filter((id) => !rails.has(id)).sort().join(' ')
  const back = (s: Node, d: Node): Node => {
    if (s.type === 'zone') return s
    /* a column left holding one zone besides its rail is drawn as that one */
    const stay = s.kids.filter((k) => !isRail(k))
    if (stay.length === 1 && stay.length < s.kids.length && !(d.type === 'split' && d.kids.some(isRail))) {
      const k = stay[0]
      const nk = back(k, d)
      return nk === k ? s : { ...s, kids: s.kids.map((x) => (x === k ? nk : x)) }
    }
    if (d.type === 'zone') return s
    const match = s.kids.map((k) => (isRail(k) ? -1 : d.kids.findIndex((x) => !isRail(x) && key(x) === key(k))))
    if (match.some((j, i) => j < 0 && !isRail(s.kids[i]))) return s
    const kids = s.kids.map((k, i) => (match[i] < 0 ? k : back(k, d.kids[match[i]])))
    const railShare = s.kids.reduce((a, k, i) => a + (isRail(k) ? s.sizes[i] : 0), 0)
    const rest = match.reduce((a, j) => a + (j < 0 ? 0 : d.sizes[j]), 0) || 1
    const sizes = match.map((j, i) => (j < 0 ? s.sizes[i] : (d.sizes[j] / rest) * (1 - railShare)))
    const same = kids.every((k, j) => k === s.kids[j]) && sizes.every((x, j) => Math.abs(x - s.sizes[j]) < 1e-9)
    return same ? s : { ...s, kids, sizes }
  }
  return back(kept, drawn)
}

/** Can this zone be cut in two along `dir` and leave both halves usable?
 *  `keep`: what it shows stays that many px across (Home's conversation,
 *  READABLE), so cut side by side it needs that and a new zone beside it. */
export function canSplit(r: Rect | undefined, dir: 'row' | 'col', keep = 0): boolean {
  if (!r) return false
  return dir === 'row' ? r.w >= Math.max(MIN_W, keep) + MIN_W + GUTTER : r.h >= 2 * MIN_H + GUTTER
}

/** Why this zone cannot be cut along `dir` (adm-c93a 5.3: "Split: disabled,
 *  with the reason, below the minimums"); null when it can. */
export function whyNoSplit(r: Rect | undefined, dir: 'row' | 'col', stacked = false, keep = 0): string | null {
  if (stacked) return 'The zones are stacked at this width: widen the window to split'
  if (!r) return 'Not measured yet'
  if (canSplit(r, dir, keep)) return null
  if (dir === 'row' && keep > MIN_W)
    return `Needs ${keep + MIN_W + GUTTER} px across, this zone is ${Math.round(r.w)}: it keeps ${keep} px to stay readable, and a new zone is at least ${MIN_W}`
  return dir === 'row'
    ? `Needs ${2 * MIN_W + GUTTER} px across, this zone is ${Math.round(r.w)}: zones are at least ${MIN_W} px wide`
    : `Needs ${2 * MIN_H + GUTTER} px high, this zone is ${Math.round(r.h)}: zones are at least ${MIN_H} px high`
}

/** The part of a zone `w` px across that stays with it, cut side by side,
 *  so it keeps `keep` px: half, when half is that much; else `keep`, and the
 *  new zone the rest. Never less than `keep` once laid out: a cut that joins
 *  its parent row loses its gutter from the whole row, not from this zone. */
export function keepShare(w: number, keep = 0): number {
  const along = w - GUTTER
  return along <= 0 || along / 2 >= keep ? 0.5 : Math.min(1, keep / along)
}

/* -- edits ------------------------------------------------------------------- */

const clone = (n: Node): Node => (n.type === 'zone' ? { ...n } : { ...n, kids: n.kids.map(clone), sizes: [...n.sizes] })

function findPath(n: Node, id: string, path: number[] = []): number[] | null {
  if (n.type === 'zone') return n.id === id ? path : null
  for (let i = 0; i < n.kids.length; i++) {
    const p = findPath(n.kids[i], id, [...path, i])
    if (p) return p
  }
  return null
}
const at = (n: Node, path: number[]): Node => path.reduce<Node>((m, i) => (m as Split).kids[i], n)

/** Cut a zone in two. What it holds stays in the first half; the new half is
 *  `made` (by default: a zone following what is read). A cut the same way as
 *  its parent joins the parent rather than nesting. `share`: the part of it
 *  the zone keeps (half by default; `keepShare`). */
export function splitZone(tree: Node, id: string, dir: 'row' | 'col', made?: Zone, before = false, share = 0.5): { tree: Node; made: Zone } {
  const t = clone(tree)
  const path = findPath(t, id)
  const fresh = made ?? zone(t)
  if (!path) return { tree, made: fresh }
  const target = at(t, path) as Zone
  const pair = before ? [fresh, target] : [target, fresh]
  const parts = before ? [1 - share, share] : [share, 1 - share]
  if (path.length === 0) return { tree: { type: 'split', dir, kids: pair, sizes: parts }, made: fresh }
  const parent = at(t, path.slice(0, -1)) as Split
  const i = path[path.length - 1]
  if (parent.dir === dir) {
    const s = parent.sizes[i]
    parent.kids.splice(before ? i : i + 1, 0, fresh)
    parent.sizes.splice(i, 1, ...parts.map((p) => s * p))
  } else {
    parent.kids[i] = { type: 'split', dir, kids: pair, sizes: parts }
  }
  return { tree: t, made: fresh }
}

/** The zones directly beside zone `id` in the split that holds it, the one
 *  after it first. */
export function besideZone(tree: Node, id: string): Zone[] {
  const path = findPath(tree, id)
  if (!path || !path.length) return []
  const parent = at(tree, path.slice(0, -1)) as Split
  const i = path[path.length - 1]
  return [parent.kids[i + 1], parent.kids[i - 1]].filter((k): k is Zone => !!k && k.type === 'zone')
}

/* A split left holding one child is replaced by it, and flattened into its
   own parent when they run the same way. */
function collapse(t: Node, pp: number[]): Node {
  const parent = at(t, pp) as Split
  if (parent.kids.length !== 1) return t
  const only = parent.kids[0]
  if (pp.length === 0) return only
  const gp = at(t, pp.slice(0, -1)) as Split
  const j = pp[pp.length - 1]
  if (only.type === 'split' && only.dir === gp.dir) {
    gp.kids.splice(j, 1, ...only.kids)
    gp.sizes.splice(j, 1, ...only.sizes.map((s) => s * gp.sizes[j]))
  } else gp.kids[j] = only
  return t
}

/** Close a zone: its presentation goes, nothing else. Its neighbour takes its space. */
export function closeZone(tree: Node, id: string): Node {
  const t = clone(tree)
  const path = findPath(t, id)
  if (!path || path.length === 0) return tree
  const parent = at(t, path.slice(0, -1)) as Split
  const i = path[path.length - 1]
  const ni = i > 0 ? i - 1 : 1
  parent.sizes[ni] += parent.sizes[i]
  parent.kids.splice(i, 1)
  parent.sizes.splice(i, 1)
  return collapse(t, path.slice(0, -1))
}

function nearest(parent: Split, i: number): number {
  for (let d = 1; d < parent.kids.length; d++)
    for (const j of [i - d, i + d]) if (j >= 0 && j < parent.kids.length && parent.kids[j].type === 'zone') return j
  return -1
}

/** Can this zone merge into a zone beside it in the same split? */
export function canMerge(tree: Node, id: string): boolean {
  const path = findPath(tree, id)
  if (!path || path.length === 0) return false
  return nearest(at(tree, path.slice(0, -1)) as Split, path[path.length - 1]) >= 0
}

/** Take a zone out into its neighbour (`into`, else the nearest sibling
 *  zone): the neighbour takes its space and what was kept in it, after its
 *  own. What the neighbour follows is unchanged. `into` may be a zone inside
 *  a sibling that is itself split (opr-3c4e8ba64f56): that sibling takes the
 *  space, the zone named takes what was kept. */
export function mergeZone(tree: Node, id: string, into?: string): { tree: Node; into: Zone | null } {
  const t = clone(tree)
  const path = findPath(t, id)
  if (!path || path.length === 0) return { tree, into: null }
  const parent = at(t, path.slice(0, -1)) as Split
  const i = path[path.length - 1]
  const gone = parent.kids[i] as Zone
  const ni = into ? parent.kids.findIndex((k, j) => j !== i && zones(k).some((z) => z.id === into)) : nearest(parent, i)
  if (ni < 0) return { tree, into: null }
  const target = into ?? (parent.kids[ni] as Zone).id
  parent.kids[ni] = updateZone(parent.kids[ni], target, (z) =>
    z.slot && gone.slot ? { ...z, slot: { ...z.slot, items: [...new Set([...z.slot.items, ...gone.slot.items])] } } : { ...z })
  const n = findZone(parent.kids[ni], target)!
  parent.sizes[ni] += parent.sizes[i]
  parent.kids.splice(i, 1)
  parent.sizes.splice(i, 1)
  return { tree: collapse(t, path.slice(0, -1)), into: n }
}

/** Move the boundary after child `i` of `split` so child `i` is `first`
 *  pixels, held to both sides' minimums. */
export function resize(tree: Node, split: Split, i: number, first: number, rects: Map<Node, Rect>, wrap = false): { tree: Node; stopped: boolean; split: Split } {
  const r = rects.get(split)
  if (!r) return { tree, stopped: false, split }
  const axis = split.dir === 'row' ? 'w' : 'h'
  const along = (split.dir === 'row' ? r.w : r.h) - GUTTER * (split.kids.length - 1)
  const total = (split.sizes[i] + split.sizes[i + 1]) * along
  const lo = minSize(split.kids[i], axis, wrap)
  const hi = total - minSize(split.kids[i + 1], axis, wrap)
  const a = Math.max(lo, Math.min(hi, first))
  const sizes = [...split.sizes]
  sizes[i] = a / along
  sizes[i + 1] = (total - a) / along
  const next = { ...split, sizes }
  return { tree: replaceSplit(tree, split, next), stopped: a !== first, split: next }
}

/** WIDEN ZONE `id` TO `want` PIXELS ACROSS (Home's conversation, opened out
 *  of its rail): the row nearest it gives the room, taken from the zones
 *  beside it -- the nearest first -- and never below their minimums. The
 *  same as dragging its dividers: only shares change. Null when they cannot
 *  give that much, or when nothing beside it shares its row (it is as wide
 *  as the page, or its row has wrapped onto more lines). */
export function widenZone(tree: Node, id: string, want: number, rects: Map<Node, Rect>, wrap = false): Node | null {
  const path = findPath(tree, id)
  if (!path) return null
  for (let d = path.length - 1; d >= 0; d--) {
    const split = at(tree, path.slice(0, d)) as Split
    if (split.dir !== 'row') continue
    const r = rects.get(split)
    if (!r || wrapped(split, rects)) return null
    const i = path[d]
    const ws = split.kids.map((k) => rects.get(k)?.w ?? 0)
    let need = want - ws[i]
    if (need <= 0) return tree
    const order = split.kids.map((_, j) => j).filter((j) => j !== i).sort((a, b) => Math.abs(a - i) - Math.abs(b - i) || b - a)
    const spare = (j: number) => Math.max(0, ws[j] - minSize(split.kids[j], 'w', wrap))
    if (order.reduce((s, j) => s + spare(j), 0) < need) return null
    ws[i] = want
    for (const j of order) {
      const take = Math.min(need, spare(j))
      ws[j] -= take
      need -= take
      if (need <= 0) break
    }
    const along = r.w - GUTTER * (split.kids.length - 1)
    return replaceSplit(tree, split, { ...split, sizes: ws.map((w) => w / along) })
  }
  return null
}

/** The bounds a divider moves within, in pixels for child `i`. */
export function bounds(split: Split, i: number, rects: Map<Node, Rect>, wrap = false): { lo: number; hi: number; along: number } {
  const r = rects.get(split)!
  const axis = split.dir === 'row' ? 'w' : 'h'
  const along = (split.dir === 'row' ? r.w : r.h) - GUTTER * (split.kids.length - 1)
  const total = (split.sizes[i] + split.sizes[i + 1]) * along
  return { lo: minSize(split.kids[i], axis, wrap), hi: total - minSize(split.kids[i + 1], axis, wrap), along }
}

export function even(tree: Node, split: Split): Node {
  return replaceSplit(tree, split, { ...split, sizes: split.kids.map(() => 1 / split.kids.length) })
}

function replaceSplit(n: Node, old: Split, next: Split): Node {
  if (n === old) return next
  if (n.type === 'zone') return n
  return { ...n, kids: n.kids.map((k) => replaceSplit(k, old, next)) }
}

export function updateZone(n: Node, id: string, f: (z: Zone) => Zone): Node {
  if (n.type === 'zone') return n.id === id ? f(n) : n
  return { ...n, kids: n.kids.map((k) => updateZone(k, id, f)) }
}

/* -- Fluid Focus edits ------------------------------------------------------- */

/** Exchange two leaf records without changing either path or any share. */
export function swapLeaves(tree: Node, aId: string, bId: string): Node {
  if (aId === bId) return tree
  const a = findZone(tree, aId), b = findZone(tree, bId)
  if (!a || !b) return tree
  const swap = (n: Node): Node => {
    if (n.type === 'zone') return n.id === aId ? b : n.id === bId ? a : n
    const kids = n.kids.map(swap)
    return kids.some((k, i) => k !== n.kids[i]) ? { ...n, kids } : n
  }
  return swap(tree)
}

/** Put `zone` in the leaf occupied by `id`, preserving the tree's geometry. */
export function replaceZone(tree: Node, id: string, zone: Zone): Node {
  if (tree.type === 'zone') return tree.id === id ? zone : tree
  let changed = false
  const kids = tree.kids.map((k) => {
    const next = replaceZone(k, id, zone)
    changed ||= next !== k
    return next
  })
  return changed ? { ...tree, kids } : tree
}

/** Remove a leaf and give its share to its adjacent branch. Unlike merge,
 *  this never moves kept items into the neighbour. */
export function removeLeaf(tree: Node, id: string): Node {
  return closeZone(tree, id)
}

export const findZone = (n: Node, id: string): Zone | undefined => zones(n).find((z) => z.id === id)

/** Keep `address` in zone `id` (after what it keeps), and take it out of
 *  `from` when it is moved rather than kept again. */
export function keepIn(tree: Node, id: string, address: string): Node {
  return updateZone(tree, id, (z) => {
    const s = z.slot ?? keepSlot()
    return s.items.includes(address) ? z : { ...z, slot: { ...s, items: [...s.items, address] } }
  })
}
export function unkeep(tree: Node, id: string, address: string): Node {
  return updateZone(tree, id, (z) => (z.slot ? { ...z, slot: { ...z.slot, items: z.slot.items.filter((a) => a !== address) } } : z))
}

/** Every address kept anywhere on a tree. */
export const itemsOf = (n: Node): string[] => zones(n).flatMap((z) => z.slot?.items ?? [])

/* -- reading one back --------------------------------------------------------- */

const SHOWS = new Set(['objects', 'everything', 'sections', 'media', 'files', 'forms', 'fillable', 'kinds', 'needs-you'])
const PRESENTS = new Set(['cards', 'gallery', 'slides', 'list', 'focus', 'previews', 'across'])
/** A post a zone is held on, as the server takes it (lab_workspaces._TURN),
 *  and only on a zone that follows (arrangements._slot); null is no pin, on
 *  any zone, as there. */
const PIN = /^[A-Za-z0-9_.:-]{1,80}$/

/** A tree read back from storage is only trusted when it is well formed. */
export function valid(n: unknown, depth = 0): n is Node {
  if (!n || typeof n !== 'object' || depth > 8) return false
  const o = n as Record<string, unknown>
  if (o.type === 'zone') {
    if (typeof o.id !== 'string' || typeof o.show !== 'string') return false
    if (o.slot === undefined) return true
    const s = o.slot as Record<string, unknown>
    return !!s && typeof s.follow === 'boolean' && SHOWS.has(s.show as string) && Array.isArray(s.items)
      && (s.items as unknown[]).every((a) => typeof a === 'string') && PRESENTS.has(s.present as string)
      && (s.pin === undefined || s.pin === null || (s.follow === true && typeof s.pin === 'string' && PIN.test(s.pin)))
  }
  if (o.type !== 'split' || (o.dir !== 'row' && o.dir !== 'col')) return false
  const kids = o.kids as unknown[]
  const sizes = o.sizes as unknown[]
  return Array.isArray(kids) && Array.isArray(sizes) && kids.length >= 2 && kids.length === sizes.length
    && sizes.every((s) => typeof s === 'number' && Number.isFinite(s)) && kids.every((k) => valid(k, depth + 1))
}

/** Every zone named, so "Keep in @Side" can say where. */
export function named(n: Node): Node {
  let t = n
  for (const z of zones(n)) if (!z.name) t = updateZone(t, z.id, (x) => ({ ...x, name: freshName(t) }))
  return t
}
