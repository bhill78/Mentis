/* ------------------------------------------------------------------------ *
 * WHERE A DURABLE THING SITS IN SPACE, AND HOW IT IS SEEN FROM HERE.
 *
 * THE BEHAVIOUR IS MARK III's 3D BRAIN; THE DATA IS MARK IV's OWN. What is
 * carried across is how that view placed, projected and fogged a population
 * -- the parts the owner judged made it the best version -- and none of its
 * data model. Positions are drawn from facts `/api/space` states and claim
 * nothing beyond them:
 *
 *   REGION   the Conversation the record puts a thing in. Two things near
 *            each other are, at most, in the same Conversation; that IS a
 *            relation the record holds and the surface may say so.
 *   HEIGHT   the layer its Kind declares, read from the server's ladder:
 *            what directs work above what is known, above the structure,
 *            above the talk, above acquired material.
 *   THE REST a hash of the thing's own id: arbitrary, so it asserts nothing,
 *            and deterministic, so the Brain somebody learns their way around
 *            is the same one next time. No force simulation; nothing settles.
 *
 * PROXIMITY IS NEVER A RELATIONSHIP. The only strands are links the record
 * holds, handed over by the server; nothing here infers a neighbour.
 *
 * NO LIBRARY. A plain perspective camera is a few multiplications a point;
 * a WebGL dependency would buy a bundle and a physics engine this does not
 * want (Mark III measured and refused the same).
 * ------------------------------------------------------------------------ */

export interface SpaceNode {
  entry: string
  kind: string
  layer: string
  conversation: string | null
  at: number | null
  summary: string | null
  /** its line ends in a deletion; its words are not given */
  deleted: boolean
  /** a Turn or Topic read at a later version than its first */
  edited: boolean
  /** something else took its place; it is still itself */
  replaced: boolean
}

export interface SpaceEdge {
  from: string
  to: string
  relation: string
}

export interface SpaceRead {
  nodes: SpaceNode[]
  edges: SpaceEdge[]
  conversations: Record<string, string | null>
  layers: string[]
  total: number
  omitted: number
  cap: number
  material: boolean
}

/** One durable thing, placed. World units, centred on the origin. */
export interface Placed {
  node: SpaceNode
  id: string
  x: number
  y: number
  z: number
}

/** A link the record holds between two placed things. Never a proximity. */
export interface Strand {
  from: Placed
  to: Placed
  relation: string
}

/** A stable number in [0, 1) from a string. Deterministic on purpose. */
export function hashed(said: string, salt: number): number {
  let h = 2166136261 ^ salt
  for (let i = 0; i < said.length; i += 1) {
    h ^= said.charCodeAt(i)
    h = Math.imul(h, 16777619)
  }
  /* Mixed before it is used: FNV alone leaves similar names close together,
     which put whole regions -- and colours -- on top of one another. */
  h ^= h >>> 16
  h = Math.imul(h, 0x85ebca6b)
  h ^= h >>> 13
  h = Math.imul(h, 0xc2b2ae35)
  h ^= h >>> 16
  return ((h >>> 0) % 100000) / 100000
}

/** HOLD DENSITY CONSTANT, NOT EXTENT: radius goes as the cube root of the
 *  population, so a Brain that grows for years gets wider, not denser. */
export function worldRadius(n: number): number {
  const REFERENCE = 200
  const ROOM = 300
  if (n < 1) return ROOM
  return ROOM * Math.cbrt(Math.max(n, 1) / REFERENCE)
}

/**
 * Place every node. ONE PASS, NO SIMULATION.
 *
 * Conversations are spread evenly over a sphere (golden angle), each taking
 * the slot its own id chooses, so a Conversation keeps its part of the sky.
 * A Conversation's own entry is its region's centre. Participants belong to
 * no one Conversation and sit at the core, where every region is equally
 * near; anything else the record places nowhere goes to the outskirts,
 * loose, because material nobody can place is not the heart of the Brain.
 */
