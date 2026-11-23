import { useEffect, useRef, useState } from 'react'
import type { MagnetResource } from './contract'
import { configurationRead } from './configuration'

interface Batch { post: string; artifact: { ref: string; digest: string; size: number }; at: number; state: string }
export default function BatchHistory({ resource }: { resource: MagnetResource }) {
  const [rows, setRows] = useState<Batch[]>([]), [next, setNext] = useState<string | null>(null)
  const [error, setError] = useState(''), [busy, setBusy] = useState(false)
  const alive = useRef(true), generation = useRef(0)
  const load = async (cursor?: string) => {
    const mine = ++generation.current; setBusy(true)
    try {
      const params = new URLSearchParams({ limit: '20' }); if (cursor) params.set('cursor', cursor)
      const v = await configurationRead(`/fluid/api/magnets/${encodeURIComponent(resource.saved.id)}/collection/history?${params}`)
      if (v.magnet !== resource.saved.id || !Array.isArray(v.batches)) throw new Error('Batch history did not identify this Magnet.')
      if (alive.current && mine === generation.current) { setRows((old) => cursor ? [...old, ...v.batches] : v.batches); setNext(v.next ?? null); setError('') }
    } catch (e) { if (alive.current && mine === generation.current) setError((e as Error).message) }
    finally { if (alive.current && mine === generation.current) setBusy(false) }
  }
  useEffect(() => { alive.current = true; void load(); return () => { alive.current = false; generation.current++ } }, [resource])
  const choose = async (batch: Batch | null) => {
    setBusy(true)
    try { await resource.selectBatch?.(batch?.artifact ?? null) }
    catch (e) { if (alive.current) setError((e as Error).message) }
    finally { if (alive.current) setBusy(false) }
  }
  return <section aria-label="Retained batch history"><h3>Retained batches</h3><p>Earlier collections keep their original captured content. Selecting one never collects or refreshes its sources.</p><button type="button" className="q2-magnet-link" disabled={busy} onClick={() => void choose(null)}>Show latest retained batch</button><ul className="q2-magnet-items">{rows.map((b) => <li key={b.artifact.ref}><button type="button" className="q2-magnet-link" disabled={busy} onClick={() => void choose(b)}>Collected {new Date(b.at * 1000).toLocaleString()} · {b.state}</button><small>{b.artifact.size.toLocaleString()} retained bytes</small></li>)}</ul>{next && <button type="button" disabled={busy} onClick={() => void load(next)}>Earlier batches</button>}{busy && <p role="status">Reading retained history…</p>}{error && <p role="status">{error}</p>}</section>
}
