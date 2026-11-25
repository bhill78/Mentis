import type { RouteResult } from '../../fluid/surface/magnet/route'

const entry = (v: unknown) => typeof v === 'string' && /^ent-[a-zA-Z0-9]{6,40}$/.test(v)
const admission = (v: unknown) => typeof v === 'string' && /^adm-[a-zA-Z0-9]{6,40}$/.test(v)
const integer = (v: unknown) => typeof v === 'number' && Number.isSafeInteger(v) && v >= 0
const statuses = ['ok', 'partial', 'busy', 'unavailable']
/** The server has verified the whole immutable batch. Inspect its captured
 * sources, which may predate the current configuration; never substitute it. */
export function collectionRows(page: any): { results: RouteResult[]; status: string; reason?: string; posts: number; sources: any[] } {
  if (!page || !Array.isArray(page.sources) || !page.sources.length || page.sources.length > 20) throw new Error('The list of sources in this collection is invalid.')
  const results: RouteResult[] = [], keys = new Set<string>(), reasons: string[] = []
  let complete = true
  for (const one of page.sources) {
    const source = one?.source
    if (!source || !statuses.includes(one.status) || !Array.isArray(one.results)) throw new Error('A source in this collection lacks its recorded status.')
    const key = source.kind === 'conversation' && entry(source.conversation) ? `conversation:${source.conversation}`
      : source.kind === 'file' && typeof source.collection === 'string' ? `file:${source.collection}:${source.path ?? ''}` : null
    if (!key || one.key !== key || keys.has(key)) throw new Error('A captured source has inconsistent identity.')
    keys.add(key)
    if (one.status !== 'ok') complete = false
    if (typeof one.reason === 'string' && one.reason) reasons.push(one.reason)
    if (['busy', 'unavailable'].includes(one.status) && one.results.length) throw new Error('An unavailable source cannot claim collected results.')
    for (const r of one.results) {
      if (!r || typeof r.id !== 'string' || !r.id || !['post', 'file', 'image', 'attachment'].includes(r.kind)) throw new Error('A collected item lacks usable identity.')
      if (source.kind === 'conversation') {
        if (!entry(r.conversation) || !entry(r.version)) throw new Error('A collected Conversation item does not say where it came from.')
        if (r.via === 'home' && r.conversation !== source.conversation) throw new Error('A collected home post says it came from somewhere it did not.')
      } else {
        const v = r.value
        if (r.kind !== 'file' || r.via !== 'held-source' || !admission(r.id) || r.version !== r.id || r.conversation !== null || r.author !== null
          || !v || v.ref !== r.id || v.collection !== source.collection || v.path !== source.path || typeof v.text !== 'string'
          || typeof v.digest !== 'string' || !/^[0-9a-f]{64}$/.test(v.digest) || v.offset !== 0
          || !integer(v.end) || v.end > 65536 || !integer(v.size) || v.end > v.size || new TextEncoder().encode(v.text).length !== v.end
          || v.shortened !== (v.end < v.size) || v.omitted_bytes !== v.size - v.end || v.next_offset !== (v.shortened ? v.end : null)
          || typeof v.acquired_at !== 'number' || !Number.isFinite(v.acquired_at) || r.at !== v.acquired_at
          || v.citation !== `${v.ref}@${v.digest.slice(0, 12)}[0:${v.end}]`) throw new Error('A held-file range or its immutable provenance is invalid.')
      }
      results.push({ ...r, capturedSourceKey: one.key } as RouteResult)
    }
  }
  const status = complete ? 'ok' : results.length ? 'partial' : page.sources.every((s: any) => s.status === 'busy') ? 'busy' : 'unavailable'
  return { results, status, ...(reasons.length ? { reason: reasons.join(' ') } : {}), posts: results.filter((r) => r.kind === 'post').length, sources: page.sources }
}
