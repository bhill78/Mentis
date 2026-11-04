/* WHERE A WORKSPACE'S DISCS ARE DRAWN, wide (Floats.tsx), browser-free.
 *
 * The server puts a new disc on its launcher's grid (mentis/fluid/arrangements.py
 * _launcher_slot): 96px apart and six to a row, room for the disc and not for its
 * name, its orbit or the column underneath. So a disc still on that grid is drawn
 * in the same slot of a roomier grid, held within `flow` (the column it stands
 * over) and clear of the left edge, and a disc moved off it stays where it was
 * put, unless that would clip or cover another.
 *
 * DRAWING ONLY: as the Focus bar's lift, nothing here is saved. A saved rectangle
 * is unchanged, so another device or a wider window draws from it afresh. A slot
 * keeps its cell whichever disc is raised or opened, so nothing moves under the
 * pointer; a slide-out takes its disc's cell. */

/** The server's grid (arrangements.py _LAUNCHER_ORIGIN, _LAUNCHER_PITCH, _LAUNCHER_COLUMNS). */
const LAUNCHER = { origin: 24, pitch: 96, columns: 6 }

/** What a disc takes up beyond its 56px, from its corner: its orbit above it and
 *  its name, at most two lines and 104px wide, below it. */
export const DISC_FOOT = { left: 24, top: 14, right: 80, bottom: 103 }
/** The roomier grid: a cell apart, no two feet touch. */
export const DISC_CELL = { x0: 28, y0: 24, w: 108, h: 118 }

export interface DiscAt { x: number; y: number }
export interface DiscRoom {
  /** how far right a row of cells may run: the column under them, or the room */
  flow: number
  /** the windows' layer, when it has been measured */
  w?: number
  h?: number
}

/** How far right the cells run: the column they stand over, however narrow it is
 *  drawn (never fewer than three cells); with no column drawn, the room. */
export const discFlow = (column: number | null, roomW: number): number =>
  column == null ? roomW : Math.max(column, DISC_CELL.x0 + 2 * DISC_CELL.w + DISC_FOOT.right)

const slotOf = (x: number, y: number): number | null => {
  const col = (x - LAUNCHER.origin) / LAUNCHER.pitch, row = (y - LAUNCHER.origin) / LAUNCHER.pitch
  return Number.isInteger(col) && Number.isInteger(row) && col >= 0 && col < LAUNCHER.columns && row >= 0 ? row * LAUNCHER.columns + col : null
}

const clash = (a: DiscAt, b: DiscAt): boolean =>
  a.x - DISC_FOOT.left < b.x + DISC_FOOT.right && b.x - DISC_FOOT.left < a.x + DISC_FOOT.right
  && a.y - DISC_FOOT.top < b.y + DISC_FOOT.bottom && b.y - DISC_FOOT.top < a.y + DISC_FOOT.bottom

/** How many cells a row holds: at least one, and the whole of each foot within `flow`. */
const perRow = (flow: number): number => Math.max(1, Math.floor((flow - DISC_CELL.x0 - DISC_FOOT.right) / DISC_CELL.w) + 1)

/** Where each disc is drawn, by its id. Asked of stored positions and never of
 *  their order, which raising a window changes. */
export function settledDiscs<D extends DiscAt & { id: string }>(discs: readonly D[], room: DiscRoom): Map<string, DiscAt> {
  const across = perRow(room.flow)
  const cell = (n: number): DiscAt => ({ x: DISC_CELL.x0 + (n % across) * DISC_CELL.w, y: DISC_CELL.y0 + Math.floor(n / across) * DISC_CELL.h })
  const byPlace = [...discs].sort((a, b) => a.y - b.y || a.x - b.x || (a.id < b.id ? -1 : 1))
  const out = new Map<string, DiscAt>()
  const free = (at: DiscAt) => ![...out.values()].some((o) => clash(o, at))
  /* first where somebody put them, then the launcher's around them */
  for (const d of byPlace) {
    if (slotOf(d.x, d.y) != null) continue
    const held = {
      x: Math.max(DISC_FOOT.left, room.w ? Math.min(d.x, room.w - DISC_FOOT.right) : d.x),
      y: Math.max(DISC_FOOT.top, room.h ? Math.min(d.y, room.h - DISC_FOOT.bottom) : d.y),
    }
    let at = held
    for (let n = 0; !free(at); n++) at = cell(n)
    out.set(d.id, at)
  }
  for (const d of byPlace) {
    const slot = slotOf(d.x, d.y)
    if (slot == null) continue
    let n = slot
    while (!free(cell(n))) n++
    out.set(d.id, cell(n))
  }
  return out
}

/** How far down the discs reach over a column of `width`, counting only those
 *  that run on from its top: one moved further down covers what it was put on,
 *  and reserves nothing. 0 when none stands over it. */
export function discsReach(drawn: Iterable<DiscAt>, width: number): number {
  let reach = 0
  const over = [...drawn].filter((d) => d.x - DISC_FOOT.left < width).sort((a, b) => a.y - b.y)
  for (const d of over) if (d.y - DISC_FOOT.top < (reach || DISC_CELL.y0)) reach = Math.max(reach, d.y + DISC_FOOT.bottom + 8)
  return reach
}
