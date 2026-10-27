export type Recent = { path: string; kind: 'file' | 'folder'; purpose: 'database' | 'folder'; size?: number; used_at: number }
const key = 'mentis.sources.recent'
export function readRecent(): Recent[] {
  try { return JSON.parse(localStorage.getItem(key) ?? '[]').filter((x: Recent) => typeof x.path === 'string' && Number.isFinite(x.used_at)) } catch { return [] }
}
export function remember(item: Omit<Recent, 'used_at'>) {
  const previous=readRecent().find(x=>x.path===item.path&&x.purpose===item.purpose)
  const all = [{ ...previous, ...item, used_at: Date.now() }, ...readRecent().filter(x => x.path !== item.path || x.purpose !== item.purpose)]
  const kept = all.filter((x, i) => all.slice(0, i).filter(y => y.purpose === x.purpose).length < 8)
  try { localStorage.setItem(key, JSON.stringify(kept)) } catch { /* optional browser history */ }
  return kept
}
export function forget(item: Recent) {
  const all = readRecent().filter(x => x.path !== item.path || x.purpose !== item.purpose)
  try { localStorage.setItem(key, JSON.stringify(all)) } catch { /* optional */ }
  return all
}
export function cleanPath(value: string) {
  const s = value.trim(), quoted = s.startsWith('"') && s.endsWith('"')
  return { path: quoted ? s.slice(1, -1) : s, quoted }
}
export const baseName = (p: string) => p.replace(/[\\/]+$/, '').split(/[\\/]/).pop() ?? p
export const suggestedName = (p: string) => baseName(p).replace(/^\./, '').replace(/\.(db|sqlite3?|db3)$/i, '')
