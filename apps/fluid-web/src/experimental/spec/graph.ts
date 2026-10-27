/* EXPERIMENTAL: the shared node/edge grammar and the reading half of diagram and whiteboard (drawn in ../types/graph.tsx). */
import type { Ctx, TypeSpec } from './api'
import { listOf, pairsOf, quoted } from '../util'

export const KINDS = ['start', 'step', 'decision', 'end', 'note', 'commit'] as const

export type Kind = (typeof KINDS)[number]

export interface GNode { id: string; label: string; kind: Kind; detail?: string; group?: string; date?: string; author?: string; tag?: string; n: number }

export interface GEdge { key: string; from: string; to: string; label?: string; n: number }

export interface Graph { nodes: GNode[]; edges: GEdge[]; groups: string[]; byId: Record<string, GNode> }

const ID = /^[A-Za-z0-9_][A-Za-z0-9_.-]*$/

const NODE = /^([A-Za-z0-9_][A-Za-z0-9_.-]*)\s*:(.*)$/

export const GRAMMAR =
  'one per line: `id: "Label" kind=… group=… detail="…"` for a node; `a -> b "label"` for an edge (label optional); `# …` is a comment'

/** Read node and edge lines. Used by both diagram and whiteboard. */
export function parseGraph(body: string, a: Record<string, string>, c: Ctx, what: string): Graph {
  const nodes: GNode[] = [], byId: Record<string, GNode> = {}
  const raw: { from: string; to: string; label?: string; n: number }[] = []
  body.split('\n').forEach((text, i) => {
    const n = i + 1, line = text.trim(), where = `line ${n}`
    if (!line || line.startsWith('#')) return
    const nm = NODE.exec(line)
    if (nm) {
      const id = nm[1]
      let rest = nm[2], label = id
      const qd = quoted(rest)
      if (qd) [label, rest] = qd
      /* Quotes are optional when nothing follows the label. */
      else if (rest.trim() && !/[="]/.test(rest)) { label = rest.trim(); rest = '' }
      const { pairs, flags, residue } = pairsOf(rest)
      if (residue) c.err(where, `I can't read “${residue}”. After the label write key=value, or key="text with spaces".`)
      for (const f of flags) c.err(where, `“${f}” is on its own. Settings look like kind=decision; a label with spaces goes first, in double quotes.`)
      const node: GNode = { id, label, kind: 'step', n }
      for (const [k, v] of Object.entries(pairs)) {
        if (k === 'kind') {
          if ((KINDS as readonly string[]).includes(v)) node.kind = v as Kind
          else c.err(where, `kind must be one of: ${KINDS.join(', ')} — not “${v}”.`)
        } else if (k === 'detail') node.detail = v
        else if (k === 'group') node.group = v
        else if (k === 'date') node.date = v
        else if (k === 'author') node.author = v
        else if (k === 'tag') node.tag = v
        else c.err(where, `“${k}” is not a node setting. A node may say kind=…, group=…, detail="…", date=…, author="…" or tag=….`)
      }
      if (byId[id]) c.err(where, `The id “${id}” is already used on line ${byId[id].n}. Every node needs its own id.`)
      else { byId[id] = node; nodes.push(node) }
      return
    }
    if (/-+>/.test(line)) {
      // Arrows are looked for only before the label, so a label may contain "->".
      const cut = line.indexOf('"') < 0 ? line.length : line.indexOf('"')
      const parts = line.slice(0, cut).trim().split(/\s*-+>\s*/)
      const last = /^(\S*)\s*(.*)$/.exec(parts[parts.length - 1])!
      parts[parts.length - 1] = last[1]
      if (parts.length < 2) { c.err(where, `“${line}” is neither a node (id: "Label") nor an edge (a -> b).`); return }
      const tail = (last[2] + line.slice(cut)).trim()
      let label: string | undefined
      if (tail) {
        const qd = quoted(tail)
        if (qd && !qd[1].trim()) label = qd[0]
        else { c.err(where, `After “${last[1]}” I expected nothing, or a label in double quotes, e.g. ${parts[0]} -> ${last[1]} "yes".`); return }
      }
      const bad = parts.filter((p) => !ID.test(p))
      if (bad.length) { c.err(where, `“${bad[0] || '(nothing)'}” is not a node id. Ids are letters, digits, _ . or - with no spaces, e.g. a -> b.`); return }
      if (label !== undefined && parts.length > 2) { c.err(where, 'A label can only go on a single edge (a -> b "label"), not on a chain a -> b -> c.'); return }
      for (let k = 0; k + 1 < parts.length; k++) raw.push({ from: parts[k], to: parts[k + 1], label, n })
      return
    }
    c.err(where, `“${line}” is neither a node (id: "Label") nor an edge (a -> b).`)
  })
  const edges: GEdge[] = [], seen: Record<string, number> = {}
  const known = nodes.length <= 14 ? ` The ids are: ${nodes.map((x) => x.id).join(', ')}.` : ''
  for (const e of raw) {
    const missing = [e.from, e.to].filter((id) => !byId[id])
    if (missing.length) {
      c.err(`line ${e.n}`, `The edge names “${missing[0]}”, but no node has that id. Declare it (${missing[0]}: "Label") or check the spelling.${known}`)
      continue
    }
    const base = `${e.from}->${e.to}`
    seen[base] = (seen[base] ?? 0) + 1
    if (seen[base] === 2) c.warn(`line ${e.n}`, `${base} is declared more than once; each is drawn.`)
    edges.push({ key: seen[base] > 1 ? `${base}#${seen[base]}` : base, from: e.from, to: e.to, label: e.label, n: e.n })
  }
  const declared = listOf(a.groups)
  const groups = [...declared]
  for (const nd of nodes)
    if (nd.group !== undefined && !groups.includes(nd.group)) {
      if (declared.length) c.warn(`line ${nd.n}`, `group “${nd.group}” is not in groups=…, so it goes after the declared ones.`)
      groups.push(nd.group)
    }
  if (!nodes.length && what === 'diagram') c.err('body', 'A diagram needs at least one node, e.g. a: "Start" kind=start.')
  return { nodes, edges, groups, byId }
}

export const diagramSpec: TypeSpec<Graph> = {
  type: 'diagram',
  summary: 'A flow of boxes and arrows, laid out automatically from declared nodes and edges. Select, follow paths, leave notes.',
  attrs: {
    title: { req: 'optional', says: 'a heading' },
    direction: { req: 'optional', choices: ['down', 'right'], says: 'which way the flow reads: down (default) or right' },
    groups: { req: 'optional', says: 'comma list: the order of the groups (drawn as lanes)' },
    view: { req: 'optional', choices: ['flow', 'git'], says: 'flow (default) or git: draws a commit history graph with branch tracks and parent links' },
  },
  body: GRAMMAR + '; kind is start, step (default), decision, end or note',
  parse: (body, a, c) => {
    const g = parseGraph(body, a, c, 'diagram')
    if (a.view === 'git') {
      const active = new Set<string>(), done = new Set<string>()
      const visit = (id: string): boolean => {
        if (active.has(id)) return true
        if (done.has(id)) return false
        active.add(id)
        if (g.edges.filter((e) => e.from === id).some((e) => visit(e.to))) return true
        active.delete(id); done.add(id); return false
      }
      if (g.nodes.some((n) => visit(n.id))) c.err('body', 'Git history cannot contain a cycle.')
    }
    return g
  },
}

export const whiteboardSpec: TypeSpec<Graph> = {
  type: 'whiteboard',
  summary: 'A board of cards a person rearranges: seeded from declared cards, zones and links; moves, edits and additions are state.',
  attrs: {
    title: { req: 'optional', says: 'a heading' },
    groups: { req: 'optional', says: 'comma list: the zones, left to right (empty ones too), e.g. "Now,Next,Later"' },
    direction: { req: 'optional', choices: ['down', 'right'], says: 'only when there are no groups: seed cards along the flow, down (default) or right' },
  },
  body: GRAMMAR + '; group= puts a card in a zone; kind is optional (start, step, decision, end, note)',
  parse: (body, a, c) => parseGraph(body, a, c, 'whiteboard'),
}
