import { useEffect, useState } from 'react'
import { getJson } from '../conversation/facts'
import { PAUSE_MS } from './useDebounced'
import { workflowsOf, type WorkflowRow } from './workflows'

/* THE ESTABLISHED WORKFLOWS, kept once for the page (as Settings keeps the
   Personas) and read again each time the `/` palette opens, since one may be
   established at any moment. A failed read keeps what was held; with nothing
   held the palette simply lists its commands.

   AT MOST ONE ASK PER TYPING PAUSE (stage 1c): the palette opening and
   closing as `/` words are typed and erased asks once it has stayed open for
   a pause, and never while an ask is still out. What is held shows meanwhile. */
let held: WorkflowRow[] = []
let out: Promise<void> | null = null
const heard = new Set<() => void>()

export const WORKFLOWS_PATH = '/fluid/api/governed?state=standing&kind=workflow&limit=200'

/** Read the Workflows again, unless an ask is already out (then: that one).
 *  `get` is the read itself, given by the tests. */
export function reread(get: (path: string) => Promise<Parameters<typeof workflowsOf>[0]> = getJson): Promise<void> {
  if (out) return out
  out = get(WORKFLOWS_PATH)
    .then((g) => { held = workflowsOf(g) })
    .catch(() => {})
    .then(() => { out = null; for (const fn of [...heard]) fn() })
  return out
}

/** What is held now (for the tests). */
export const heldWorkflows = () => held

export function useWorkflows(open: boolean): WorkflowRow[] {
  const [, tick] = useState(0)
  useEffect(() => {
    const fn = () => tick((n) => n + 1)
    heard.add(fn)
    return () => { heard.delete(fn) }
  }, [])
  useEffect(() => {
    if (!open) return
    const t = window.setTimeout(() => { void reread() }, PAUSE_MS)
    return () => clearTimeout(t)
  }, [open])
  return held
}
