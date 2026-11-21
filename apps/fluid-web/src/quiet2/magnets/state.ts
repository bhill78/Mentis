/* One resource's feature state. Ownership and expiry belong exclusively to
 * quiet2/space/registry; there is deliberately no registry in this module. */
import type { RouteAnswer, RouteResult, RouteSource } from '../../fluid/surface/magnet/route'
import type { MagnetGet, MagnetResource, MagnetSnapshot, SavedMagnet } from './contract'
import { unsupportedMagnet } from './read'

const stopped = () => new DOMException('The Magnet read was abandoned.', 'AbortError')
const validStatus = (v: unknown) => ['ok', 'partial', 'busy', 'unavailable'].includes(String(v))
const reasonOf = (body: unknown) => body && typeof body === 'object' && typeof (body as { error?: unknown }).error === 'string' ? (body as { error: string }).error : undefined

export function createMagnetResource(at: { id: string; brainKey: string; saved: SavedMagnet; get: MagnetGet }): MagnetResource {
  if (!at.brainKey.trim()) throw new Error('Which Brain this page serves is unknown. No Magnet was opened.')
  const issue = at.saved.reason ?? unsupportedMagnet(at.saved.config, at.saved.id)
  if (issue || !at.saved.config) throw new Error(issue ?? 'The saved definition is unavailable.')
  const config = at.saved.config
  const source = config.sources[0] as { kind: 'conversation'; conversation: string }
  const key = `conversation:${source.conversation}`
  const selected = config.selection.informationTypes?.length ? config.selection.informationTypes : ['post', 'file', 'image']
  let current: MagnetSnapshot = { title: at.saved.name, loading: false, results: [], x: 32, y: 80, tab: 'Overview', pinned: false, expanded: false }
  const heard = new Set<() => void>()
  let disposed = false, generation = 0
  let control: AbortController | null = null
  let pending: Promise<void> | null = null
  const emit = (change: Partial<MagnetSnapshot>) => {
    if (disposed) return
    current = { ...current, ...change }
    heard.forEach((fn) => fn())
  }
  const cancel = () => {
    generation++
    control?.abort(); control = null; pending = null
    emit({ loading: false })
  }
  const readAnswer = async (query: URLSearchParams, mine: number, signal: AbortSignal): Promise<RouteSource> => {
    const got = await at.get(`/fluid/api/magnets/${encodeURIComponent(at.saved.id)}/read?${query}`, signal)
    if (disposed || generation !== mine || signal.aborted) throw stopped()
    if (got.status === 503) return { key, status: 'busy', reason: reasonOf(got.body) ?? 'The server has no room for this read just now.' }
    if (got.status !== 200) throw new Error(`The Magnet read is unavailable (${got.status}). Nothing was substituted.`)
    const answer = got.body as RouteAnswer | null
    if (!answer || typeof answer !== 'object' || answer.magnet !== at.saved.id || !Array.isArray(answer.sources)) throw new Error('The Magnet read did not match this saved Magnet.')
    if (answer.unavailable) return { key, status: 'unavailable', reason: answer.unavailable }
    const found = answer.sources.find((s) => s.key === key)
    if (!found || !validStatus(found.status)) throw new Error('The server did not answer for this source conversation.')
    if (found.summary != null) {
      if (typeof found.summary !== 'object' || Array.isArray(found.summary)) throw new Error('The source summary could not be read.')
      const s = found.summary
      if ((s.title != null && typeof s.title !== 'string') || (s.posts != null && (!Number.isFinite(s.posts) || s.posts < 0)) || (s.activity != null && !Number.isFinite(s.activity)))
        throw new Error('The source summary contained malformed title, tally or activity information.')
    }
    return found
  }
  const read = (more = false): Promise<void> => {
    if (disposed) return Promise.resolve()
    if (pending) return pending
    if (more && !current.next) return Promise.resolve()
    const mine = ++generation
    const abort = new AbortController(); control = abort
    const cursor = more ? current.next : undefined
    emit({ loading: true, error: undefined })
    const run = async () => {
      try {
        if (!more) {
          const summary = await readAnswer(new URLSearchParams({ mode: 'summary' }), mine, abort.signal)
          if (summary.status === 'busy' || summary.status === 'unavailable') { emit({ summary, status: summary.status, reason: summary.reason ?? undefined }); return }
          emit({ summary, title: summary.summary?.title || at.saved.name })
        }
        const q = new URLSearchParams({ mode: 'page', source: key, types: selected.join(',') })
        if (cursor) q.set('cursor', cursor)
        const page = await readAnswer(q, mine, abort.signal)
        if (page.status === 'busy' || page.status === 'unavailable') { emit({ status: page.status, reason: page.reason ?? undefined }); return }
        if (!Array.isArray(page.results)) throw new Error('The source page did not provide readable results.')
        for (const item of page.results) {
          if (!item || typeof item.id !== 'string' || !item.id || !['post', 'file', 'image', 'attachment'].includes(item.kind) || !selected.includes(item.kind as never)) throw new Error('The source page returned an unexpected information type.')
          if (item.conversation != null && item.conversation !== source.conversation) throw new Error('The source page returned an item from another conversation.')
        }
        if (page.next && typeof page.next !== 'string') throw new Error('The source cursor could not be read.')
        if (cursor && page.next === cursor) throw new Error('The source returned the same cursor. Reading stopped without substituting a broader page.')
        const results = new Map<string, RouteResult>()
        if (more) current.results.forEach((r) => results.set(`${r.kind}:${r.id}`, r))
        page.results.forEach((r) => results.set(`${r.kind}:${r.id}`, r))
        emit({ results: [...results.values()], next: page.next ?? undefined, status: page.status, reason: page.reason ?? undefined,
          ...(!more ? { previousOpen: current.openedAt, openedAt: Date.now() } : {}) })
      } catch (e) {
        if (disposed || generation !== mine || abort.signal.aborted) return
        emit({ error: e instanceof Error ? e.message : 'The Magnet could not be read.' })
      } finally {
        if (!disposed && generation === mine) { control = null; pending = null; emit({ loading: false }) }
      }
    }
    pending = run()
    return pending
  }
  return {
    id: at.id, brainKey: at.brainKey, saved: at.saved,
    snapshot: () => current,
    subscribe: (fn) => { if (!disposed) heard.add(fn); return () => { heard.delete(fn) } },
    update: emit, read, cancel,
    dispose() {
      if (disposed) return
      disposed = true; generation++; control?.abort(); control = null; pending = null
      current = { ...current, results: [], summary: undefined, next: undefined, loading: false }
      heard.forEach((fn) => fn()); heard.clear()
    },
  }
}