export function place(nodes: SpaceNode[], layers: string[]): Placed[] {
  const radius = worldRadius(nodes.length)
  const regions: string[] = []
  const size = new Map<string, number>()
  for (const n of nodes) {
    if (!n.conversation) continue
    if (!size.has(n.conversation)) regions.push(n.conversation)
    size.set(n.conversation, (size.get(n.conversation) ?? 0) + 1)
  }
  const golden = Math.PI * (3 - Math.sqrt(5))
  const centres = new Map<string, [number, number, number]>()
  regions.forEach((r, i) => {
    const at = (i + hashed(r, 7)) / Math.max(regions.length, 1)
    const y = 1 - at * 2
    const ring = Math.sqrt(Math.max(0, 1 - y * y))
    const theta = golden * i + hashed(r, 11) * 0.6
    centres.set(r, [Math.cos(theta) * ring, y, Math.sin(theta) * ring])
  })

  /* THE LAYER IS HEIGHT, in the ladder's own order, over the layers present
     -- so a Brain with no acquired material does not keep a floor for it. */
  const present = layers.filter((l) => nodes.some((n) => n.layer === l))
  const span = Math.max(1, present.length - 1)
  const lift = (layer: string) => {
    const i = present.indexOf(layer)
    return i < 0 ? 0 : (0.5 - i / span) * radius * 0.5
  }

  return nodes.map((node) => {
    const id = node.entry
    const j = (salt: number) => hashed(id, salt) - 0.5
    const centre = node.conversation ? centres.get(node.conversation) : undefined
    if (centre) {
      /* A busy Conversation reads as a neighbourhood, a quiet one stays
         small -- and it reads as ONE neighbourhood: the spread is held well
         inside the gap between regions, and things gather toward the middle
         of their region rather than filling a box, so thirty-eight
         Conversations are thirty-eight clusters and not one even haze. */
      const here = size.get(node.conversation!) ?? 1
      const gap = radius * 1.6 / Math.sqrt(Math.max(regions.length, 1))
      const spread = Math.min(gap * 0.42, radius * 0.07 * Math.cbrt(Math.max(here, 1)))
      /* The Conversation itself holds the middle; its Topics stay near it. */
      const reach = node.entry === node.conversation ? 0 : node.kind === 'topic' ? 0.35 : 1
      const theta = hashed(id, 17) * Math.PI * 2
      const phi = Math.acos(2 * hashed(id, 19) - 1)
      const r = spread * Math.pow(hashed(id, 23), 0.75) * reach
      return {
        node,
        id,
        x: centre[0] * radius + Math.sin(phi) * Math.cos(theta) * r,
        y: centre[1] * radius * 0.75 + lift(node.layer) * 0.45 * (reach ? 1 : 0) + Math.cos(phi) * r * 0.7,
        z: centre[2] * radius + Math.sin(phi) * Math.sin(theta) * r,
      }
    }
    if (node.layer === 'who') {
      const a = hashed(id, 3) * Math.PI * 2
      const r = radius * (0.12 + hashed(id, 29) * 0.14)
      return { node, id, x: Math.cos(a) * r, y: j(5) * radius * 0.25, z: Math.sin(a) * r }
    }
    const a = hashed(id, 3) * Math.PI * 2
    return {
      node,
      id,
      x: Math.cos(a) * 1.25 * radius,
      y: j(5) * 2 * radius * 0.75 + lift(node.layer),
      z: Math.sin(a) * 1.25 * radius,
    }
  })
}

/** The links between placed things. BOTH ENDS MUST BE PLACED, and that is all. */
export function strands(placed: Placed[], edges: SpaceEdge[]): Strand[] {
  const held = new Map(placed.map((p) => [p.id, p]))
  const found: Strand[] = []
  for (const e of edges) {
    const from = held.get(e.from)
    const to = held.get(e.to)
    if (from && to) found.push({ from, to, relation: e.relation })
  }
  return found
}

/** Where the eye is. The Brain does not move; the viewer does. */
export interface Eye {
  turn: number
  /** clamped short of the poles so the world never inverts */
  rise: number
  /** distance from what it orbits */
  out: number
  /** WHAT IT ORBITS: the selection when there is one, so zoom goes toward it. */
  at: { x: number; y: number; z: number }
}

export interface Seen {
  sx: number
  sy: number
  depth: number
  ahead: boolean
  scale: number
}

/** Project one point. A plain perspective camera and nothing more. */
export function look(p: { x: number; y: number; z: number }, eye: Eye, width: number, height: number): Seen {
  const cosT = Math.cos(eye.turn)
  const sinT = Math.sin(eye.turn)
  const cosR = Math.cos(eye.rise)
  const sinR = Math.sin(eye.rise)
  const px = p.x - eye.at.x
  const py = p.y - eye.at.y
  const pz = p.z - eye.at.z
  const x1 = px * cosT - pz * sinT
  const z1 = px * sinT + pz * cosT
  const y2 = py * cosR - z1 * sinR
  const z2 = py * sinR + z1 * cosR
  const depth = z2 + eye.out
  const focal = Math.min(width, height) * 0.9
  const scale = focal / Math.max(depth, 1)
  return { sx: width / 2 + x1 * scale, sy: height / 2 - y2 * scale, depth, ahead: depth > 1, scale }
}

/**
 * How present a thing is at this depth, in [0, 1].
 *
 * FOG IS WHAT MAKES A SPACE FEEL LARGE, and the band travels with the eye:
 * the near face of the Brain is present, whatever is behind its far side has
 * gone, and flying inside gives a horizon. Eased, because a straight ramp
 * greys the middle of the Brain, which is where most of it is.
 */
