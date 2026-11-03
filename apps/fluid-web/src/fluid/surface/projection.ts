/* WHAT THIS DEVICE SHOWS OF A PAGE (plan §3.9 item 3; part P5).
 *
 * Close is this browser device's, per presentation class (deviceLocal.ts):
 * a closed surface stays in the arrangement, byte for byte, and is only not
 * drawn here. This is how the drawing leaves it out, browser-free:
 *
 *   - projectVisibleTree(tree, closed): the tree TreeView draws. A closed
 *     leaf is taken out as closeZone takes one out -- its share goes to the
 *     sibling before it (the one after, when it was first) -- and a page
 *     whose every leaf is closed draws the empty page (EMPTY_HERE). The stored
 *     tree is never touched; the same tree and set give the same object back,
 *     so what TreeView drew is what an edit is made on.
 *   - storedTree(stored, edited): the stored tree an edit of the drawn tree
 *     stands for: the edit, with each closed leaf put back where it was
 *     taken from, at its share. No edit, no change: the stored tree itself.
 *   - openFloats / closedHere: the windows still open here (the rendered
 *     count), and what is closed here, for Reopen.
 *
 * Which surfaces offer Close, and where, is a rule held open for the owner
 * (Turn #1442): CLOSE_HERE below. */

import { CONVERSATION_SHOW, type Float } from '../focus/types'
import { closeZone, emptyZone, freshId, zones, type Node, type Split, type Zone } from '../workspace/tree'
import type { PlacementKind, SurfaceKind, ZoneId } from './types'

/** Where × Close (this device) is drawn, by surface kind and where it is.
 *  Stack cards and sheets always draw ×, as P4 drew them (chrome.ts
 *  closeShown); a docked section and a window draw it too; the conversation's
 *  own section never does, nor Home's zones (another holder). HELD OPEN for
 *  the owner (Turn #1442): change it here. */
export const CLOSE_HERE: Partial<Record<SurfaceKind, readonly PlacementKind[]>> = {
  section: ['dock', 'stack', 'sheet'],
  float: ['float', 'stack', 'sheet'],
  magnet: ['dock', 'float', 'stack', 'sheet'],
  conversation: ['stack', 'sheet'],
}
export const closeOffered = (kind: SurfaceKind, at: PlacementKind): boolean => !!CLOSE_HERE[kind]?.includes(at)

/** The id of the empty leaf drawn when every leaf of a page is closed here:
 *  the empty page (tree.ts emptyZone), never a section following what is read. */
export const EMPTY_HERE = 'closed-here-empty'
const emptyLeaf = (): Zone => emptyZone(EMPTY_HERE)

/** One closed leaf, as it was taken out: enough to put it back. */
interface Taken {
  leaf: Zone
  /** the split it was in, by direction */
  dir: Split['dir']
  /** the leaves of the sibling that took its share */
  near: string[]
  /** it was before that sibling (it was first in its split) */
  before: boolean
  /** its share of the two, it and that sibling */
  share: number
}
/** `last`: every leaf was closed, and this is the one left when the others
 *  had been taken out (the empty leaf is drawn in its place). */
interface Projection { tree: Node; taken: Taken[]; last: Zone | null }

const cache = new WeakMap<Node, { key: string; p: Projection }>()
const keyOf = (ids: string[]) => ids.join('\u0000')

function project(tree: Node, closed: ReadonlySet<ZoneId>): Projection {
  const hidden = zones(tree).filter((z) => closed.has(z.id)).map((z) => z.id)
  if (!hidden.length) return { tree, taken: [], last: null }
  const key = keyOf(hidden)
  const hit = cache.get(tree)
  if (hit && hit.key === key) return hit.p
  let t = tree
  const taken: Taken[] = []
  let last: Zone | null = null
  for (const id of hidden) {
    if (t.type === 'zone') { last = t; break }
    const at = parentOf(t, id)!
    const ni = at.i > 0 ? at.i - 1 : 1
    const mine = at.parent.sizes[at.i], theirs = at.parent.sizes[ni]
    taken.push({ leaf: at.parent.kids[at.i] as Zone, dir: at.parent.dir, near: zones(at.parent.kids[ni]).map((z) => z.id),
      before: at.i < ni, share: mine + theirs > 0 ? mine / (mine + theirs) : 0.5 })
    t = closeZone(t, id)
  }
  const p: Projection = { tree: last ? emptyLeaf() : t, taken, last }
  cache.set(tree, { key, p })
  return p
}

/** `n` without the drawn-only empty leaf, as closeZone takes a leaf out;
 *  null when nothing else is left. The empty leaf changed (something kept in
 *  it) is a real zone now, under an id of its own. */
function withoutEmpty(n: Node): Node | null {
  const e = zones(n).find((z) => z.id === EMPTY_HERE)
  if (!e) return n
  if (JSON.stringify(e) !== JSON.stringify(emptyLeaf())) {
    const real = (x: Node): Node => (x.type === 'zone' ? (x.id === EMPTY_HERE ? { ...x, id: freshId('z') } : x) : { ...x, kids: x.kids.map(real) })
    return real(n)
  }
  return n.type === 'zone' ? null : closeZone(n, EMPTY_HERE)
}

/** The tree drawn on this device: `tree` without the leaves closed here. */
export const projectVisibleTree = (tree: Node, closed: ReadonlySet<ZoneId>): Node => project(tree, closed).tree

/** The stored tree an edit of the drawn tree stands for. `edited` is what the
 *  edit made of projectVisibleTree(stored, closed). */
