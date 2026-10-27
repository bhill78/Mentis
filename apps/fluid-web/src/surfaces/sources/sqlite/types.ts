import type { Choice } from '../route'
export interface Column { name: string; type: string; pk: number; secret: boolean; hidden: number }
export interface Table {
  name: string; key: string; internal: boolean; virtual: boolean; rows: number | null; rows_state: string
  bytes: number | null; bytes_basis: string; columns: Column[]
  parents: { table: string; column: string; target: string | null }[]; children: string[]; key_candidates: string[][]
}
export interface Inspect {
  path: string; name_suggestion: string; size: number; modified: number; tables: Table[]
  totals: { tables: number; rows: number }; wal: { present: boolean; size: number }
  disk: { ok: boolean; message: string; needed_for_snapshot: number; room: number }
}
export type Op = 'equals' | 'not_equals' | 'contains' | 'starts_with' | 'after' | 'before' | 'is_empty' | 'not_empty'
export interface Rule { column: string; op: Op; value: string; kind: 'text' | 'integer' | 'real' }
export interface Config { omit: string[]; rows: Rule[]; decisions: Record<string, Choice> }
export type Cfg = Record<string, Config>
export const config = (cfg: Cfg, name: string): Config => cfg[name] ?? { omit: [], rows: [], decisions: {} }
export const complete = (r: Rule) => r.op === 'is_empty' || r.op === 'not_empty' || r.value !== ''
export interface Sample {
  columns: { name: string; type: string; typeof: string; key: boolean; secret: boolean; omitted: boolean }[]
  rows: (string | number | null)[][]; matching: number | null; total: number | null; matching_note?: string
  bytes_estimate: number | null; run: { sql: string; params: { n: number; value: [string, string] }[] }
}
export type Samples = Record<string, Sample>
export const isTaken = (c: Column, cfg: Config) => c.secret ? cfg.decisions[c.name] === 'include' : !cfg.omit.includes(c.name)
