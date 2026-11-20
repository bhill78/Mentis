/* WHICH BRAIN THIS PAGE WAS OPENED ON, AND NOTHING DECIDED ON IT GOING TO ANOTHER.
 *
 * Quiet Chat binds the page to the Brain the server serves when it opens
 * (`GET /fluid/api/needs-you/brain`: the Brain's id and an instance
 * fingerprint, never where it is), and from then on:
 *   - EVERY WRITE NAMES THAT BRAIN (`X-Mentis-Brain`). The server refuses a
 *     write naming another Brain than it serves, before anything is written
 *     (409 `BrainChanged`): a decision opened on one Brain is never recorded in
 *     another -- a different Brain, a copy served from elsewhere, or a copy
 *     restored in place.
 *   - WHAT A DECISION FORM IS DRAWN FROM IS CONFIRMED to be that Brain's
 *     (`confirmBrain`, after each read), so a form is never shown from another.
 *   - ONCE ANOTHER BRAIN HAS ANSWERED, THE PAGE STAYS "MOVED" until it is
 *     reloaded: only a reload binds it again. Nothing is carried across.
 *
 * A page that never bound (Fluid, or Quiet when the server could not say)
 * sends no Brain, and its writes are as they always were. Nothing here is kept
 * beyond the page. */

import { useSyncExternalStore } from 'react'

export const BRAIN_HEADER = 'X-Mentis-Brain'
export const BRAIN_PATH = '/fluid/api/needs-you/brain'

export type BrainId = { corpus_id?: string | null; instance?: string | null } | null | undefined

/** The Brain as the page names it back: `<corpus_id>@<instance>`; null where it named none. */
export const brainKeyOf = (b: BrainId): string | null =>
  ((b?.corpus_id ?? '').trim() && (b?.instance ?? '').trim() ? `${b!.corpus_id}@${b!.instance}` : null)

/** A binding, apart from the page, so it is checkable. */
export interface Binding {
  /** an answer named this Brain (null: it named none, which decides nothing). False once moved. */
  saw(brain: string | null): boolean
  /** the Brain the page is bound to, or null before any answer named one */
  bound(): string | null
  /** another Brain has answered since the page was bound: nothing here is current */
  moved(): boolean
  /** the server said so itself (a write was refused as another Brain's) */
  move(): void
  subscribe(f: () => void): () => void
}

export function createBinding(): Binding {
  let bound: string | null = null
  let moved = false
  const told = new Set<() => void>()
  const tell = () => told.forEach((f) => f())
  return {
    saw(brain) {
      if (brain === null) return !moved
      if (bound === null) { bound = brain; tell() }
      else if (brain !== bound && !moved) { moved = true; tell() }
      return !moved
    },
    bound: () => bound,
    moved: () => moved,
    move() { if (!moved) { moved = true; tell() } },
    subscribe(f) { told.add(f); return () => { told.delete(f) } },
  }
}

/** The page's own binding. */
export const page = createBinding()

/** The page has moved: another Brain answered since it was opened. */
export const useBrainMoved = (binding: Binding = page): boolean =>
  useSyncExternalStore(binding.subscribe, binding.moved, binding.moved)

/** What the page says once it has moved, and its way back to the Brain the server serves. */
export const MOVED_WORDS = 'The server now serves another Brain than this page was opened on. Nothing decided here will be recorded there. Reloading shows that Brain’s own requests; anything typed here and not sent is not carried over, so copy it first if you need it.'
export const RELOAD_WORDS = 'Reload for this Brain'

/** A response that says the write named another Brain than the server serves. */
export function refusedAsOtherBrain(status: number, body: unknown): boolean {
  return status === 409 && !!body && typeof body === 'object' && (body as { kind?: unknown }).kind === 'BrainChanged'
}

type Fetch = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>

/** Ask the server which Brain it serves, and say whether it is the one the page is bound to
 *  (binding it, where none is bound yet). False where another Brain answered. Null where the
 *  server could not say: nothing is decided by that. */
export async function confirmBrain(get: Fetch = (i, n) => globalThis.fetch(i, n)): Promise<boolean | null> {
  try {
    const r = await get(BRAIN_PATH, { headers: { 'X-Mentis-Client': '1' }, cache: 'no-store' })
    if (!r.ok) return null
    const got = await r.json().catch(() => null) as { brain?: BrainId } | null
    const key = brainKeyOf(got?.brain)
    if (key === null) return null
    return page.saw(key)
  } catch {
    return null
  }
}

const API = /^\/(api|fluid\/api)(\/|$|\?)/
const isWrite = (m: string) => m !== 'GET' && m !== 'HEAD' && m !== 'OPTIONS'

/** Every write this page makes to Mentis names the Brain it is bound to, and a refusal as
 *  another Brain's moves the page. Wraps `window.fetch` as `live.ts` does for the development
 *  server's Brain choice; reads and other addresses pass untouched. Once per page. */
export function guardWrites(binding: Binding = page): void {
  if (typeof window === 'undefined' || (window as { __mentisBrainGuard?: boolean }).__mentisBrainGuard) return
  ;(window as { __mentisBrainGuard?: boolean }).__mentisBrainGuard = true
  const plain = window.fetch.bind(window)
  window.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
    const method = (init?.method ?? (input instanceof Request ? input.method : 'GET')).toUpperCase()
    const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url
    const path = url.startsWith(location.origin) ? url.slice(location.origin.length) : url
    const bound = binding.bound()
    if (!isWrite(method) || !API.test(path) || bound === null) return plain(input, init)
    const headers = new Headers(init?.headers ?? (input instanceof Request ? input.headers : undefined))
    headers.set(BRAIN_HEADER, bound)
    const res = await plain(input, { ...init, headers })
    if (res.status === 409) {
      const body = await res.clone().json().catch(() => null)
      if (refusedAsOtherBrain(res.status, body)) binding.move()
    }
    return res
  }
}
