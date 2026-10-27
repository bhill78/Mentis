import { complete, type Config, type Op, type Rule, type Sample, type Table } from './types'
export const labels: Record<Op, string> = { equals: 'is', not_equals: 'is not', contains: 'contains', starts_with: 'starts with', after: 'after', before: 'before', is_empty: 'is empty', not_empty: 'is not empty' }
export function realNumber(raw: string) {
  const m=/^([+-]?)0x([0-9a-f]+)(?:\.([0-9a-f]+))?p([+-]?\d+)$/i.exec(raw)
  return m ? (m[1]==='-'?-1:1)*(parseInt(m[2],16)+[...(m[3]??'')].reduce((n,c,i)=>n+parseInt(c,16)/16**(i+1),0))*2**Number(m[4]) : Number(raw)
}
export function kindOf(sample: Sample | undefined, column: string) {
  const c = sample?.columns.find(c => c.name === column)
  if (c?.typeof === 'integer' || c?.typeof === 'real' || c?.typeof === 'blob') return c.typeof
  const index = sample?.columns.findIndex(c => c.name === column) ?? -1
  const values = sample?.rows.map(r => r[index]).filter(v => v != null && v !== '') ?? []
  return values.length && values.every(v => typeof v === 'string' && /^\d{4}-\d\d-\d\d(?:[ T]|$)/.test(v)) ? 'date' : 'text'
}
export function operators(kind: string): [Op, string][] {
  if (kind === 'date') return [['after','after'],['before','before'],['is_empty','is empty'],['not_empty','is not empty']]
  if (kind === 'integer' || kind === 'real') return [['equals','='],['not_equals','≠'],['after','more than'],['before','less than'],['is_empty','is empty']]
  return (['equals','not_equals','contains','starts_with','is_empty','not_empty'] as Op[]).map(op => [op, labels[op]])
}
export const eligible = (table: Table, cfg: Config, sample?: Sample) => table.columns.filter(c => !c.secret && !cfg.omit.includes(c.name) && kindOf(sample,c.name) !== 'blob' && !/BLOB/i.test(c.type))
export function newRule(table: Table, cfg: Config, sample?: Sample): Rule | null {
  const cols = eligible(table,cfg,sample)
  const c = cols.find(c => !c.pk && !table.parents.some(p=>p.column===c.name) && kindOf(sample,c.name)==='text') ?? cols[0]
  if (!c) return null
  const k = kindOf(sample,c.name)
  return { column: c.name, op: operators(k)[0][0], value: '', kind: k==='integer' || k==='real' ? k : 'text' }
}
export const wireRules = (cfg: Config) => ({ omit: cfg.omit, rows: cfg.rows.filter(complete).map(r => ({ column:r.column, op:r.op,
  ...(r.op==='is_empty'||r.op==='not_empty' ? {} : { value:[r.kind, r.value] }) })) })
export function sentence(r: Rule) {
  const label = r.op==='after' && r.kind!=='text' ? 'more than' : r.op==='before' && r.kind!=='text' ? 'less than' : labels[r.op]
  return `${r.column} ${label}${r.op==='is_empty'||r.op==='not_empty' ? '' : ` “${r.value}”`}`
}