export function storedTree(stored: Node, closed: ReadonlySet<ZoneId>, edited: Node): Node {
  const p = project(stored, closed)
  if (edited === p.tree) return stored
  if (p.last) {
    /* every leaf was closed: the stored tree is kept whole, and what was
       made over the empty leaf goes beside it */
    const made = withoutEmpty(edited)
    if (!made) return stored
    return { type: 'split', dir: 'row', kids: [stored, made], sizes: [0.5, 0.5] }
  }
  let t: Node = edited
  for (let i = p.taken.length - 1; i >= 0; i--) t = put(t, p.taken[i])
  return t
}

/** Put a closed leaf back beside the sibling that took its share; that
 *  sibling gone, at the end of the tree. */
function put(t: Node, x: Taken): Node {
  if (zones(t).some((z) => z.id === x.leaf.id)) return t
  const target = x.near.length ? nodeOf(t, new Set(x.near)) : null
  if (!target) return t.type === 'split' && t.dir === x.dir
    ? { ...t, kids: [...t.kids, x.leaf], sizes: [...t.sizes.map((s) => s * (1 - 1 / (t.kids.length + 1))), 1 / (t.kids.length + 1)] }
    : { type: 'split', dir: x.dir, kids: [t, x.leaf], sizes: [0.5, 0.5] }
  return replace(t, target.node, target.parent, (n, parent, i) => {
    const pair = x.before ? [x.leaf, n] : [n, x.leaf]
    const parts = x.before ? [x.share, 1 - x.share] : [1 - x.share, x.share]
    if (parent && parent.dir === x.dir) {
      const s = parent.sizes[i]
      const kids = [...parent.kids], sizes = [...parent.sizes]
      kids.splice(i, 1, ...pair)
      sizes.splice(i, 1, ...parts.map((q) => s * q))
      return { kind: 'parent', node: { ...parent, kids, sizes } }
    }
    return { kind: 'self', node: { type: 'split', dir: x.dir, kids: pair, sizes: parts } }
  })
}

/** The node whose leaves are exactly `ids` (the sibling as it was), else the
 *  smallest holding them all, else the leaf of theirs that is still there. */
function nodeOf(t: Node, ids: Set<string>): { node: Node; parent: Split | null } | null {
  const all: { node: Node; parent: Split | null; leaves: string[] }[] = []
  const walk = (n: Node, parent: Split | null) => {
    all.push({ node: n, parent, leaves: zones(n).map((z) => z.id) })
    if (n.type === 'split') n.kids.forEach((k) => walk(k, n))
  }
  walk(t, null)
  const holds = all.filter((x) => [...ids].every((id) => x.leaves.includes(id))).sort((a, b) => a.leaves.length - b.leaves.length)
  const exact = holds.find((x) => x.leaves.length === ids.size)
  const any = all.find((x) => x.node.type === 'zone' && ids.has(x.node.id))
  const got = exact ?? holds[0] ?? any
  return got ? { node: got.node, parent: got.parent } : null
}

type Swap = { kind: 'self' | 'parent'; node: Node }
/** `t` with `target` (child of `parent`) swapped by `f`: itself, or its parent. */
function replace(t: Node, target: Node, parent: Split | null, f: (n: Node, parent: Split | null, i: number) => Swap): Node {
  const i = parent ? parent.kids.indexOf(target) : -1
  const s = f(target, parent, i)
  const swapFrom = s.kind === 'parent' ? parent! : target
  if (t === swapFrom) return s.node
  const walk = (n: Node): Node => (n === swapFrom ? s.node : n.type === 'zone' ? n : { ...n, kids: n.kids.map(walk) })
  return walk(t)
}

function parentOf(n: Node, id: string): { parent: Split; i: number } | null {
  if (n.type === 'zone') return null
  for (let i = 0; i < n.kids.length; i++) {
    const k = n.kids[i]
    if (k.type === 'zone' && k.id === id) return { parent: n, i }
    const got = parentOf(k, id)
    if (got) return got
  }
  return null
}

/** The windows still open on this device (the rendered count, plan §3.9
 *  item 6): a window closed here takes no room here, though its stored slot
 *  still counts against the 12. */
export const openFloats = (floats: readonly Float[], closed: ReadonlySet<ZoneId>): Float[] => floats.filter((f) => !closed.has(f.zone.id))

/** What is closed on this device on a page: its leaves and windows (the
 *  conversation's own, by what stands in for it), each once, for Reopen. */
export function closedHere(view: { tree: Node; focus?: { floats?: Float[]; column?: Zone } }, closed: ReadonlySet<ZoneId>,
  standIn?: Zone | null): { id: ZoneId; name: string }[] {
  if (!closed.size) return []
  const named = (z: Zone) => (z.show === CONVERSATION_SHOW ? standIn?.name ?? 'Conversation' : z.name ?? 'Zone')
  const out = new Map<ZoneId, string>()
  const column = view.focus?.column
  if (column && closed.has(column.id)) out.set(column.id, named(column))
  for (const z of zones(view.tree)) if (closed.has(z.id)) out.set(z.id, named(z))
  for (const f of [...(view.focus?.floats ?? [])].reverse()) if (closed.has(f.zone.id)) out.set(f.zone.id, named(f.zone))
  return [...out].map(([id, name]) => ({ id, name }))
}

/** Move up or down among the cards drawn (`shown`, in their order): the
 *  index in the class's whole stack order (`order`) a card goes to, or null
 *  at the end. Cards not drawn here keep their places. */
export function stackStep(order: readonly ZoneId[], shown: readonly ZoneId[], id: ZoneId, by: -1 | 1): number | null {
  const i = shown.indexOf(id)
  const j = i + by
  if (i < 0 || j < 0 || j >= shown.length) return null
  return order.indexOf(shown[j])
}
