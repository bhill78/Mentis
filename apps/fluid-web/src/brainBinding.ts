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

/** THE BRAIN THE PAGE IS BOUND TO, as it becomes known. Null before any
 *  answer names one -- which is most of a page's first moments, since the
 *  ask goes out while the page draws (`live.ts`) -- and null for a page that
 *  binds to none at all (legacy Fluid). Anything kept per Brain subscribes
 *  to this rather than reading `page.bound()` once at mount, where it would
 *  read that null and never hear the answer. */
export const useBrainBound = (binding: Binding = page): string | null =>
  useSyncExternalStore(binding.subscribe, binding.bound, binding.bound)

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

let guarded = false
/** This page binds itself to a Brain and guards its writes (Quiet Chat); false on every other
 *  page (Fluid), whose reads and writes are as they always were. */
export const guarding = () => guarded

/** What a write made before the page could say which Brain it is on comes to: NOT SENT. */
export const UNCONFIRMED = 'Nothing was sent: this page could not confirm which Brain the server serves. Try again in a moment.'

/** Bind the page if it is not yet bound: ask the server, once more if the first ask said
 *  nothing. The page's Brain, or null where it still cannot say. */
async function boundNow(binding: Binding, get: Fetch): Promise<string | null> {
  for (let i = 0; i < 2 && binding.bound() === null; i++) {
    if (binding !== page) break
    await confirmBrain(get)
  }
  return binding.bound()
}

/** WHICH BRAIN THIS PAGE IS ON, ASKED FOR NOW -- what the write guard resolves before a
 *  write leaves (`boundNow`), for anything that must know WHERE a submission is going
 *  while it is still being BUILT. A body is serialised before the guard ever sees it, so a
 *  page that asks only afterwards can carry values chosen for one Brain into another's
 *  work; whatever is scoped to the Brain asks this first instead.
 *
 *  Null where the page still cannot say, and null once it has moved: neither is a Brain to
 *  record anything against, and both are answers, not errors.
 *
 *  `fresh` asks again even when the page is already bound -- for a page that does NOT guard
 *  its writes (legacy Fluid), which would otherwise never notice the server having moved on
 *  to another Brain. A guarding page needs no second ask: its own writes are checked.
 *
 *  AND A FRESH ASK THAT CAME BACK WITH NOTHING IS NOT THE OLD ANSWER (re-review B1-F1). The
 *  fresh ask exists because nothing else on an unguarded page would notice the server having
 *  moved on; falling back to the binding it already had when that ask fails -- unreachable,
 *  a 503, an answer naming no Brain -- would defeat exactly the boundary it was added for,
 *  and send values scoped to the old Brain into whatever the server serves now. So where the
 *  page WAS bound and the fresh ask could not say, this is null: no Brain to place anything
 *  against, which is an answer and not an error. An unbound page has no old answer to fall
 *  back to, so its two asks stand as they were. */
export async function brainNow(
  binding: Binding = page,
  confirm: () => Promise<boolean | null> = confirmBrain,
  fresh = false,
): Promise<string | null> {
  if (fresh && !binding.moved()) {
    const had = binding.bound()
    if ((await confirm()) === null && had !== null) return null
  }
  for (let i = 0; i < 2 && binding.bound() === null && !binding.moved(); i++) await confirm()
  return binding.moved() ? null : binding.bound()
}

/** Every write this page makes to Mentis names the Brain it is bound to, and a refusal as
 *  another Brain's moves the page. Wraps `window.fetch` as `live.ts` does for the development
 *  server's Brain choice; reads and other addresses pass untouched. Once per page. */
export function guardWrites(binding: Binding = page): void {
  if (typeof window === 'undefined' || (window as { __mentisBrainGuard?: boolean }).__mentisBrainGuard) return
  ;(window as { __mentisBrainGuard?: boolean }).__mentisBrainGuard = true
  guarded = true
  const plain = window.fetch.bind(window)
  window.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
    const method = (init?.method ?? (input instanceof Request ? input.method : 'GET')).toUpperCase()
    const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url
    const path = url.startsWith(location.origin) ? url.slice(location.origin.length) : url
    if (!isWrite(method) || !API.test(path)) return plain(input, init)
    /* A WRITE BEFORE THE PAGE IS BOUND WAITS FOR THE BINDING, and where the page still cannot
       say which Brain it is on, it is not sent at all: it never leaves unnamed. */
    const bound = await boundNow(binding, plain)
    if (bound === null) {
      return new Response(JSON.stringify({ error: UNCONFIRMED, kind: 'BrainUnconfirmed' }),
        { status: 409, headers: { 'Content-Type': 'application/json' } })
    }
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