export function presence(depth: number, radius: number, out: number): number {
  const near = Math.max(1, out - radius * 0.95)
  const far = out + radius * 1.9
  if (depth <= near) return 1
  if (depth >= far) return 0
  const t = (depth - near) / (far - near)
  return Math.max(0.06, 1 - t * t)
}

/** What the pointer is over, nearest the eye first. Screen space, so it
 *  matches what was drawn. */
export function under(at: { x: number; y: number }, drawn: (Placed & Seen)[], slack = 9): Placed | null {
  let best: Placed | null = null
  let bestDepth = Infinity
  let bestD = Infinity
  for (const d of drawn) {
    if (!d.ahead) continue
    const dx = d.sx - at.x
    const dy = d.sy - at.y
    const dd = dx * dx + dy * dy
    if (dd > slack * slack) continue
    /* Nearest to the pointer wins outright when it is clearly nearer; among
       near-ties the one in front does. */
    if (dd + 4 < bestD || (Math.abs(dd - bestD) <= 4 && d.depth < bestDepth)) {
      best = d
      bestDepth = d.depth
      bestD = dd
    }
  }
  return best
}

/* ---- colour, read from the theme --------------------------------------- */

/** A CSS colour as rgb, or null where it is not a syntax read here. */
export function rgbOf(colour: string): [number, number, number] | null {
  const said = (colour || '').trim().toLowerCase()
  if (said.startsWith('#')) {
    const body = said.slice(1)
    const parts =
      body.length === 3 || body.length === 4
        ? [...body.slice(0, 3)].map((c) => c + c)
        : body.length === 6 || body.length === 8
          ? [body.slice(0, 2), body.slice(2, 4), body.slice(4, 6)]
          : null
    if (!parts) return null
    const n = parts.map((c) => Number.parseInt(c, 16))
    return n.some(Number.isNaN) ? null : [n[0], n[1], n[2]]
  }
  const rgb = said.match(/^rgba?\(([^)]*)\)$/)
  if (rgb) {
    const n = rgb[1]
      .split(/[\s,/]+/)
      .filter(Boolean)
      .slice(0, 3)
      .map((v) => (v.endsWith('%') ? Number.parseFloat(v) * 2.55 : Number.parseFloat(v)))
    if (n.length < 3 || n.some(Number.isNaN)) return null
    return [Math.round(n[0]), Math.round(n[1]), Math.round(n[2])]
  }
  return null
}

/** A colour at an opacity; canvas cannot paint `color-mix`. An unreadable
 *  colour is drawn magenta so somebody SEES it, never a plausible wrong one. */
export function tint(colour: string, alpha: number): string {
  const a = Math.max(0, Math.min(1, alpha))
  const n = rgbOf(colour)
  return n ? `rgba(${n[0]}, ${n[1]}, ${n[2]}, ${a})` : `rgba(255, 0, 255, ${a})`
}

/** Whether the ground under the drawing is dark, measured, not assumed. */
export function isDark(ground: string): boolean {
  const n = rgbOf(ground)
  if (!n) return true
  return (n[0] * 0.299 + n[1] * 0.587 + n[2] * 0.114) / 255 < 0.5
}

/**
 * A colour for the i-th of some set of names, where there are more things to
 * tell apart than the theme has colours (one per Conversation, one per
 * relation). GOLDEN-ANGLE BY ORDER OF FIRST APPEARANCE: hashing names onto the
 * wheel put three of the commonest relations within eight degrees of each
 * other, while stepping by the golden angle keeps any few far apart -- and a
 * name that appears later takes the next step, so nothing already coloured
 * changes colour.
 */
export function orderHue(i: number, dark: boolean): string {
  const h = (i * 137.508 + 196) % 360
  return hsl(h, dark ? 58 : 50, dark ? 64 : 40)
}

/** Every distinct value, in the order it first appears. */
export function firstSeen(values: (string | null)[]): Map<string, number> {
  const m = new Map<string, number>()
  for (const v of values) if (v !== null && !m.has(v)) m.set(v, m.size)
  return m
}

function hsl(h: number, s: number, l: number): string {
  const sp = s / 100
  const lp = l / 100
  const c = (1 - Math.abs(2 * lp - 1)) * sp
  const hp = h / 60
  const x = c * (1 - Math.abs((hp % 2) - 1))
  const [r1, g1, b1] =
    hp < 1 ? [c, x, 0] : hp < 2 ? [x, c, 0] : hp < 3 ? [0, c, x] : hp < 4 ? [0, x, c] : hp < 5 ? [x, 0, c] : [c, 0, x]
  const m = lp - c / 2
  const hex = (v: number) => Math.round((v + m) * 255).toString(16).padStart(2, '0')
  return `#${hex(r1)}${hex(g1)}${hex(b1)}`
}
