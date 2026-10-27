import type { Act, Id, Product } from '../api'

/* ------------------------------------------------------------------------ *
 * WHAT THE GRAPH IS FOR, AS A DERIVATION.
 *
 * Happening = glance · Graph = CAUSAL STRUCTURE · History = explanation.
 *
 * Graph's job is the SHAPE of the work: who was asked, who took it up, where
 * it branched, what came back, and what it produced. It is not the record in
 * rows — that is History, and it still holds every act.
 *
 * So acts are sorted into two kinds. STRUCTURAL acts get a mark and a place
 * in the shape. INTERIOR acts — the record reads, the measurements, the
 * routine steps inside one execution — are attached to the structural act
 * they happened under and drawn as a run of beads beside it. Nothing is
 * dropped; its RESOLUTION changes. Measured on the Solid Electrolytes case:
 * 29 acts, of which 11 belong to one execution and 7 of those are interior.
 * ------------------------------------------------------------------------ */

export type Role =
  /** a person asked for something — the origin of a piece of work */
  | 'steer'
  /** somebody took work up */
  | 'execution'
  /** work was handed outward: a branch */
  | 'branch'
  /** something came back to whoever was waiting */
  | 'return'
  /** the work produced, found, or ran into something */
  | 'result'
  /** the ordinary interior of an execution */
  | 'interior'

const ROLES: Record<string, Role> = {
  'expectation-recorded': 'steer',
  'execution-started': 'execution',
  'help-requested': 'branch',
  'clarification-requested': 'branch',
  'result-returned': 'return',
  'result-recovered': 'return',
  'expectation-met': 'return',
  'clarification-answered': 'return',
  'artifact-produced': 'result',
  'finding-recorded': 'result',
  'problem-noticed': 'result',
  'media-generated': 'result',
}

/** What a mark means in one word, for the label beside a result or a return.
 *  Executions and steers are named by their actor instead — who took it up is
 *  the fact worth reading at a glance. */
export const TERM: Record<string, string> = {
  'result-returned': 'returned',
  'result-recovered': 'recovered',
  'expectation-met': 'delivered',
  'clarification-answered': 'answered',
  'artifact-produced': 'produced',
  'finding-recorded': 'found',
  'problem-noticed': 'problem',
  'media-generated': 'generated',
  'help-requested': 'asked for help',
  'clarification-requested': 'asked',
  'expectation-recorded': 'asked for',
  'execution-started': 'took it up',
}

/** What an act made, from the `produced` Relation alone. An act whose only
 *  claim on a Kind is `about[]` REFERENCED it and made nothing. */
export const madeBy = (a: Act): Product[] => a.produced ?? []

/**
 * An act's place in the shape.
 *
 * Two different questions are answered here and they must not be confused.
 * The act's own recorded TYPE says what sort of move it was — asking, taking
 * work up, branching, returning — and reading that is reading the record, not
 * guessing. PRODUCTION is a separate question with a separate answer, and the
 * only admissible evidence for it is a `produced` link.
 *
 * So an act nobody has a role for, which nonetheless brought a durable Entry
 * into being, earns a place in the shape — that is how an act type invented
 * tomorrow becomes visible without this file being edited. And an act NAMED
 * like a result which produced nothing gets no product mark, however it reads.
 */
export const roleOf = (a: Act): Role =>
  ROLES[a.act] ?? (madeBy(a).length > 0 ? 'result' : 'interior')
export const isStructural = (a: Act) => roleOf(a) !== 'interior'

export interface Node {
  act: Act
  role: Role
  /** vertical order, oldest first */
  row: number
  /** lateral slot; 0 is the trunk. Branching only — never identity. */
  col: number
  /** the slot this one branched out of, so a return can be drawn closing
   *  back into it. Presentation only: it says where the work came from, not
   *  that any particular later act consumed what came back. */
  fromCol: number
  /** the structural act this one came out of, where the record says so */
  parent: Id | null
  /** interior acts that happened under this one, in order */
  inside: Act[]
  /** what this act itself brought into being */
  products: Product[]
  /** what its gathered interior acts produced, so a durable thing made by a
   *  routine step is not lost at the moment that step collapses into a bead */
  insideProducts: Product[]
}

/** Everything durable behind one structural node, its own and its interior's.
 *  This is what "3 things produced" counts, and it counts links. */
