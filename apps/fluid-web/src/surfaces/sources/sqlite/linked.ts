import { complete, config, type Cfg, type Table } from './types'
export const parentsOf = (tables: Table[], name: string) => [...new Set(tables.find(t => t.name === name)?.parents.map(p => p.table) ?? [])].filter(p => tables.some(t => t.name === p))
export const childrenOf = (tables: Table[], name: string) => tables.filter(t => parentsOf(tables, t.name).includes(name)).map(t => t.name)
export function closure(tables: Table[], starts: Iterable<string>, blocked: Iterable<string> = []) {
  const deny = new Set(blocked), paths: Record<string, string[]> = {}, queue = [...starts].map(n => [n])
  while (queue.length) {
    const path = queue.shift()!, name = path[path.length - 1]
    if (deny.has(name) || paths[name] || !tables.some(t => t.name === name)) continue
    paths[name] = path
    parentsOf(tables, name).forEach(p => queue.push([...path, p]))
  }
  return paths
}
export const selected = (tables: Table[], chosen: string[], dismissed: string[]) => Object.keys(closure(tables, chosen, dismissed))
export const suggested = (tables: Table[], chosen: string[], dismissed: string[]) => selected(tables, chosen, dismissed).filter(n => !chosen.includes(n))
export const alsoDropped = (tables: Table[], chosen: string[], dismissed: string[], x: string) => {
  const now = new Set(selected(tables, chosen, dismissed))
  return selected(tables, chosen, dismissed.filter(n => n !== x)).filter(n => n !== x && !now.has(n))
}
export interface Dangling { child: string; parent: string; column: string; kind: 'filtered' | 'untaken' | 'omitted' }
export function danglingLinks(tables: Table[], sel: string[], cfg: Cfg): Dangling[] {
  const out: Dangling[] = []
  tables.filter(t => sel.includes(t.name)).forEach(t => t.parents.forEach(p => {
    if (config(cfg, t.name).omit.includes(p.column)) out.push({ child: t.name, parent: p.table, column: p.column, kind: 'omitted' })
    else if (!sel.includes(p.table)) out.push({ child: t.name, parent: p.table, column: p.column, kind: 'untaken' })
    else if (config(cfg, p.table).rows.some(complete)) out.push({ child: t.name, parent: p.table, column: p.column, kind: 'filtered' })
  }))
  return out.filter((x, i) => out.findIndex(y => JSON.stringify(y) === JSON.stringify(x)) === i)
}
