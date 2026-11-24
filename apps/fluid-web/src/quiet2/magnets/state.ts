/* Retained collection only. Opening never activates or substitutes a live source read. */
import { CLIENT_HEADERS } from '../../api'
import { BRAIN_HEADER, brainNow, page, refusedAsOtherBrain } from '../../brainBinding'
import { fluidFetch } from '../../fluid/http'
import type { MagnetGet, MagnetResource, MagnetSnapshot, SavedMagnet } from './contract'
import { unsupportedMagnet } from './read'
import { loadWorking, saveWorking, workingKey } from './workingState'
import { clearInspections, emptyPlaces } from './places'
import { collectionRows } from './collectionRows'
import { NO_SOURCE_TO_COLLECT } from './configuration'

const obj = (v: unknown): Record<string, any> | null => v && typeof v === 'object' && !Array.isArray(v) ? v as Record<string, any> : null
const entry = (v: unknown): v is string => typeof v === 'string' && /^ent-[a-zA-Z0-9]{6,40}$/.test(v)
export function createMagnetResource(at: { id: string; brainKey: string; saved: SavedMagnet; get: MagnetGet }): MagnetResource {
  if (!at.brainKey.trim()) throw new Error('Which Brain this page serves is unknown. No Magnet was opened.')
  const issue = at.saved.reason ?? unsupportedMagnet(at.saved.config, at.saved.id)
  if (issue || !at.saved.config) throw new Error(issue ?? 'The saved definition is unavailable.')
  let current: MagnetSnapshot = { title: at.saved.name, loading: false, results: [], x: 32, y: 80,
    open: false, wide: false, tab: 'Summary', overlay: null, places: emptyPlaces(),
    query: '', searchType: 'All', searchTarget: null, searchListScroll: 0, lens: null,
    returnRoute: null, settingsReturn: null, context: null, contextSuppressed: false, carried: null,
    ...loadWorking(at.brainKey, at.saved.id) }
  const heard = new Set<() => void>()
  let disposed = false, generation = 0, control: AbortController | null = null, pending: Promise<void> | null = null
  const emit = (change: Partial<MagnetSnapshot>) => {
    if (disposed) return
    current = { ...current, ...change }; saveWorking(at.brainKey, at.saved.id, current)
    heard.forEach((fn) => fn())
  }
  const read = (): Promise<void> => {
    if (disposed) return Promise.resolve()
    if (pending) return pending
    const mine = ++generation, abort = new AbortController(); control = abort
    emit({ loading: true, error: undefined })
    pending = (async () => {
      try {
        const selection = current.batchSelection
        const query = selection ? '?' + new URLSearchParams({ batch: selection.ref, digest: selection.digest }) : ''
        const got = await at.get(`/fluid/api/magnets/${encodeURIComponent(at.saved.id)}/collection${query}`, abort.signal)
        if (disposed || generation !== mine || abort.signal.aborted) return
        const answer = obj(got.body)
        if (got.status !== 200 || !answer || answer.error) throw new Error(answer?.error ?? `Retained collection unavailable (${got.status}).`)
        if (answer.magnet !== at.saved.id || unsupportedMagnet(answer.config, at.saved.id)) throw new Error('The retained collection did not match this Magnet definition.')
        if (answer.activation == null) {
          if (answer.page != null) throw new Error('A collection page without retained provenance was refused.')
          at.saved.config = answer.config
          emit({ activation: null, results: [], status: undefined, summary: undefined }); return
        }
        const decoded = collectionRows(answer.page)
        if (!entry(answer.activation.post) || !/^adm-[a-zA-Z0-9]{6,40}$/.test(answer.activation.artifact?.ref ?? '')) throw new Error('The retained collection lacks its recorded Admission.')
        if (selection && (answer.activation.artifact.ref !== selection.ref || answer.activation.artifact.digest !== selection.digest)) throw new Error('The historical read did not return the selected immutable batch. Nothing was substituted.')
        at.saved.config = answer.config
        emit({ activation: answer.activation, results: decoded.results, status: decoded.status, reason: decoded.reason, next: undefined,
          summary: { key: 'retained-sources', status: decoded.status as 'ok' | 'partial' | 'busy' | 'unavailable', summary: { posts: decoded.posts } } })
      } catch (e) {
        if (!disposed && generation === mine && !abort.signal.aborted) emit({ error: e instanceof Error ? e.message : 'The retained collection could not be read.' })
      } finally {
        if (!disposed && generation === mine) { control = null; pending = null; emit({ loading: false }) }
      }
    })()
    return pending
  }
  let collecting: Promise<void> | null = null
  const collect = (): Promise<void> => {
    if (disposed) return Promise.resolve()
    if (collecting) return collecting
    // NOTHING CONFIGURED IS NOTHING TO COLLECT, said here rather than sent.
    // Collection walks the configured sources; with none there is nothing to
    // walk, so this is a no-op and not a wider read. The server would refuse it
    // too (`no-readable-source`), but it should not have to: no request is made.
    if (!at.saved.config?.sources.length) { emit({ collectionMessage: NO_SOURCE_TO_COLLECT }); return Promise.resolve() }
    emit({ collecting: true, collectionMessage: undefined })
    collecting = (async () => {
      try {
        const bound = await brainNow(page)
        if (!bound || page.moved() || bound.split('@')[0] !== at.brainKey.split('|').at(-1)) throw new Error('Collection unavailable: confirm this page’s Brain by reloading.')
        const who = await at.get('/fluid/api/participants?limit=1'), owner = obj(who.body)?.me
        if (who.status !== 200 || !entry(owner)) throw new Error('The server did not identify the owner. Nothing was collected.')
        const attemptKey = `${workingKey(at.brainKey)}:${at.saved.id}:collect`
        let op: string | null = null
        try { op = sessionStorage.getItem(attemptKey) } catch { /* Optional storage. */ }
        op ??= `magnet-collect-${crypto.randomUUID()}`
        try { sessionStorage.setItem(attemptKey, op) } catch { /* This request remains keyed. */ }
        const r = await fluidFetch(`/fluid/api/magnets/${encodeURIComponent(at.saved.id)}/activate`, { method: 'POST', headers: { ...CLIENT_HEADERS, [BRAIN_HEADER]: bound, 'Content-Type': 'application/json' }, body: JSON.stringify({ author: owner, op }) })
        const v = await r.json().catch(() => null)
        if (refusedAsOtherBrain(r.status, v)) page.move()
        if (!r.ok || !v?.artifact?.ref || v.magnet !== at.saved.id) {
          if (v?.refused === true) try { sessionStorage.removeItem(attemptKey) } catch { /* Optional storage. */ }
          throw new Error(v?.error ?? 'Collection outcome is unknown. Retry uses the same key; nothing retries automatically.')
        }
        try { sessionStorage.removeItem(attemptKey) } catch { /* Optional storage. */ }
        if (v.conversation && at.saved.config) at.saved.config.conversation = v.conversation
        emit({ collectionMessage: `Retained ${v.page?.results ?? ''} items. Showing the most recent batch; earlier batches remain in the Magnet Conversation.` })
        emit({ batchSelection: undefined })
        cancel()
        await read()
      } catch (e) { emit({ collectionMessage: e instanceof Error ? e.message : 'Collection failed.' }) }
      finally { collecting = null; emit({ collecting: false }) }
    })()
    return collecting
  }
  const cancel = () => { generation++; control?.abort(); control = null; pending = null; emit({ loading: false }) }
  return { id: at.id, brainKey: at.brainKey, saved: at.saved, snapshot: () => current,
    subscribe: (fn) => { if (!disposed) heard.add(fn); return () => { heard.delete(fn) } }, update: emit, read, collect, cancel,
    async selectBatch(batch) {
      if (batch && (!/^adm-[a-zA-Z0-9]{6,40}$/.test(batch.ref) || !/^[0-9a-f]{64}$/.test(batch.digest))) throw new Error('Choose a recorded batch with a verified digest.')
      cancel(); emit({ batchSelection: batch ?? undefined, results: [], activation: null, places: clearInspections(current.places), returnRoute: null }); await read()
    },
    dispose() { if (disposed) return; saveWorking(at.brainKey, at.saved.id, current); disposed = true; generation++; control?.abort(); heard.clear() },
  }
}
