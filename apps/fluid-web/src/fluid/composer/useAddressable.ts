import { useEffect, useState } from 'react'
import { getJson } from '../conversation/facts'
import type { Person } from '../identity/people'
import { useDebounced } from './useDebounced'

/* `@` BEYOND THIS CONVERSATION (stage 1c): the names the record holds that
   match what is typed, searched by Fluid's own `/fluid/api/participants?q=`
   once typing pauses -- not production's `/api/participants`, which lists
   everybody with where each last ran. `runtimes=1` keeps what each declared
   runs its work, which the palette says beside the name. */

interface Row { id: string; alias: string; about?: string; default_runtime?: string | null; runtime_mode?: Person['runtime_mode'] }

/** How many names one search returns; the palette shows five of them. */
export const ADDRESSABLE_LIMIT = 20

export function addressablePath(q: string): string {
  return `/fluid/api/participants?q=${encodeURIComponent(q)}&limit=${ADDRESSABLE_LIMIT}&runtimes=1`
}

export const personOfRow = (r: Row): Person => ({
  participant: r.id, alias: r.alias, about: r.about,
  default_runtime: r.default_runtime ?? null, runtime_mode: r.runtime_mode,
})

/** The names matching `query` (an `@` trigger's words), or null while the
 *  words typed are not yet the words answered. Nothing is asked for none. */
export function useAddressable(query: string): { data: Person[] | null } {
  const q = query.trim().replace(/^@/, '')
  const asked = useDebounced(q)
  const [got, setGot] = useState<{ q: string; people: Person[] } | null>(null)
  useEffect(() => {
    if (!asked) return
    let live = true
    void getJson<{ participants: Row[] }>(addressablePath(asked))
      .then((d) => { if (live) setGot({ q: asked, people: d.participants.map(personOfRow) }) })
      .catch(() => { if (live) setGot({ q: asked, people: [] }) })
    return () => { live = false }
  }, [asked])
  return { data: q && got?.q === q ? got.people : null }
}
