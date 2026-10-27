import Bounded from './governance/Bounded'
import { useState } from 'react'
import { qs, useApi, type Id } from '../api'

/* ------------------------------------------------------------------------ *
 * What this durable object is connected to, from the existing closure read.
 *
 * THIS IS NOT THE CONVERSATION'S CAUSAL GRAPH. That one answers "what
 * happened because of this Turn" and its nodes are acts, executions and
 * Turns. This answers a different question about a different sort of thing:
 * "what does this piece of knowledge stand in relation to", and its nodes are
 * durable Entries. Provenance — the work that minted it — is NOT in here;
 * it is its own band in Details, because "made by that run" must never read
 * like "follows from that finding".
 *
 * IT HAS NO DEPTH LIMIT AND NO RELEVANCE SCORE. The server walks outward
 * until there is nothing unvisited left to walk to, so the extent is a fact
 * about the record rather than a number somebody picked. What this file does
 * with a large result is DISCLOSE IT PROGRESSIVELY — the immediate relations
 * first, the rest on request — which is a statement about attention, not
 * about relevance.
 *
 * Familiar relations have plain direction-aware presentation labels. Other
 * relations retain their declared meaning. Every recorded link remains in
 * technical detail; indirect connections never claim applicability.
 * ------------------------------------------------------------------------ */

interface Node {
  entry: Id
  kind: string | null
  family: string | null
  summary: string | null
  meaning: string | null
  distance: number
  unreadable?: boolean
}

interface Edge {
  link: Id
  from: Id
  other: Id
  relation: string
  inverse: string | null
  meaning: string | null
  direction: 'in' | 'out'
  reason: string | null
}

interface Closure {
  entry: Id
  focus: Node | null
  nodes: Record<string, Node>
  edges: Edge[]
  exhausted: boolean
  omitted: number
  reach: number
  why_not?: string
}

// Labels describe only the asserted direction; indirect links never claim applicability.
export function relationshipWords(relation: string, outward: boolean, meaning: string | null) {
  const words: Record<string, [string, string]> = {
    'scoped-to': ['Placed in', 'Material placed here'],
    'derived-from': ['Concluded from', 'A conclusion drawn from this'],
    'supports': ['Supports', 'Supported by'],
    'outcome-of': ['Outcome of', 'Recorded outcome'],
    'in-context': ['Recorded in the context of', 'Related material recorded in this context'],
    'supersedes': ['Replaces', 'Replaced by'],
    'proposes-to-supersede': ['Proposed to replace; nothing ended', 'Proposed replacement; nothing ended'],
    'disputes': ['Disagrees with; standing unchanged', 'Challenged by; standing unchanged'],
    'establishes': ['Confers standing on', 'Established by'],
    'answers': ['Answers', 'Answered by'],
  }
  return words[relation]?.[outward ? 0 : 1] ?? (meaning || 'Recorded connection; inspect its definition for meaning')
}

export default function KindWeb({ id, onOpenEntry }: { id: Id; onOpenEntry: (id: Id) => void }) {
  const [cap, setCap] = useState(60)
  const c = useApi<Closure>(`/api/neighborhood${qs({ entry: id, closure: 1, cap })}`)
  const d = c.data
  if (c.loading) return <p className="ei-faint">Reading relationships…</p>
  if (c.error) return <p className="ei-faint">Could not read: {c.error}</p>
  if (!d?.nodes) return <p className="ei-faint">{d?.why_not ?? 'No relationship read available.'}</p>
  const rows = Object.values(d.nodes).filter(n => n.entry !== id).sort((a,b) => a.distance - b.distance)
  const direct = rows.filter(n => n.distance === 1)
  const indirect = rows.filter(n => n.distance > 1)
  const render = (node: Node) => {
    const edges = [...new Map(d.edges.filter(e => e.other === node.entry || e.from === node.entry).map(e => [e.link,e])).values()]
    const directEdges = edges.filter(e => e.from === id || e.other === id)
    return <div className="web-node" key={node.entry}>
      {[...new Set(directEdges.map(e => relationshipWords(e.relation, e.from === id ? e.direction === 'out' : e.direction !== 'out', e.meaning)))].map(word => <p key={word}>{word}</p>)}
      <button className="web-other" onClick={() => onOpenEntry(node.entry)}><span className="web-other-body"><span className="web-other-term">{node.kind ?? 'Entry'}</span><span className="web-other-said">{node.summary ?? node.entry}</span></span></button>
      {[...new Set(directEdges.map(e => e.reason).filter(Boolean))].map(reason => <p className="web-why" key={reason}>{reason}</p>)}
      <details><summary>Technical details · {edges.length} links involving this record</summary><p className="ei-faint">Includes further connections from this record, not just its connection to the inspected material. Direction is relative to the traversal origin in “from”.</p><Bounded items={edges} label="Links">{e => <pre key={e.link}>{JSON.stringify({ ...e, asserted_from: e.direction === 'out' ? e.from : e.other, asserted_to: e.direction === 'out' ? e.other : e.from }, null, 2)}</pre>}</Bounded></details>
    </div>
  }
  return <div className="web">
    <Bounded items={direct} label="Directly related records">{render}</Bounded>
    {!rows.length && <p className="ei-faint">No related records returned.</p>}
    {!!indirect.length && <details><summary>{indirect.length} further connected records · indirect connections do not establish applicability</summary><Bounded items={indirect} label="Indirectly connected records">{render}</Bounded></details>}
    {!d.exhausted && <p className="ei-faint">At least {rows.length} related records. {d.omitted} connections were not explored by this bounded read; this is not the complete graph. <button className="ei-link" onClick={() => setCap(cap + 60)}>Read 60 more related records</button> Or open a related record to continue from it.</p>}
  </div>
}