export const productsAt = (n: Node): Product[] => [...n.products, ...n.insideProducts]

export interface Shape {
  nodes: Node[]
  byId: Map<Id, Node>
  cols: number
  /** every act, structural or not, so nothing here loses the record */
  all: Act[]
}

/**
 * Build the shape.
 *
 * Lateral position expresses BRANCHING and nothing else. An execution that
 * was caused by a branch off another execution sits one slot outward; a slot
 * is released as soon as that execution's last act has passed, so the width
 * is bounded by how concurrently the work actually branched rather than by
 * how many participants exist.
 */
export function shapeOf(list: Act[]): Shape | null {
  const all = [...list].sort((a, b) => a.at - b.at)
  if (all.length === 0) return null

  const byActId = new Map(all.map((a) => [a.id, a]))
  const structural = all.filter(isStructural)
  if (structural.length === 0) return null

  /** Walk up `caused_by` until a structural act is reached. An interior act
   *  belongs to the structural act it happened under, however many ordinary
   *  steps lie between. */
  const anchorOf = (a: Act): Id | null => {
    let at: Act | undefined = a
    const seen = new Set<Id>()
    while (at?.caused_by && !seen.has(at.caused_by)) {
      seen.add(at.caused_by)
      const up: Act | undefined = byActId.get(at.caused_by)
      if (!up) return null
      if (isStructural(up)) return up.id
      at = up
    }
    return null
  }

  /* An interior act with no causal parent still belongs somewhere: the
     execution it was recorded under is the honest answer, and the record
     carries it. */
  const lastExecutionOf = new Map<Id, Id>()
  for (const a of structural) if (a.execution) lastExecutionOf.set(a.execution, a.id)

  const inside = new Map<Id, Act[]>()
  for (const a of all) {
    if (isStructural(a)) continue
    const anchor = anchorOf(a) ?? (a.execution ? (lastExecutionOf.get(a.execution) ?? null) : null)
    if (!anchor) continue
    inside.set(anchor, [...(inside.get(anchor) ?? []), a])
  }

  /* Lateral slots, assigned per execution and released when it ends. */
  const endOf = new Map<Id, number>()
  structural.forEach((a, i) => {
    if (a.execution) endOf.set(a.execution, i)
  })

  const slotOf = new Map<Id, number>()
  const cameFrom = new Map<Id, number>()
  const busy: (Id | null)[] = []
  const colOf = (a: Act, i: number): number => {
    if (!a.execution) return 0
    const held = slotOf.get(a.execution)
    if (held !== undefined) return held
    /* A branch goes outward from whatever it branched off; the first
       execution in the record holds the trunk. */
    const cause = a.caused_by ? byActId.get(a.caused_by) : undefined
    const from = cause?.execution ? (slotOf.get(cause.execution) ?? 0) : -1
    let slot = from + 1
    while (busy[slot] != null && endOf.get(busy[slot] as Id)! >= i) slot += 1
    busy[slot] = a.execution
    slotOf.set(a.execution, slot)
    cameFrom.set(a.execution, Math.max(0, from))
    return slot
  }

  const nodes: Node[] = structural.map((act, row) => {
    const col = colOf(act, row)
    return {
    act,
    role: roleOf(act),
    row,
    col,
    fromCol: act.execution ? (cameFrom.get(act.execution) ?? 0) : 0,
    parent: (() => {
      const p = act.caused_by ? byActId.get(act.caused_by) : undefined
      if (!p) return null
      return isStructural(p) ? p.id : anchorOf(p)
    })(),
    inside: inside.get(act.id) ?? [],
    products: madeBy(act),
    insideProducts: (inside.get(act.id) ?? []).flatMap(madeBy),
    }
  })

  const byId = new Map(nodes.map((n) => [n.act.id, n]))
  return { nodes, byId, cols: Math.max(1, ...nodes.map((n) => n.col + 1)), all }
}

/** Which structural node an act belongs to — used to keep Graph, History and
 *  the Happening spine pointing at the same thing when a selection arrives
 *  from somewhere else. */
export function holderOf(shape: Shape, id: Id | null): Node | null {
  if (!id) return null
  const direct = shape.byId.get(id)
  if (direct) return direct
  return shape.nodes.find((n) => n.inside.some((a) => a.id === id)) ?? null
}
