/* WHICH BRAIN IS ANSWERING NOW, for anything kept about a decision.
 *
 * NEVER REMEMBERED. The same address can start serving another Brain while a
 * tab stays open (a deployment, a restore), and a restored or copied Brain
 * reuses ids; an identity read when the page loaded would then put one
 * Brain's half-made answer onto another's request. So this asks
 * `/api/brain?identity=1` itself, afresh, each time the decision is shown,
 * each time `again` changes and each time the reader returns to the tab -- it does not go through the page's own kept identity
 * (fluid/store.ts `brainIdentity`, which the rest of the page may keep).
 *
 * `undefined` while it is being read; `null` where the server did not say or
 * could not be asked: then nothing kept is restored and nothing is stored.
 *
 * (Needs you does not use this: it takes the identity from its own answer,
 * needs/about.ts. This is for a decision that has no such answer of its own:
 * the adoption decision on a record page.) */
import { useEffect, useState } from 'react'
import { scopeOf } from '../../experimental/draftKeep'
import { fluidFetch } from '../../fluid/http'

export async function readBrainScope(): Promise<string | null> {
  try {
    const res = await fluidFetch('/api/brain?identity=1', { headers: { 'X-Mentis-Client': '1' }, cache: 'no-store' })
    if (!res.ok) return null
    return scopeOf(await res.json() as { corpus_id?: string; corpus_path?: string | null })
  } catch { return null }
}

export function useFreshBrainScope(again: unknown): string | null | undefined {
  const [scope, setScope] = useState<string | null | undefined>(undefined)
  useEffect(() => {
    let on = true
    setScope(undefined)
    void readBrainScope().then((s) => { if (on) setScope(s) })
    /* and again whenever the reader comes back to the tab: that is when the
       server behind it may have become another */
    const back = () => { if (document.visibilityState === 'visible') void readBrainScope().then((s) => { if (on) setScope(s) }) }
    document.addEventListener('visibilitychange', back)
    window.addEventListener('focus', back)
    return () => { on = false; document.removeEventListener('visibilitychange', back); window.removeEventListener('focus', back) }
  }, [again])
  return scope
}
