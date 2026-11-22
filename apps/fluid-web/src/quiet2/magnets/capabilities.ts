import { useEffect, useState } from 'react'
import { CLIENT_HEADERS } from '../../api'
import { READ_ONLY } from '../live'
import { resourceCorpus } from './managementApi'

interface ScopedWrites { corpus_id: string; conversations: string[]; arrangements: string[] }
/** Only the disposable proxy exposes this scope. Normal servers use normal UI authority. */
export function useMagnetWrites(brainKey: string | null) {
  const [scope, setScope] = useState<ScopedWrites | null>(null)
  useEffect(() => {
    setScope(null)
    if (!READ_ONLY || !brainKey) return
    const abort = new AbortController()
    void fetch('/__q2/magnet-capabilities', { headers: CLIENT_HEADERS, signal: abort.signal, cache: 'no-store' }).then(async (r) => {
      const v = await r.json()
      if (!abort.signal.aborted && r.ok && v.fixture === true && v.corpus_id === resourceCorpus(brainKey) && Array.isArray(v.conversations) && Array.isArray(v.arrangements)) setScope(v)
    }).catch(() => {})
    return () => abort.abort()
  }, [brainKey])
  const valid = !!brainKey && scope?.corpus_id === resourceCorpus(brainKey)
  return {
    conversation: (id: string | null | undefined) => !!brainKey && (!READ_ONLY || (!!id && valid && scope!.conversations.includes(id))),
    arrangement: (id: string | null | undefined) => !!brainKey && (!READ_ONLY || (!!id && valid && scope!.arrangements.includes(id))),
    fixture: READ_ONLY && valid,
  }
}
