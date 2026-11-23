import { page } from '../../brainBinding'
import type { MagnetSnapshot } from './contract'

// Device working state only. Retained content and messages belong to the Brain.
export function workingKey(brainKey: string): string | null {
  const bound = page.bound()
  return bound && !page.moved() && bound.split('@')[0] === brainKey.split('|').at(-1)
    ? `mentis.magnet.working.v1:${brainKey}:${bound}` : null
}
const tabs = ['Overview', 'Posts', 'Files', 'Perspectives', 'Conversation']
const positions = (v: unknown): Partial<Record<import('./contract').MagnetTab | 'Compact', number>> | undefined => {
  if (!v || typeof v !== 'object' || Array.isArray(v)) return undefined
  return Object.fromEntries(Object.entries(v).filter(([k, n]) => [...tabs, 'Compact'].includes(k) && typeof n === 'number' && Number.isFinite(n) && n >= 0))
}
export function loadWorking(brainKey: string, id: string): Partial<MagnetSnapshot> {
  try {
    const key = workingKey(brainKey)
    if (!key) return {}
    const v = JSON.parse(localStorage.getItem(`${key}:${id}`) ?? '{}')
    return {
      ...(Number.isFinite(v.x) && Number.isFinite(v.y) ? { x: v.x, y: v.y } : {}),
      ...(tabs.includes(v.tab) ? { tab: v.tab } : {}),
      ...(typeof v.expanded === 'boolean' ? { expanded: v.expanded } : {}),
      ...(typeof v.pinned === 'boolean' ? { pinned: v.pinned } : {}),
      ...(typeof v.inspection === 'string' && v.inspection.length < 300 ? { inspection: v.inspection } : {}),
      ...(typeof v.query === 'string' && v.query.length < 1000 ? { query: v.query } : {}),
      ...(typeof v.agentId === 'string' && /^ent-[a-zA-Z0-9]{6,40}$/.test(v.agentId) ? { agentId: v.agentId } : {}),
      ...(['ordinary', 'retained'].includes(v.assistanceMode) ? { assistanceMode: v.assistanceMode } : {}),
      ...(v.batchSelection && /^adm-[a-zA-Z0-9]{6,40}$/.test(v.batchSelection.ref) && /^[0-9a-f]{64}$/.test(v.batchSelection.digest)
        ? { batchSelection: { ref: v.batchSelection.ref, digest: v.batchSelection.digest } } : {}),
      ...(Number.isFinite(v.scroll) && v.scroll >= 0 ? { scroll: v.scroll } : {}),
      ...(Number.isFinite(v.inspectionScroll) && v.inspectionScroll >= 0 ? { inspectionScroll: v.inspectionScroll } : {}),
      ...(positions(v.scrolls) ? { scrolls: positions(v.scrolls) } : {}),
      ...(v.inspectionReturn && tabs.includes(v.inspectionReturn.tab) && typeof v.inspectionReturn.expanded === 'boolean'
        ? { inspectionReturn: { tab: v.inspectionReturn.tab, expanded: v.inspectionReturn.expanded } } : {}),
    }
  } catch { return {} }
}
export function saveWorking(brainKey: string, id: string, s: MagnetSnapshot) {
  try {
    const key = workingKey(brainKey)
    if (key) localStorage.setItem(`${key}:${id}`, JSON.stringify({ x: s.x, y: s.y, tab: s.tab, expanded: s.expanded, pinned: s.pinned, inspection: s.inspection, inspectionReturn: s.inspectionReturn, query: s.query, scroll: s.scroll, scrolls: s.scrolls, inspectionScroll: s.inspectionScroll, agentId: s.agentId, assistanceMode: s.assistanceMode, batchSelection: s.batchSelection }))
  } catch { /* The Brain still retains collection and Conversation if storage is unavailable. */ }
}
export function openedMagnets(brainKey: string): string[] {
  try {
    const key = workingKey(brainKey), rows = key && JSON.parse(localStorage.getItem(`${key}:open`) ?? '[]')
    return Array.isArray(rows) ? rows.filter((id): id is string => typeof id === 'string' && /^mag-[a-zA-Z0-9_-]{1,60}$/.test(id)).slice(0, 20) : []
  } catch { return [] }
}
export function saveOpenedMagnets(brainKey: string, ids: string[]) {
  try { const key = workingKey(brainKey); if (key) localStorage.setItem(`${key}:open`, JSON.stringify(ids.slice(0, 20))) } catch { /* Device storage can be disabled. */ }
}
