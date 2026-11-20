/* WHICH BRAIN THIS PAGE IS READING, for anything kept about a decision.
 *
 * The same address can serve another Brain later (a restored or copied Brain
 * reuses ids), so what is kept for a request -- what it is about, a half-made
 * answer -- is kept for the Brain it was read from (`/api/brain?identity=1`,
 * the identity the page's Brain badge and the 3D Brain already use: its id
 * and where it is). `undefined` while that is being read, `null` where the
 * server did not say: then nothing is kept beyond the page. */
import { useEffect, useState } from 'react'
import { scopeOf } from '../../experimental/draftKeep'
import { brainIdentity } from '../../fluid/store'

let known: string | null | undefined

export function useBrainScope(): string | null | undefined {
  const [scope, setScope] = useState<string | null | undefined>(known)
  useEffect(() => {
    if (known !== undefined) { setScope(known); return }
    let on = true
    void brainIdentity().then((b) => { if (b) known = scopeOf(b); if (on) setScope(b ? scopeOf(b) : null) }, () => { if (on) setScope(null) })
    return () => { on = false }
  }, [])
  return scope
}
