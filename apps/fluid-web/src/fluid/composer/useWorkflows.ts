import { useEffect, useState } from 'react'
import { getJson } from '../conversation/facts'
import { workflowsOf, type WorkflowRow } from './workflows'

/* THE ESTABLISHED WORKFLOWS, kept once for the page (as Settings keeps the
   Personas) and read again each time the `/` palette opens, since one may be
   established at any moment. A failed read keeps what was held; with nothing
   held the palette simply lists its commands. */
let held: WorkflowRow[] = []
const heard = new Set<() => void>()

function reread(): void {
  void getJson<Parameters<typeof workflowsOf>[0]>('/fluid/api/governed?state=standing&kind=workflow&limit=200')
    .then((g) => { held = workflowsOf(g) })
    .catch(() => {})
    .then(() => { for (const fn of [...heard]) fn() })
}

export function useWorkflows(open: boolean): WorkflowRow[] {
  const [, tick] = useState(0)
  useEffect(() => {
    const fn = () => tick((n) => n + 1)
    heard.add(fn)
    return () => { heard.delete(fn) }
  }, [])
  useEffect(() => { if (open) reread() }, [open])
  return held
}
